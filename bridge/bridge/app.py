"""FastAPI webhook bridge for de-demo.

Run as: python -m bridge.app --config <path/to/config.yaml>
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import BackgroundTasks, FastAPI, Request, Response

from . import auth, commands, sanitize
from .config import BridgeConfig, load_config
from .memory import Memory
from .sessions import SessionManager

logger = logging.getLogger("bridge.app")

# The placeholder secret shipped in config.example.yaml / bridge.yaml.j2.
# Anyone who knows it can forge valid webhook signatures.
DEMO_SIGNING_SECRET = "changeme-demo-secret"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def enforce_signing_secret_policy(config: BridgeConfig) -> None:
    """Refuse to expose the bridge beyond loopback with the well-known demo
    secret; on loopback, warn loudly instead of failing the demo flow."""
    if config.chat.signing_secret != DEMO_SIGNING_SECRET:
        return
    if config.server.host not in _LOOPBACK_HOSTS:
        raise SystemExit(
            "bridge: refusing to bind to "
            f"{config.server.host!r} with the default demo signing secret — "
            "set CHATOPS_SIGNING_SECRET (or chat.signing_secret) to a real value "
            "before exposing the webhook beyond loopback."
        )
    logger.warning(
        "bridge: running with the default demo signing secret (loopback only); "
        "set CHATOPS_SIGNING_SECRET for any non-demo deployment"
    )


def enforce_allowlist_policy(config: BridgeConfig) -> None:
    """Warn loudly when no user allowlist is configured.

    `auth.is_allowed` fail-opens on an empty `allowed_users`: with a valid
    signature, *any* sender may then drive the agent. That is a fine demo
    default on loopback, but off-box it is an easy footgun (an open bridge),
    so surface it — escalated when the bind is non-loopback. We warn rather
    than fail because a properly-set signing secret already limits delivery
    to the real chat platform, so an open user list can be a deliberate
    choice; the operator should just make it knowingly."""
    if config.auth.allowed_users:
        return
    if config.server.host not in _LOOPBACK_HOSTS:
        logger.warning(
            "bridge: bound to %r with an EMPTY user allowlist — any "
            "signature-valid sender can drive the agent. Set auth.allowed_users "
            "to restrict who may use the bridge before exposing it beyond loopback.",
            config.server.host,
        )
        return
    logger.warning(
        "bridge: no user allowlist configured (auth.allowed_users is empty); "
        "every signature-valid sender is accepted (loopback only)"
    )


async def deliver_reply(channel_id, thread_id, text: str, config: BridgeConfig) -> None:
    """Always log the reply; best-effort POST it to chat.api_base_url."""
    logger.info("[reply] channel=%s thread=%s text=%s", channel_id, thread_id, text)
    if config.chat.api_base_url:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    config.chat.api_base_url,
                    json={"channel_id": channel_id, "thread_id": thread_id, "text": text},
                )
        except Exception:
            logger.warning(
                "failed to deliver reply callback to %s", config.chat.api_base_url, exc_info=True
            )


async def handle_event(
    event: dict, config: BridgeConfig, sessions: SessionManager, memory: Memory
) -> None:
    """Background handler for a verified, parsed webhook event."""
    if event.get("event_type") != "message":
        logger.debug("handle_event: ignoring event_type=%s", event.get("event_type"))
        return

    sender = event.get("sender") or {}
    if not auth.is_allowed(sender, config):
        logger.debug("handle_event: dropping message from disallowed sender %s", sender)
        return

    channel_id = event.get("channel_id")
    thread_id = event.get("thread_id")
    key = f"{channel_id}:{thread_id}"
    text = sanitize.sanitize_inbound_text((event.get("text") or "").strip())

    if commands.is_command(text):
        token = text.split(" ", 1)[0]
        if token in commands.ADMIN_COMMANDS and not auth.is_admin(sender, config):
            reply_text = auth.REFUSAL_MESSAGE
        else:
            reply_text = await commands.handle_command(
                text,
                key,
                sessions,
                is_admin=auth.is_admin(sender, config),
                base_mode=config.agent.permission_mode,
            )
        await deliver_reply(channel_id, thread_id, reply_text, config)
        return

    if text.startswith("!"):
        if not auth.is_admin(sender, config):
            await deliver_reply(channel_id, thread_id, auth.REFUSAL_MESSAGE, config)
            return
        await deliver_reply(channel_id, thread_id, auth.BASH_NOT_IMPLEMENTED_MESSAGE, config)
        return

    augmented_text = memory.inject_context(channel_id, thread_id, text)
    reply_text = await sessions.send_turn(key, augmented_text)

    memory.record(channel_id, thread_id, "user", text)
    memory.record(channel_id, thread_id, "assistant", reply_text)

    await deliver_reply(channel_id, thread_id, reply_text, config)


def create_app(config: BridgeConfig) -> FastAPI:
    sessions = SessionManager(config)
    memory = Memory(config, config.sessions.data_dir)
    pid_path = Path(config.server.pid_file)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        pid_path.parent.mkdir(parents=True, exist_ok=True)
        pid_path.write_text(str(os.getpid()))
        sweep_task = asyncio.create_task(sessions.idle_sweep_loop())
        try:
            yield
        finally:
            sweep_task.cancel()
            try:
                await sweep_task
            except asyncio.CancelledError:
                pass
            await sessions.shutdown_all()
            memory.close()
            try:
                pid_path.unlink()
            except FileNotFoundError:
                pass

    app = FastAPI(lifespan=lifespan)
    app.state.config = config
    app.state.sessions = sessions
    app.state.memory = memory

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.post("/webhook/events")
    async def webhook_events(request: Request, background_tasks: BackgroundTasks):
        raw_body = await request.body()
        signature = request.headers.get("X-Chat-Signature")
        expected = hmac.new(
            config.chat.signing_secret.encode("utf-8"), raw_body, hashlib.sha256
        ).hexdigest()
        if not signature or not hmac.compare_digest(signature, expected):
            return Response(status_code=401)

        try:
            event = json.loads(raw_body)
        except json.JSONDecodeError:
            return Response(status_code=400)

        if event.get("event_type") == "verification":
            return {"challenge": event.get("challenge")}

        background_tasks.add_task(handle_event, event, config, sessions, memory)
        return {"status": "ok"}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="de-demo chat bridge")
    parser.add_argument("--config", required=True, help="path to bridge config YAML")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    config = load_config(args.config)
    enforce_signing_secret_policy(config)
    enforce_allowlist_policy(config)
    app = create_app(config)

    import uvicorn

    uvicorn.run(app, host=config.server.host, port=config.server.port)


if __name__ == "__main__":
    main()
