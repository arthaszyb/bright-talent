"""
de_agent_escalate_lib.py — Shared escalation library
Used by both the MCP server and the escalation-guard hook.
Creates and tracks escalation events in a canonical format.
"""

import json
import os
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def get_events_file() -> str:
    """Resolve the escalations events file path."""
    # Try DE_AGENT_PROJECT_DIR first
    project_dir = os.getenv('DE_AGENT_PROJECT_DIR')
    if project_dir:
        return os.path.join(project_dir, 'work', '.escalations', 'events.jsonl')

    # Fall back to CLAUDE_PROJECT_DIR
    project_dir = os.getenv('CLAUDE_PROJECT_DIR')
    if project_dir:
        return os.path.join(project_dir, 'work', '.escalations', 'events.jsonl')

    # If neither is set, use a relative path (from the tool directory)
    return './work/.escalations/events.jsonl'


def compute_dedup_key(category: str, summary: str) -> str:
    """Compute dedup key: sha256(category:normalized_summary)[:16]."""
    normalized = f"{category}:{summary.lower().strip()}"
    normalized = re.sub(r'\s+', ' ', normalized)
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def load_recent_events(window_seconds: int = 300) -> dict:
    """Load recent events for deduplication checking."""
    events_file = get_events_file()
    if not os.path.exists(events_file):
        return {}

    recent = {}
    now = datetime.now(timezone.utc)

    try:
        with open(events_file, 'r') as f:
            for line in f:
                try:
                    event = json.loads(line.strip())
                    event_time = datetime.fromisoformat(event.get('ts', '').replace('Z', '+00:00'))
                    age_seconds = (now - event_time).total_seconds()

                    if 0 <= age_seconds <= window_seconds:
                        dedup_key = event.get('dedup_key', '')
                        if dedup_key:
                            recent[dedup_key] = event
                except (json.JSONDecodeError, ValueError):
                    pass
    except Exception:
        pass

    return recent


def create_escalation(
    category: str,
    summary: str,
    trigger_condition: str,
    evidence: str,
    risk: str,
    recommended_next_step: str,
    missing_evidence: str = ""
) -> dict:
    """
    Create and append an escalation event to events.jsonl.
    Returns {event_id, deduped, chat_message}.
    """
    events_file = get_events_file()
    dedup_window = int(os.getenv('DE_ESCALATION_DEDUP_WINDOW', '300'))
    show_event_id = os.getenv('DE_ESCALATION_SHOW_EVENT_ID', 'true').lower() == 'true'

    # Ensure directories exist
    events_dir = os.path.dirname(events_file)
    try:
        os.makedirs(events_dir, exist_ok=True)
    except Exception:
        pass

    # Compute dedup key
    dedup_key = compute_dedup_key(category, summary)

    # Check for recent duplicates
    recent_events = load_recent_events(dedup_window)
    if dedup_key in recent_events:
        prior_event = recent_events[dedup_key]
        return {
            "event_id": prior_event.get('event_id', ''),
            "deduped": True,
            "chat_message": (
                f"[escalation already pending] {summary} — "
                "Mentors are already reviewing this issue. Awaiting response."
            )
        }

    # Generate new event ID
    now = datetime.now(timezone.utc)
    date_str = now.strftime('%Y%m%d')
    time_str = now.strftime('%H%M%S')
    rand_hex = os.urandom(3).hex()
    event_id = f"esc-{date_str}-{time_str}-{rand_hex}"

    ts = now.isoformat().replace('+00:00', 'Z')
    if not ts.endswith('Z'):
        ts += 'Z'

    # Create event record
    mentors = os.getenv('DE_MENTORS', 'mentor-one@acme.example').split(',')
    mentors = [m.strip() for m in mentors if m.strip()]

    event = {
        "event_id": event_id,
        "ts": ts,
        "instance_id": os.getenv('DE_INSTANCE_ID', 'unknown'),
        "session_id": os.getenv('SESSION_ID', os.getenv('CLAUDE_PROJECT_ID', '')),
        "category": category,
        "summary": summary,
        "trigger_condition": trigger_condition,
        "evidence": evidence,
        "missing_evidence": missing_evidence,
        "risk": risk,
        "recommended_next_step": recommended_next_step,
        "mentors": mentors,
        "dedup_key": dedup_key,
        "deduped": False
    }

    # Append to events.jsonl
    try:
        with open(events_file, 'a') as f:
            f.write(json.dumps(event) + '\n')
    except Exception:
        pass

    # Construct chat message
    if show_event_id:
        chat_message = f"[escalation {event_id}] {summary} — @{mentors[0] if mentors else 'mentor-one@acme.example'} please review: {recommended_next_step}"
    else:
        chat_message = f"{summary} — @{mentors[0] if mentors else 'mentor-one@acme.example'} please review: {recommended_next_step}"

    return {
        "event_id": event_id,
        "deduped": False,
        "chat_message": chat_message
    }
