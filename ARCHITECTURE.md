# de-demo Architecture Conventions (binding for all components)

Demo of the Acme Corp Digital Employee platform. The original spec blueprint (`docs/…`, cited by section number throughout module docstrings) is not part of this repository; this file and `DESIGN.md` carry everything binding — this file fixes the cross-component conventions the specs left open.

## Layout (fixed)

```
de-demo/
├── mocks/                      # change_gateway.py (port 8801), service_catalog.json, chat_client.py (port 9100 side)
├── scaffold/
│   ├── VERSION                 # 0.1.0
│   ├── base/
│   │   ├── de                  # instance CLI (bash, managed file — copied into instance repos)
│   │   ├── .claude/
│   │   │   ├── hooks/          # 6 security hooks
│   │   │   ├── policy/         # 4 policy YAMLs
│   │   │   └── tools/          # de-agent-escalate MCP stub
│   │   └── kb/                 # foundational KB
│   ├── templates/              # *.j2 + instance/ (init templates)
│   ├── instance-test-seeds/    # 5 common guardrail *.mock.yaml (copied verbatim from docs)
│   └── builder/                # Python package (uv project: pyproject.toml)
├── instances/acme-checkout-sre/
├── skills/skills/ticket-review/
├── eval/                       # de-eval (uv project)
├── bridge/                     # FastAPI (uv project)
├── console/                    # backend/ (FastAPI+SQLite) + frontend/ (React SPA)
└── scripts/leak-check.sh
```

## Cross-component contracts

1. **Scaffold resolution (demo monorepo shortcut):** instances reference the local scaffold. `de` resolves scaffold root as `${DE_SCAFFOLD_ROOT:-<instance_root>/../../scaffold}`. `instance.yaml` uses `base: {version: "0.1.0", repo: "file://../../scaffold"}`. No network fetch in the demo; "fetch base" = copy from that path into `.base-cache/`.
2. **Builder invocation:** `de` calls `uv run --project "$SCAFFOLD_ROOT/builder" python -m builder.<module> <args>`. Builder modules expose `python -m builder.build|validate|diff|doctor|status <instance_root>`.
3. **Env contract:** before any agent/hook/eval run, export `DE_AGENT_PROJECT_DIR=<instance_root>/runtime` (or `editor/`), `DE_SCOPE_SERVICE_CATALOG=<comma-separated scope>`. Hooks resolve all paths through `DE_AGENT_PROJECT_DIR`; hook state lives under `$DE_AGENT_PROJECT_DIR/work/`.
4. **Ports:** Change Gateway mock **8801**; chat mock **9100**. Never cross-wire. Skill scripts read `CHANGE_GATEWAY_BASE` (default `http://localhost:8801`).
5. **Python:** every runnable component is a `uv` project (`pyproject.toml`, Python >=3.11, stdlib-preferred; declare real deps only where needed: builder needs `jinja2`+`pyyaml`, bridge needs `fastapi`+`uvicorn`). Never call system `python3`.
6. **Exit codes (`de` and `de-eval`):** 0 success / 1 operational failure / 2 usage error.
7. **Sanitization:** every new file must pass `scripts/leak-check.sh` (run from de-demo root) before commit. Fictional universe only: Acme Corp, `*.acme.example`, `mentor-one@acme.example`, `DE-ACME-CHECKOUT-001`, `acme.storefront.*` / `acme.logistics.*` catalog paths.
8. **Versioning:** scaffold `VERSION`=0.1.0; skill `ticket-review` v0.1.0; strict digits-only semver everywhere.
