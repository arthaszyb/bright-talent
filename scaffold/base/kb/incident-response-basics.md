# Incident Response Basics

Foundational principles for responding to production incidents at Acme Corp.

## What is an incident?

An incident is any unplanned disruption to service for end-users: a deployment that breaks checkout, a cache cluster that stops serving, a data pipeline that runs late, or an on-call alert that fires without a clear root cause.

## Detection

Incidents are typically discovered through:
- **Automated alerts** from monitoring systems (Acme platform observability stack)
- **User reports** via support or chat
- **Regular checks** of dashboard metrics during shifts

When you see an alert or report, assume it is real until proven otherwise. Escalate if you are uncertain whether a situation qualifies as an incident — mentors make the call.

## Initial response (first 5 minutes)

1. **Confirm the symptom.** Read the alert message, check the dashboard metric the alert tracks, and verify it with a recent query if the dashboard seems stale (e.g., a cache-hit ratio drop, a latency spike, error-rate increase).
2. **Assess scope.** Which service(s) are affected? Is it just one region, one version, or fleet-wide? How many users?
3. **Communicate.** Post a summary in the incident channel so the team knows what's happening. Include: symptom, affected scope, alert time, current status.
4. **Page on-call.** If the incident is **customer-facing** and **ongoing**, page the primary on-call engineer (mentors).

## Mitigation (first 15 minutes)

Mitigations are *safe, fast* actions to restore service while the root cause is still unknown:

- **Restart** a service if logs show it is in a bad state (high latency to internal dependencies, memory leak, stuck connection pool).
- **Revert** a recent deployment if the incident correlates with a deploy time and the deployment touched the affected code path.
- **Scale up** a cache cluster if the cache-hit ratio is dropping (do NOT scale down during an incident).
- **Failover** to another region or provider if available (requires a pre-staged runbook and on-call approval).
- **Degrade gracefully**: disable non-critical features to reduce load on the affected system (e.g., turn off recommendations if the recs service is slow).

Never attempt a mitigation you are unfamiliar with — ask a mentor or escalate.

## Investigation (ongoing)

While mitigating, start investigating root cause:

- Check **logs** from the affected service for errors, exception patterns, or unusual behavior in the window around the alert time.
- Check **metrics** (CPU, memory, disk, requests/sec) for anomalies or patterns that correlate with the incident time.
- Check **recent changes**: deployments, config changes, data migrations, traffic campaigns scheduled during the incident window.
- Check **dependencies**: does the affected service call an external API, database, or cache? Did one of those fail?

Document your findings in the incident postmortem stub (see kb/team/incidents/).

## Escalation and handoff

Escalate to a mentor if:
- You have not identified a mitigation after 10 minutes.
- The incident is ongoing and you need a decision on impact/severity.
- Multiple teams are involved and you need to coordinate a response.
- A mitigation requires a change to production configuration you do not have permission for.

## Non-goals

This guide does **not** cover: post-incident review/RCA process, on-call rotation, severity definitions, escalation thresholds (those are team-specific; ask your mentors).
