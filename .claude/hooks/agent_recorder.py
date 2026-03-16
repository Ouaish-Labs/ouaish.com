#!/usr/bin/env python3
"""
Claude Code PostToolUse Hook: Record Agent dispatches and key Bash events.

Automatically tracks every Agent tool call — subagent_type, model, agent_id,
timestamp — to .session/agents.json. Also records pytest runs, gh api calls,
and gh pr create/comment to .session/events.json.

The workflow_gate.py PreToolUse hook reads these files to verify that required
phases (Phase 0 architect, Phase C½ review agents) actually ran.

The model cannot fake this record. Only a real Agent dispatch triggers
PostToolUse, so only real dispatches appear in agents.json.

Exit codes:
- 0: Always (PostToolUse hooks should not block)
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

SESSION_DIR = Path(".session")
AGENTS_FILE = SESSION_DIR / "agents.json"
EVENTS_FILE = SESSION_DIR / "events.json"
DEBUG_LOG = Path(__file__).parent / "hook_debug.log"


def log_debug(message: str):
    try:
        with open(DEBUG_LOG, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] agent_recorder: {message}\n")
    except Exception:
        pass


def ensure_session_dir():
    """Create .session/ if it doesn't exist."""
    SESSION_DIR.mkdir(exist_ok=True)


def append_json(filepath: Path, entry: dict):
    """Append an entry to a JSON array file."""
    ensure_session_dir()
    entries = []
    if filepath.exists():
        try:
            entries = json.loads(filepath.read_text())
        except (json.JSONDecodeError, Exception):
            entries = []
    entries.append(entry)
    filepath.write_text(json.dumps(entries, indent=2))


def record_agent(input_data: dict):
    """Record an Agent dispatch."""
    tool_input = input_data.get("tool_input", {})
    tool_response = input_data.get("tool_response", {})

    # Extract agent ID from response — format varies
    agent_id = None
    if isinstance(tool_response, dict):
        agent_id = tool_response.get("agent_id") or tool_response.get("agentId")
    elif isinstance(tool_response, str):
        match = re.search(r"agentId:\s*(\S+)", tool_response)
        if match:
            agent_id = match.group(1)

    entry = {
        "type": "agent_dispatch",
        "subagent_type": tool_input.get("subagent_type", "general-purpose"),
        "model": tool_input.get("model"),
        "description": tool_input.get("description", ""),
        "agent_id": agent_id,
        "timestamp": datetime.utcnow().isoformat(),
    }

    append_json(AGENTS_FILE, entry)
    log_debug(f"Recorded agent: {entry['subagent_type']} (id: {agent_id})")


def record_bash_event(input_data: dict):
    """Record interesting Bash events (pytest, gh api, gh pr)."""
    tool_input = input_data.get("tool_input", {})
    tool_response = input_data.get("tool_response", {})
    command = tool_input.get("command", "")

    stdout = ""
    exit_code = None
    if isinstance(tool_response, dict):
        stdout = tool_response.get("stdout", "")
        exit_code = tool_response.get("exit_code") or tool_response.get("exitCode")
    elif isinstance(tool_response, str):
        stdout = tool_response

    event = None

    # pytest run
    if re.search(r"\bpytest\b", command):
        has_passed = re.search(r"(\d+)\s+passed", stdout)
        has_failed = re.search(r"(\d+)\s+failed", stdout)
        event = {
            "type": "pytest",
            "passed": int(has_passed.group(1)) if has_passed else 0,
            "failed": int(has_failed.group(1)) if has_failed else 0,
            "exit_code": exit_code,
        }

    # gh api comments check
    elif re.search(r"gh\s+api\s+.*pulls.*comments", command):
        event = {
            "type": "external_review_check",
            "command": command[:200],
            "response_length": len(stdout),
        }

    # gh pr create
    elif re.search(r"\bgh\s+pr\s+create\b", command):
        pr_url = ""
        for line in stdout.splitlines():
            if "github.com" in line and "/pull/" in line:
                pr_url = line.strip()
                break
        event = {
            "type": "pr_created",
            "pr_url": pr_url,
        }

    # gh pr comment with Final Summary
    elif re.search(r"\bgh\s+pr\s+comment\b", command) and "Final Summary" in command:
        event = {
            "type": "final_summary_posted",
        }

    if event:
        event["timestamp"] = datetime.utcnow().isoformat()
        event["command_preview"] = command[:100]
        append_json(EVENTS_FILE, event)
        log_debug(f"Recorded event: {event['type']}")


def main():
    try:
        raw_input = sys.stdin.read()
        input_data = json.loads(raw_input)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")

    if tool_name == "Agent":
        record_agent(input_data)
    elif tool_name == "Bash":
        record_bash_event(input_data)

    sys.exit(0)


if __name__ == "__main__":
    main()
