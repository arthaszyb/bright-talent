# Changelog — access-review

All notable changes to the `access-review` skill. Versions are the skill's
`SKILL.md` `version:`; releases are git tags `access-review/v<version>`.

## 0.1.0

- Initial release. Reviews a service access-grant request against the Acme
  least-privilege access policy and renders a comment-only Markdown review.
  Three illustrative rules: requested role must be in the service's catalog;
  production grants must cite a ticket and be time-boxed (≤ 90 days); a
  privileged role on a PII-classified service in production requires manager
  approval. Never grants, approves, or revokes — the decision stays with a
  human approver.
