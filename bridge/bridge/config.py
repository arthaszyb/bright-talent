"""Config loading for the bridge demo.

Accepts the simplified YAML schema described in bridge/README.md. Lenient
about unknown keys and missing keys (dataclass-style defaults applied).
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import yaml


@dataclasses.dataclass
class ChatConfig:
    app_id: str = "demo-app-id"
    signing_secret: str = "changeme-demo-secret"
    api_base_url: str = ""
    bot_id: str = "demo-bot"


@dataclasses.dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 9100
    pid_file: str = "log/bridge-http.pid"


@dataclasses.dataclass
class AgentConfig:
    claude_cmd: str = "claude"
    permission_mode: str = "acceptEdits"
    extra_args: list = dataclasses.field(default_factory=list)
    env: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class SessionsConfig:
    idle_timeout_seconds: int = 60
    max_sessions: int = 20
    working_dir: str = "./runtime"
    data_dir: str = "./data"


@dataclasses.dataclass
class AuthConfig:
    allowed_users: list = dataclasses.field(default_factory=list)
    admin_users: list = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class MemoryConfig:
    enabled: bool = True
    context_min_chars: int = 5
    context_max_chars: int = 2000
    context_max_results: int = 3


@dataclasses.dataclass
class BridgeConfig:
    chat: ChatConfig = dataclasses.field(default_factory=ChatConfig)
    server: ServerConfig = dataclasses.field(default_factory=ServerConfig)
    agent: AgentConfig = dataclasses.field(default_factory=AgentConfig)
    sessions: SessionsConfig = dataclasses.field(default_factory=SessionsConfig)
    auth: AuthConfig = dataclasses.field(default_factory=AuthConfig)
    memory: MemoryConfig = dataclasses.field(default_factory=MemoryConfig)
    reply_transport: str = "log+callback"


def _build(cls, data: dict[str, Any]):
    data = data or {}
    field_names = {f.name for f in dataclasses.fields(cls)}
    kwargs = {k: v for k, v in data.items() if k in field_names}
    return cls(**kwargs)


def load_config(path: str | Path) -> BridgeConfig:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    return config_from_dict(raw)


def config_from_dict(raw: dict[str, Any]) -> BridgeConfig:
    raw = raw or {}
    return BridgeConfig(
        chat=_build(ChatConfig, raw.get("chat", {})),
        server=_build(ServerConfig, raw.get("server", {})),
        agent=_build(AgentConfig, raw.get("agent", {})),
        sessions=_build(SessionsConfig, raw.get("sessions", {})),
        auth=_build(AuthConfig, raw.get("auth", {})),
        memory=_build(MemoryConfig, raw.get("memory", {})),
        reply_transport=raw.get("reply_transport", "log+callback"),
    )
