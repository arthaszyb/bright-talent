# How to Use the Knowledge Base

The DE's knowledge base is a searchable, structured collection of runbooks, SOPs, incident postmortems, and foundational principles. This page explains how the agent searches it.

## The KB directory structure

```
runtime/kb/
  foundations/             # Generic SRE principles (this folder)
  team/                    # Team-specific runbooks, runbooks, incidents
  wiki/ (optional)         # External wiki refs, if configured
  index.md                 # Generated master index (points into the above)
```

The agent has access to this entire tree at runtime and can read any file. The search strategy is grep-based, not vector-based.

## How the agent finds knowledge

When faced with a question about operations (e.g., "how do I scale the cache cluster?"), the agent:

1. **Grep for keywords** in the KB tree. For the example above: `grep -r "scale" kb/` to find all pages mentioning scaling.
2. **Read the matched files** to understand context and validate the match (is this page about *cache* scaling, or about scaling something else?).
3. **Extract and cite the relevant section** (e.g., `kb/team/runbooks/cache-scaling-sop.md#Rules`).
4. **Follow cross-references** if a page points to another page (the agent can grep again to dig deeper).

This is intentionally manual — the agent reasons about what to search for, reads whole files to preserve structure, and can iterate if the first search doesn't answer the question.

## Best practices for KB authoring

**For operations:** write for section-level citation. Every SOP/runbook should have clear, stable headers (`## Thresholds`, `## Escalation`, `## Rollback steps`) so the DE can point to `kb/team/runbooks/foo.md#thresholds` rather than a vague "somewhere in the runbook."

**For skills:** if a skill enforces a rule or SOP, the skill's documentation should cite the exact KB page and section it is enforcing. This way, when the DE applies the rule, a human auditor can go read the rule directly, not just trust the agent's paraphrase.

**Keep it curated:** the KB is not a general-purpose corpus — it is a team's accumulated, reviewed ops documentation. If it grows beyond a few hundred pages, grep search degrades in precision and latency; at that point, consider a different retrieval strategy (outside the scope of this platform).

## What the agent does NOT do

- The agent does **not** automatically ingest every page it reads. It reads and recalls only what is relevant to the current question.
- The agent does **not** synthesize information across pages — it cites sources, not original synthesis (model-level reasoning is where synthesis happens).
- The agent does **not** update the KB in response to operational findings. Corrections become PRs against the wiki, reviewed like any other doc change.
- The agent does **not** rely on the KB for critical safety thresholds — those are embedded in skill logic (enforced code, not just documentation).

## When to escalate instead of grep

Escalate to a mentor if:
- The KB doesn't cover a situation (the runbook is stale or missing).
- Two different KB sections give conflicting guidance.
- The agent identifies a gap in the KB during an incident and needs a human decision.

This keeps the KB honest: if it gets out of sync with reality, operational failures will surface the drift.
