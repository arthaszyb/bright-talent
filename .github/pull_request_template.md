## What & why

<!-- One or two sentences. Link the issue if there is one. -->

## Component(s) touched

<!-- scaffold/builder | de CLI | bridge | console | eval | skills | mocks | docs -->

## Checklist

- [ ] `uvx ruff check .` passes
- [ ] `bash scripts/leak-check.sh .` is clean (fictional universe intact)
- [ ] Affected component test suites pass locally
- [ ] No hand-edits to compiled artifacts (`instances/*/runtime/`, `editor/`);
      build metadata re-committed if scaffold/base or templates changed
- [ ] Skill changes: version bump + CHANGELOG entry (release pipeline in `skills/README.md`)
