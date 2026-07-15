# Changelog — ticket-review

## 0.1.0

- Initial release: review cache-cluster scaling change tickets against the
  cache-scaling SOP (`kb/team/runbooks/cache-scaling-sop.md`).
- Four-step scripted pipeline (fetch_ticket → fetch_metrics → analyze →
  render_comment) plus a bundled stdlib-only mock Change Gateway
  (`scripts/mock_server.py`, port 8801, seeded tickets 1001/1002/1003).
- Full test suite: 9 trigger cases, 6 safety cases, 2 command-replay e2e cases,
  coverage table in `tests/test-cases.md`.
- Comment-only by design: no approve/reject capability.
