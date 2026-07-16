# bridge

Chat bridge service for de-demo (fictional Acme Corp universe). Bridges a
chat-platform webhook to a persistent `claude` CLI subprocess per
conversation thread (`channel_id:thread_id`), with slash commands, an
allowlist/admin gate, and lightweight cross-thread memory recall.

This is a deliberately simplified demo build of the full production design
described in `docs/50-bridge/`. See "Demo simplifications" below.

## Ports

- The bridge's own HTTP webhook server listens on **port 9100** by default
  (`server.port` in config).
- The mock chat client (`mocks/chat_client.py`) runs its own tiny local
  callback listener on **port 9101** by default (`--callback-port`), which
  receives the bridge's outbound reply POSTs. Point the bridge's
  `chat.api_base_url` at this listener (e.g. `http://localhost:9101`) so
  replies get delivered back to the mock client.
- **Port 8801** belongs to an unrelated component: the mock Change Gateway
  in `mocks/change_gateway.py`. It has nothing to do with the bridge or the
  chat client — don't confuse it with 9100/9101.

## Future wiring into `./de serve`

Per `DESIGN.md` S6, `./de serve` is *expected* to eventually:

1. Render `scaffold/templates/bridge.yaml.j2` into
   `<instance>/log/bridge-config.yaml` (secrets injected via env refs).
2. Launch `uv run --project bridge python -m bridge.app --config <path>`.
3. Track the process via the PID file written at `log/bridge-http.pid`.

**This is not yet implemented.** `scaffold/de serve` currently just prints
"later milestone" — the bridge built here is a fully standalone,
independently testable service, not yet wired into the `de` CLI. That's
expected and out of scope for this task.

## Quickstart

Install and run the bridge directly against the example config:

```bash
cd de-demo
uv run --project bridge python -m bridge.app --config bridge/config.example.yaml
```

In another shell, drive it with the mock chat client:

```bash
python3 mocks/chat_client.py \
  --bridge-url http://localhost:9100 \
  --secret changeme-demo-secret \
  --channel c1 --thread t1 --sender u1 \
  --message "hello"
```

Note: `bridge/config.example.yaml` points `agent.claude_cmd` at `"claude"`
(the real Claude Code CLI). For fully offline smoke testing without a real
`claude` binary, point `agent.claude_cmd` at the test shim, e.g.:

```yaml
agent:
  claude_cmd: "python3 bridge/tests/fake_claude.py"
```

## Config format

See `bridge/config.example.yaml` for the full annotated shape. Top-level
keys: `chat`, `server`, `agent`, `sessions`, `auth`, `memory`,
`reply_transport`. The loader (`bridge/bridge/config.py`) is lenient: any
missing key gets a dataclass default, and unknown extra keys are ignored.

## Running tests

Fully offline, no live `claude` binary or non-loopback network needed:

```bash
uv run --project bridge --extra dev pytest bridge/tests -q
```

Tests use `bridge/tests/fake_claude.py`, a minimal stdin/stdout shim that
emulates the `claude --output-format stream-json --input-format stream-json
--verbose --permission-mode <mode>` protocol closely enough to exercise
session spawn/resume/reuse/isolation and the webhook HMAC/verification/
allowlist/`/reset` flows end to end.

## Demo simplifications (vs. the full docs/50-bridge design)

- No relay mode — webhook mode only.
- No managed workspaces / runtime snapshot isolation — sessions use a
  single configurable working directory (with per-session `/cd` override).
- No dream consolidation loop — `bridge/bridge/dream.py` is a stub only,
  not wired into any scheduler.
- No custom `slash_commands` config surface — only the fixed built-in
  command set (`/help /reset /cd /pwd /plan /mode`).
- No real bash passthrough for `!`-prefixed messages — only admin-gating
  plus a "not implemented in this demo" reply.
- No quoted-message context threading or `no_mention_groups` filtering.
