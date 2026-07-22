# Contributing

Thanks for your interest in the intelligent-staff platform demo. This page is
the short version; `ARCHITECTURE.md` (binding conventions) and `DESIGN.md`
(seam contracts, deviation register) are the authoritative design docs.

## Ground rules

- **Fictional universe only.** Everything must live in the Acme Corp universe
  (`*.acme.example`, `acme.storefront.*`). `scripts/leak-check.sh` enforces
  the red lines mechanically — run it before every commit:

  ```bash
  bash scripts/leak-check.sh .
  ```

- **Never hand-edit build artifacts.** `instances/*/runtime/` and `editor/`
  are compiled output; change `instance.yaml` / templates / base and rebuild.
- **Safety invariants are load-bearing.** Changes that loosen permission
  monotonicity, base-file no-shadowing, protected MCP servers, or the
  propose-don't-execute stance need a design discussion first (open an issue).

## Dev setup

Prereqs: [`uv`](https://docs.astral.sh/uv/), `git`, and (only for live agent
runs) an authenticated `claude` CLI. Every component is its own uv project —
there is no root virtualenv to set up.

```bash
# lint (matches CI)
uvx ruff check .

# component test suites (all runnable from the repo root)
uv run --project scaffold/builder --extra dev pytest scaffold/builder/tests
uv run --project bridge --extra dev pytest bridge/tests
uv run --project console --extra dev pytest console/tests

# console tests need a built instance runtime first:
( cd instances/acme-checkout-sre && ../../scaffold/de build . && git checkout -- . )
```

## Pull requests

- Keep PRs scoped to one component where possible (one writer per directory
  is the repo discipline).
- CI must be green: `repo-ci` (lint, leak-check, builder/bridge/console
  suites, build determinism) always runs; `skills-ci` runs when
  `skills/skills/**` changes.
- Skill changes follow the release pipeline in `skills/README.md`: version
  bump in `SKILL.md` + `CHANGELOG.md` entry → gates → tag. Never re-tag a
  released version.

## Reporting security issues

See [SECURITY.md](SECURITY.md) — please do not open public issues for
vulnerabilities.
