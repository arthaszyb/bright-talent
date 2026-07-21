# Security Policy

## Scope

This repository is a **reference implementation / demo** of a Digital
Employee platform. It ships no production credentials and operates entirely
in a fictional universe (Acme Corp). Even so, its security posture is the
point of the project — reports about weaknesses in the guardrail model are
very welcome.

Particularly interesting areas:

- the scaffold security floor: hooks under `scaffold/base/.claude/hooks/`,
  policy packs, and the merge invariants in `scaffold/builder/builder/merge.py`
- prompt-injection or escalation paths that slip past the seeded guardrail
  tests (`scaffold/instance-test-seeds/`) or the eval safety gate
- the bridge's webhook authentication and session isolation
- anything that lets an instance shadow base files, loosen permissions, or
  write outside the mock Change Gateway

## Reporting a vulnerability

Please use **GitHub private vulnerability reporting** (Security tab →
"Report a vulnerability") rather than a public issue. Include a minimal
reproduction — a failing guardrail test case (`*.mock.yaml`) is the ideal
format.

You should get an initial response within a week. Demo or not, confirmed
guardrail bypasses will be fixed and added to the seeded test set so they
stay fixed.

## Known, documented simplifications

The demo intentionally simplifies some production controls (secret storage,
transcript shipping, markup stripping in the bridge, and others). These are
tracked honestly in `DESIGN.md` §4 (deviation register) and the governance
checklist in `README.md` — check there before reporting them as findings.
