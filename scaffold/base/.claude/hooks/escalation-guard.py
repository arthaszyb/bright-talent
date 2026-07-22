#!/usr/bin/env python3
"""
escalation-guard.py — PreToolUse and PostToolUse hook
Circuit breaker against repeated failing or identical tool calls.
Backed by escalation.guard.* config and work/.escalations/guard_state.json.
"""

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

# Resolve project directory
project_dir = os.getenv('DE_AGENT_PROJECT_DIR') or os.getenv('CLAUDE_PROJECT_DIR') or '.'

# Guard configuration (from environment; defaults from spec)
MAX_TOOL_FAILURES = int(os.getenv('DE_GUARD_MAX_TOOL_FAILURES', '3'))
MAX_REPEATED_ATTEMPTS = int(os.getenv('DE_GUARD_MAX_REPEATED_ATTEMPTS', '3'))
ESCALATION_ENABLED = os.getenv('DE_ESCALATION_ENABLED', 'true').lower() == 'true'

# Paths
work_dir = os.path.join(project_dir, 'work')
escalations_dir = os.path.join(work_dir, '.escalations')
guard_state_file = os.path.join(escalations_dir, 'guard_state.json')
events_file = os.path.join(escalations_dir, 'events.jsonl')

def ensure_dirs():
    """Ensure escalations directory exists."""
    try:
        os.makedirs(escalations_dir, exist_ok=True)
    except Exception:
        pass

def load_guard_state():
    """Load guard state from JSON file."""
    if not os.path.exists(guard_state_file):
        return {"fingerprints": {}, "last_fingerprint": "", "last_repeat_count": 0}
    try:
        with open(guard_state_file, 'r') as f:
            return json.load(f)
    except Exception:
        return {"fingerprints": {}, "last_fingerprint": "", "last_repeat_count": 0}

def save_guard_state(state):
    """Save guard state to JSON file."""
    ensure_dirs()
    try:
        with open(guard_state_file, 'w') as f:
            json.dump(state, f)
    except Exception:
        pass

def compute_fingerprint(tool_name, tool_input):
    """Compute SHA256 fingerprint of tool call."""
    # Normalize tool_input to JSON string with sorted keys
    if isinstance(tool_input, dict):
        normalized = json.dumps(tool_input, sort_keys=True, separators=(',', ':'))
    else:
        normalized = str(tool_input)

    # Collapse whitespace
    normalized = re.sub(r'\s+', ' ', normalized).strip()

    fp_input = f"{tool_name}:{normalized}"
    return hashlib.sha256(fp_input.encode()).hexdigest()[:16]

def sanitize_output(output_text, max_len=1000):
    """Sanitize output: truncate and remove sensitive patterns."""
    if not output_text:
        return ""

    # Truncate to max_len
    sanitized = output_text[:max_len]

    # Remove credential patterns (same as result-sanitizer)
    credential_patterns = [
        r'sk-ant-[A-Za-z0-9_-]{20,}',
        r'sk-[A-Za-z0-9]{20,}',
        r'ghp_[A-Za-z0-9]{36}',
        r'glpat-[A-Za-z0-9_-]{20,}',
        r'AKIA[0-9A-Z]{16}',
    ]
    for pattern in credential_patterns:
        sanitized = re.sub(pattern, '[REDACTED]', sanitized, flags=re.IGNORECASE)

    # Redact password/secret/token values
    sanitized = re.sub(r'(password|secret|token)[:=]\s*\S+', r'\1=[REDACTED]', sanitized, flags=re.IGNORECASE)

    return sanitized

def create_escalation_event(category, summary, trigger_condition, evidence, risk, recommended_next_step, missing_evidence=""):
    """Create and append an escalation event to events.jsonl."""
    ensure_dirs()

    # Generate event ID: esc-<UTC yyyymmdd>-<UTC HHMMSS>-<6 hex chars>
    now = datetime.now(timezone.utc)
    date_str = now.strftime('%Y%m%d')
    time_str = now.strftime('%H%M%S')
    rand_hex = os.urandom(3).hex()
    event_id = f"esc-{date_str}-{time_str}-{rand_hex}"

    # now is UTC-aware, so isoformat() ends with "+00:00"; normalize to a
    # single trailing 'Z' (never both an offset AND 'Z').
    ts = now.isoformat().replace('+00:00', 'Z')

    # Create event record
    event = {
        "event_id": event_id,
        "ts": ts,
        "instance_id": os.getenv('DE_INSTANCE_ID', 'unknown'),
        "session_id": os.getenv('SESSION_ID', ''),
        "category": category,
        "summary": summary,
        "trigger_condition": trigger_condition,
        "evidence": evidence,
        "missing_evidence": missing_evidence,
        "risk": risk,
        "recommended_next_step": recommended_next_step,
        "mentors": os.getenv('DE_MENTORS', 'mentor-one@acme.example').split(','),
        "dedup_key": "",
        "deduped": False
    }

    # Append to events.jsonl
    try:
        with open(events_file, 'a') as f:
            f.write(json.dumps(event) + '\n')
    except Exception:
        pass

    return event_id

try:
    hook_input = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError, EOFError):
    sys.exit(0)

if not ESCALATION_ENABLED:
    sys.exit(0)

tool_name = hook_input.get('tool_name', '')
tool_input = hook_input.get('tool_input', {})
hook_event_name = hook_input.get('hook_event_name', '')

if not tool_name:
    sys.exit(0)

# Compute fingerprint
fingerprint = compute_fingerprint(tool_name, tool_input)

# Load guard state
state = load_guard_state()

# PreToolUse handling
if hook_event_name == 'PreToolUse':
    fp_entry = state.get('fingerprints', {}).get(fingerprint, {})
    if fp_entry.get('escalated', False):
        # This call already escalated — deny it
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "This exact tool call has already been escalated. "
                    "Please call the escalate tool and surface its chat_message before retrying."
                )
            }
        }
        print(json.dumps(output))
    sys.exit(0)

# PostToolUse handling
if hook_event_name == 'PostToolUse':
    # Extract output
    output_text = (
        hook_input.get('tool_output') or
        hook_input.get('tool_response') or
        hook_input.get('tool_result') or
        hook_input.get('result') or
        hook_input.get('stderr') or
        hook_input.get('stdout') or
        ""
    )

    # tool_response is often a structured object; coerce so the failure-keyword
    # scan (and .lower()) never crashes the circuit breaker on non-string output.
    if not isinstance(output_text, str):
        try:
            output_text = json.dumps(output_text, default=str)
        except (TypeError, ValueError):
            output_text = str(output_text)

    is_error = hook_input.get('is_error', False)

    # Classify as failure
    failure_keywords = [
        'permission denied', 'unauthorized', 'forbidden', 'auth failed',
        'authentication', 'not found', 'no such', 'timeout', 'timed out',
        'connection refused', 'network is unreachable', 'could not resolve',
        'scope', 'policy', 'blocked'
    ]

    is_failure = is_error or any(kw in output_text.lower() for kw in failure_keywords)

    # Track repetition
    last_fp = state.get('last_fingerprint', '')
    last_repeat_count = state.get('last_repeat_count', 0)

    if last_fp == fingerprint:
        repeat_count = last_repeat_count + 1
    else:
        repeat_count = 1

    state['last_fingerprint'] = fingerprint
    state['last_repeat_count'] = repeat_count

    # Track failures
    if fingerprint not in state['fingerprints']:
        state['fingerprints'][fingerprint] = {"failures": 0, "escalated": False}

    if is_failure:
        state['fingerprints'][fingerprint]['failures'] += 1

    # Check escalation triggers
    failure_count = state['fingerprints'][fingerprint]['failures']
    should_escalate = (is_failure and failure_count >= MAX_TOOL_FAILURES) or (repeat_count >= MAX_REPEATED_ATTEMPTS)

    if should_escalate and not state['fingerprints'][fingerprint]['escalated']:
        state['fingerprints'][fingerprint]['escalated'] = True

        # Determine category
        if any(kw in output_text.lower() for kw in ['scope', 'policy', 'blocked']):
            category = 'unknown_risk'
        elif is_failure:
            category = 'capability_gap'
        else:
            category = 'uncertain_conclusion'

        # Sanitize evidence
        evidence = sanitize_output(output_text, 1000)

        # Create event
        summary = f"Tool '{tool_name}' requires escalation after {failure_count if is_failure else repeat_count} attempts"
        trigger = f"{'3rd+ failure' if is_failure else 'repeated calls without new evidence'}"
        risk = "Model may loop or make incorrect assumptions without clarification"
        next_step = f"Review the tool output and provide guidance on how to proceed with '{tool_name}'"

        event_id = create_escalation_event(
            category, summary, trigger,
            evidence, risk, next_step
        )

        # Emit message instructing model to surface chat_message
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "message": f"[escalation {event_id}] {summary} — @mentor-one@acme.example please review: {next_step}"
            }
        }
        print(json.dumps(output))

    # Save state
    save_guard_state(state)

sys.exit(0)
