"""Headless agent invocation + stream-json transcript parsing.

eval-spec.md §3.1/§5.4: the runner spawns `claude -p "<prompt>"
--output-format stream-json --verbose` with cwd = the built runtime and the
S3 env floor, then inspects tool_use blocks (trigger detection) and the
final assistant text (result-axis judging).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AgentRun:
    returncode: int
    frames: list[dict[str, Any]] = field(default_factory=list)
    raw_lines: list[str] = field(default_factory=list)
    stderr: str = ""

    def tool_uses(self) -> list[dict[str, Any]]:
        """All tool_use content blocks across every assistant message frame."""
        out: list[dict[str, Any]] = []
        for frame in self.frames:
            message = frame.get("message") or {}
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    out.append(block)
        return out

    def final_text(self) -> str:
        """Best-effort final assistant text: concatenation of the last
        assistant message's text blocks, falling back to the `result` frame."""
        for frame in reversed(self.frames):
            if frame.get("type") == "result" and isinstance(frame.get("result"), str):
                return frame["result"]
        for frame in reversed(self.frames):
            message = frame.get("message") or {}
            if frame.get("type") == "assistant" or message.get("role") == "assistant":
                content = message.get("content")
                if isinstance(content, list):
                    texts = [
                        b.get("text", "")
                        for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    ]
                    if texts:
                        return "\n".join(texts)
        return ""


def skill_triggered(run: AgentRun, skill_name: str) -> bool:
    """Trigger = a `Skill` tool_use whose input references skill_name anywhere."""
    for block in run.tool_uses():
        if str(block.get("name", "")).lower() != "skill":
            continue
        if _contains_skill_name(block.get("input"), skill_name):
            return True
    return False


def _contains_skill_name(obj: Any, skill_name: str) -> bool:
    if isinstance(obj, str):
        return skill_name in obj
    if isinstance(obj, dict):
        return any(_contains_skill_name(v, skill_name) for v in obj.values())
    if isinstance(obj, list):
        return any(_contains_skill_name(v, skill_name) for v in obj)
    return False


def run_agent(
    prompt: str,
    cwd: Path,
    env: dict[str, str],
    extra_args: list[str] | None = None,
    timeout: int = 300,
) -> AgentRun:
    """Spawns `claude -p <prompt> --output-format stream-json --verbose`."""
    cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose"]
    if extra_args:
        cmd.extend(extra_args)
    # Headless runs in an untrusted workspace ignore the runtime's
    # settings.json permissions.allow, so the harness grants the eval floor
    # explicitly. The scaffold hooks (skill-gate etc.) still apply on top.
    if "--allowedTools" not in cmd:
        cmd.extend(["--allowedTools", "Skill,Read,Grep,Glob,Bash(uv:*)"])
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    frames: list[dict[str, Any]] = []
    raw_lines = proc.stdout.splitlines()
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            frames.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return AgentRun(returncode=proc.returncode, frames=frames, raw_lines=raw_lines, stderr=proc.stderr)


def env_floor(runtime_dir: Path, scope_service_catalog: str, base_env: dict[str, str]) -> dict[str, str]:
    """ARCHITECTURE.md §Cross-component contracts item 3 / DESIGN.md S3."""
    env = dict(base_env)
    env["DE_AGENT_PROJECT_DIR"] = str(runtime_dir)
    env["DE_SCOPE_SERVICE_CATALOG"] = scope_service_catalog
    return env
