#!/usr/bin/env python3
"""
Claude Code PreToolUse Hook: Workflow gate — blocks commit/PR if required phases missing.

Reads .session/manifest.json (created by session_init.sh) and
.session/agents.json + .session/events.json (written by agent_recorder.py).

Blocks:
- git commit: if Phase 0 architect was not dispatched
- gh pr comment "Final Summary": if review agents not dispatched or
  external review not checked

Does NOT fire if .session/manifest.json doesn't exist (non-workflow commits).

Exit codes:
- 0: Allow the command
- 2: Block the command (with error message on stderr)
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

SESSION_DIR = Path(".session")
MANIFEST_FILE = SESSION_DIR / "manifest.json"
AGENTS_FILE = SESSION_DIR / "agents.json"
EVENTS_FILE = SESSION_DIR / "events.json"
DEBUG_LOG = Path(__file__).parent / "hook_debug.log"


def log_debug(message: str):
    try:
        with open(DEBUG_LOG, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] workflow_gate: {message}\n")
    except Exception:
        pass


def load_json(filepath: Path):
    if not filepath.exists():
        return [] if "agents" in filepath.name or "events" in filepath.name else {}
    try:
        return json.loads(filepath.read_text())
    except (json.JSONDecodeError, Exception):
        return [] if "agents" in filepath.name or "events" in filepath.name else {}


def check_required_agents(manifest: dict, agents: list, required_phases: list) -> list:
    """Check if required agent types were dispatched. Returns list of missing phases."""
    missing = []
    required_agent_defs = manifest.get("required_agents", [])

    for phase_name in required_phases:
        req = next((r for r in required_agent_defs if r["phase"] == phase_name), None)
        if not req:
            continue

        pattern = req["subagent_type_pattern"]
        found = any(re.match(pattern, a.get("subagent_type", "")) for a in agents)
        if not found:
            missing.append(
                {
                    "phase": phase_name,
                    "expected": pattern,
                    "description": req.get("description", ""),
                }
            )

    return missing


def check_required_events(manifest: dict, events: list, required_event_keys: list) -> list:
    """Check if required events occurred. Returns list of missing events."""
    missing = []
    required_event_defs = manifest.get("required_events", [])

    for event_key in required_event_keys:
        parts = event_key.split(":")
        if len(parts) != 2:
            continue
        phase_name, event_type = parts

        req = next(
            (r for r in required_event_defs if r["phase"] == phase_name and r["event_type"] == event_type),
            None,
        )
        if not req:
            continue

        found = any(e.get("type") == event_type for e in events)
        if not found:
            missing.append(
                {
                    "phase": phase_name,
                    "event_type": event_type,
                    "description": req.get("description", ""),
                }
            )

    return missing


def check_gate(gate_name: str, manifest: dict, agents: list, events: list):
    """Check a specific gate. Returns error message if blocked, None if passed."""
    gates = manifest.get("gates", {})
    gate = gates.get(gate_name)
    if not gate:
        return None

    errors = []

    required_agents = gate.get("require_agents", [])
    missing_agents = check_required_agents(manifest, agents, required_agents)
    for m in missing_agents:
        errors.append(f"  - {m['phase']}: {m['description']} (expected: {m['expected']})")

    required_events = gate.get("require_events", [])
    missing_events = check_required_events(manifest, events, required_event_keys=required_events)
    for m in missing_events:
        errors.append(f"  - {m['phase']}:{m['event_type']}: {m['description']}")

    if errors:
        return "\n".join(errors)
    return None


def main():
    try:
        raw_input = sys.stdin.read()
        input_data = json.loads(raw_input)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")

    if tool_name != "Bash":
        sys.exit(0)

    # Only enforce if a session manifest exists
    if not MANIFEST_FILE.exists():
        sys.exit(0)

    manifest = load_json(MANIFEST_FILE)
    agents = load_json(AGENTS_FILE)
    events = load_json(EVENTS_FILE)

    # Gate: git commit
    if re.search(r"\bgit\s+commit\b", command):
        errors = check_gate("git_commit", manifest, agents, events)
        if errors:
            log_debug(f"Blocked git commit — missing:\n{errors}")
            print(
                f"Workflow gate: cannot commit — required phases not completed.\n"
                f"\n"
                f"Missing:\n{errors}\n"
                f"\n"
                f"The session recorder (.session/agents.json) shows these phases were\n"
                f"not executed. Run the missing phases before committing.\n"
                f"\n"
                f"Session data: {SESSION_DIR}/",
                file=sys.stderr,
            )
            sys.exit(2)

    # Gate: gh pr comment with Final Summary
    if re.search(r"\bgh\s+pr\s+comment\b", command) and "Final Summary" in command:
        errors = check_gate("final_summary", manifest, agents, events)
        if errors:
            log_debug(f"Blocked Final Summary — missing:\n{errors}")
            print(
                f"Workflow gate: cannot post Final Summary — required phases not completed.\n"
                f"\n"
                f"Missing:\n{errors}\n"
                f"\n"
                f"The session recorder (.session/) shows these phases were not executed.\n"
                f"Run the missing phases before posting the Final Summary.\n"
                f"\n"
                f"To check external reviews:\n"
                f"  gh api repos/{{owner}}/{{repo}}/pulls/{{number}}/comments --jq 'length'",
                file=sys.stderr,
            )
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
