#!/usr/bin/env python3
"""
de-agent-escalate.py — MCP server (stdio JSON-RPC)
Exposes the escalate tool for agent-initiated escalations.
Implements initialize, tools/list, tools/call per MCP spec.
"""

import json
import os
import sys

# Import the shared library from the same directory
sys.path.insert(0, os.path.dirname(__file__))
from de_agent_escalate_lib import create_escalation


def send_response(response: dict) -> None:
    """Send a JSON-RPC response on stdout."""
    print(json.dumps(response))
    sys.stdout.flush()


def handle_initialize(request_id: int, params: dict) -> None:
    """Handle initialize request."""
    response = {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "protocolVersion": "2024-11",
            "capabilities": {},
            "serverInfo": {
                "name": "de-agent-escalate",
                "version": "0.1.0"
            }
        }
    }
    send_response(response)


def handle_tools_list(request_id: int) -> None:
    """Handle tools/list request."""
    response = {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "tools": [
                {
                    "name": "escalate",
                    "description": "Escalate a task to mentors for review and decision",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "category": {
                                "type": "string",
                                "enum": [
                                    "capability_gap",
                                    "unknown_risk",
                                    "uncertain_conclusion",
                                    "missing_approval",
                                    "forced_bypass"
                                ],
                                "description": "Escalation category"
                            },
                            "summary": {
                                "type": "string",
                                "description": "One-sentence summary of what is being escalated"
                            },
                            "trigger_condition": {
                                "type": "string",
                                "description": "What triggered this escalation (e.g., 3rd failure)"
                            },
                            "evidence": {
                                "type": "string",
                                "description": "Sanitized supporting output (<=1000 chars)"
                            },
                            "missing_evidence": {
                                "type": "string",
                                "description": "What could not be verified (optional)"
                            },
                            "risk": {
                                "type": "string",
                                "description": "What could go wrong if guessed instead of escalating"
                            },
                            "recommended_next_step": {
                                "type": "string",
                                "description": "The concrete ask to the mentor"
                            }
                        },
                        "required": [
                            "category",
                            "summary",
                            "trigger_condition",
                            "evidence",
                            "risk",
                            "recommended_next_step"
                        ]
                    }
                }
            ]
        }
    }
    send_response(response)


def handle_tools_call(request_id: int, params: dict) -> None:
    """Handle tools/call (escalate tool invocation)."""
    tool_name = params.get("name", "")
    tool_input = params.get("arguments", {})

    if tool_name != "escalate":
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32601,
                "message": f"Unknown tool: {tool_name}"
            }
        }
        send_response(response)
        return

    # Extract parameters
    category = tool_input.get("category", "unknown_risk")
    summary = tool_input.get("summary", "Escalation required")
    trigger_condition = tool_input.get("trigger_condition", "")
    evidence = tool_input.get("evidence", "")
    missing_evidence = tool_input.get("missing_evidence", "")
    risk = tool_input.get("risk", "Proceeding without escalation may cause issues")
    recommended_next_step = tool_input.get("recommended_next_step", "Please review and advise")

    # Create escalation via shared library
    result = create_escalation(
        category=category,
        summary=summary,
        trigger_condition=trigger_condition,
        evidence=evidence,
        risk=risk,
        recommended_next_step=recommended_next_step,
        missing_evidence=missing_evidence
    )

    response = {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "type": "text",
            "text": json.dumps(result)
        }
    }
    send_response(response)


def main() -> None:
    """Main event loop: read JSON-RPC requests from stdin, send responses on stdout."""
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break

            request = json.loads(line.strip())
        except (json.JSONDecodeError, EOFError):
            # Skip malformed lines
            continue
        except Exception:
            break

        request_id = request.get("id", 0)
        method = request.get("method", "")

        if method == "initialize":
            handle_initialize(request_id, request.get("params", {}))
        elif method == "tools/list":
            handle_tools_list(request_id)
        elif method == "tools/call":
            handle_tools_call(request_id, request.get("params", {}))
        else:
            # Unknown method
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"Unknown method: {method}"
                }
            }
            send_response(response)


if __name__ == "__main__":
    main()
