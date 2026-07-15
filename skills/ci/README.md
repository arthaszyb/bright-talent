# skills/ci — release gate scripts

Run from the repo root (`de-demo/`). Same scripts back `.github/workflows/skills-ci.yml`.

```bash
# lint: frontmatter schema, no-bare-Bash, required tests/, coverage table
uv run --project skills/ci python skills/ci/lint.py skills/skills/ticket-review

# version-check: strict semver, > latest git tag, CHANGELOG.md heading
uv run --project skills/ci python skills/ci/version_check.py skills/skills/ticket-review

# detect-release: did every changed skill bump its version in this range?
uv run --project skills/ci python skills/ci/detect_release.py --base HEAD~1 --head HEAD

# triggers / safety / e2e are not in this dir — they shell out to `de-eval`
# (built in M4): uv run --project ../eval de-eval <gate> skills/<name>
```

All scripts exit 0 clean / 1 on violation (each violation printed).
