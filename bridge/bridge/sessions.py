"""Persistent Claude CLI subprocess sessions, keyed by channel:thread."""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import shlex
from pathlib import Path
from typing import Optional

from .config import BridgeConfig

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 4

# User-visible replies for the two agent-side failure modes. The session is
# stopped in both cases; the next message respawns it (resuming session_id).
AGENT_DIED_REPLY = (
    "(bridge) the agent session ended unexpectedly and has been reset — "
    "please resend your message."
)
AGENT_TIMEOUT_REPLY = (
    "(bridge) the agent did not finish responding within {timeout}s; the "
    "session has been reset — please retry."
)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class ClaudeSession:
    """Bookkeeping + live subprocess handle for one channel:thread session."""

    def __init__(self, key: str, working_dir: str, permission_mode: str):
        self.key = key
        self.session_id: Optional[str] = None
        self.created_at: str = _now_iso()
        self.last_active_at: str = self.created_at
        self.working_dir_override: Optional[str] = None
        self.permission_mode_override: Optional[str] = None
        self._default_working_dir = working_dir
        self._default_permission_mode = permission_mode
        self.process: Optional[asyncio.subprocess.Process] = None
        self.lock = asyncio.Lock()

    @property
    def working_dir(self) -> str:
        return self.working_dir_override or self._default_working_dir

    @property
    def permission_mode(self) -> str:
        return self.permission_mode_override or self._default_permission_mode

    def touch(self) -> None:
        self.last_active_at = _now_iso()

    def is_alive(self) -> bool:
        return self.process is not None and self.process.returncode is None


class SessionManager:
    def __init__(self, config: BridgeConfig):
        self.config = config
        self.data_dir = Path(config.sessions.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_path = self.data_dir / "sessions.json"
        self._sessions: dict[str, ClaudeSession] = {}
        self._global_lock = asyncio.Lock()
        self._load_state()

    # ---------- persistence ----------

    def _load_state(self) -> None:
        if not self.sessions_path.exists():
            return
        try:
            raw = json.loads(self.sessions_path.read_text())
        except Exception:
            logger.exception("sessions: failed to read %s", self.sessions_path)
            return
        for key, entry in (raw.get("sessions") or {}).items():
            sess = ClaudeSession(
                key,
                self.config.sessions.working_dir,
                self.config.agent.permission_mode,
            )
            sess.session_id = entry.get("session_id")
            sess.created_at = entry.get("created_at", sess.created_at)
            sess.last_active_at = entry.get("last_active_at", sess.last_active_at)
            self._sessions[key] = sess

    def _save_state(self) -> None:
        data = {
            "schema_version": SCHEMA_VERSION,
            "sessions": {
                key: {
                    "session_id": sess.session_id,
                    "created_at": sess.created_at,
                    "last_active_at": sess.last_active_at,
                }
                for key, sess in self._sessions.items()
                if sess.session_id is not None
            },
        }
        tmp_path = self.sessions_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(data, indent=2))
        os.replace(tmp_path, self.sessions_path)

    # ---------- session lifecycle ----------

    def _get_or_create_entry(self, key: str) -> ClaudeSession:
        sess = self._sessions.get(key)
        if sess is None:
            sess = ClaudeSession(
                key,
                self.config.sessions.working_dir,
                self.config.agent.permission_mode,
            )
            self._sessions[key] = sess
        return sess

    def get_working_dir(self, key: str) -> str:
        sess = self._sessions.get(key)
        if sess is None:
            return self.config.sessions.working_dir
        return sess.working_dir

    def set_cwd_override(self, key: str, directory: str) -> None:
        sess = self._get_or_create_entry(key)
        sess.working_dir_override = directory

    def set_permission_mode_override(self, key: str, mode: str) -> None:
        sess = self._get_or_create_entry(key)
        sess.permission_mode_override = mode

    def _live_count(self) -> int:
        return sum(1 for s in self._sessions.values() if s.is_alive())

    async def _evict_lru(self) -> None:
        live = [s for s in self._sessions.values() if s.is_alive()]
        if not live:
            return
        lru = min(live, key=lambda s: s.last_active_at)
        logger.info("sessions: evicting LRU session %s (max_sessions reached)", lru.key)
        await self._stop_process(lru)

    async def _spawn(self, sess: ClaudeSession) -> None:
        working_dir = sess.working_dir
        Path(working_dir).mkdir(parents=True, exist_ok=True)
        base_cmd = shlex.split(self.config.agent.claude_cmd)
        args = list(base_cmd) + [
            "--output-format", "stream-json",
            "--input-format", "stream-json",
            "--verbose",
            "--permission-mode", sess.permission_mode,
        ]
        if sess.session_id:
            args += ["--resume", sess.session_id]
        args += list(self.config.agent.extra_args)

        env = {**os.environ, **self.config.agent.env}
        logger.info("sessions: spawning subprocess for %s: %s", sess.key, args)
        sess.process = await asyncio.create_subprocess_exec(
            *args,
            cwd=working_dir,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

    async def _stop_process(self, sess: ClaudeSession) -> None:
        proc = sess.process
        if proc is None:
            return
        if proc.returncode is not None:
            sess.process = None
            return
        try:
            if proc.stdin is not None and not proc.stdin.is_closing():
                proc.stdin.close()
        except Exception:
            pass
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            proc.kill()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning("sessions: process for %s did not die after kill()", sess.key)
        sess.process = None

    async def get_or_start(self, key: str) -> ClaudeSession:
        async with self._global_lock:
            sess = self._get_or_create_entry(key)
            if sess.is_alive():
                return sess
            if self._live_count() >= self.config.sessions.max_sessions:
                await self._evict_lru()
            await self._spawn(sess)
            return sess

    async def send_turn(self, key: str, text: str) -> str:
        sess = await self.get_or_start(key)
        async with sess.lock:
            reply = await self._send_and_read(sess, text)
            sess.touch()
            self._save_state()
            return reply

    async def _send_and_read(self, sess: ClaudeSession, text: str) -> str:
        proc = sess.process
        if proc is None or proc.stdin is None or proc.stdout is None:
            return ""
        frame = json.dumps({"type": "user", "message": {"role": "user", "content": text}}) + "\n"
        try:
            proc.stdin.write(frame.encode("utf-8"))
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            logger.warning("sessions: cannot write to subprocess for %s: %s", sess.key, e)
            await self._stop_process(sess)
            return AGENT_DIED_REPLY

        timeout = max(1, int(self.config.sessions.turn_timeout_seconds))
        deadline = asyncio.get_running_loop().time() + timeout

        buffer: list[str] = []
        reply_text = ""
        turn_ended = False
        agent_died = False
        while not turn_ended:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                logger.warning("sessions: turn timed out after %ss for %s", timeout, sess.key)
                await self._stop_process(sess)
                return AGENT_TIMEOUT_REPLY.format(timeout=timeout)
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
            except asyncio.TimeoutError:
                logger.warning("sessions: turn timed out after %ss for %s", timeout, sess.key)
                await self._stop_process(sess)
                return AGENT_TIMEOUT_REPLY.format(timeout=timeout)
            if not line:
                logger.warning("sessions: subprocess stdout closed mid-turn for %s", sess.key)
                await self._stop_process(sess)
                agent_died = True
                break
            line = line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("sessions: skipping non-JSON line from subprocess: %r", line)
                continue

            obj_type = obj.get("type")
            if obj_type == "system":
                sid = obj.get("session_id")
                if sid:
                    sess.session_id = sid
                    self._save_state()
            elif obj_type == "assistant":
                sid = obj.get("session_id")
                if sid:
                    sess.session_id = sid
                message = obj.get("message") or {}
                for block in message.get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "text":
                        buffer.append(block.get("text", ""))
            elif obj_type == "stream_event":
                pass
            elif obj_type == "result":
                sid = obj.get("session_id")
                if sid:
                    sess.session_id = sid
                    self._save_state()
                result_text = obj.get("result") or ""
                reply_text = result_text if result_text else "".join(buffer)
                turn_ended = True
            elif obj_type == "error":
                error = obj.get("error") or {}
                reply_text = error.get("message", "") or "".join(buffer)
                turn_ended = True
            elif obj_type in ("user", "control_response"):
                logger.debug("sessions: tolerated frame type %s for %s", obj_type, sess.key)
            else:
                logger.debug("sessions: unknown frame type %s for %s", obj_type, sess.key)

        if not reply_text:
            reply_text = "".join(buffer)
        if agent_died and not reply_text:
            return AGENT_DIED_REPLY
        return reply_text

    def reset(self, key: str) -> None:
        sess = self._sessions.get(key)
        if sess is not None:
            self._sessions.pop(key, None)
        self._save_state()

    async def reset_async(self, key: str) -> None:
        sess = self._sessions.get(key)
        if sess is not None:
            await self._stop_process(sess)
        self.reset(key)

    async def idle_sweep(self) -> None:
        cutoff_seconds = self.config.sessions.idle_timeout_seconds
        now = datetime.datetime.now(datetime.timezone.utc)
        for sess in list(self._sessions.values()):
            if not sess.is_alive():
                continue
            try:
                last_active = datetime.datetime.fromisoformat(sess.last_active_at)
            except ValueError:
                continue
            idle_for = (now - last_active).total_seconds()
            if idle_for > cutoff_seconds:
                logger.info("sessions: idling out %s after %.1fs", sess.key, idle_for)
                await self._stop_process(sess)

    async def idle_sweep_loop(self, interval_seconds: float = 5.0) -> None:
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                await self.idle_sweep()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("sessions: idle sweep loop error")

    async def shutdown_all(self) -> None:
        for sess in list(self._sessions.values()):
            await self._stop_process(sess)
