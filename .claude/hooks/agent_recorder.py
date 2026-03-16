#!/usr/bin/env python3
"""
Claude Code PostToolUse Hook: Record Agent dispatches to .session/agents.json.

Automatically tracks every Agent tool call — subagent_type, model, agent_id,
timestamp. The workflow_gate.py PreToolUse hook reads this file to verify
that required phases (Phase 0 architect, Phase C½ review agents) actually ran.

The model cannot fake this record. Only a real Agent dispatch triggers
PostToolUse, so only real dispatches appear in agents.json.

Also records Bash events: pytest runs, gh api calls, gh pr create/comment.

Worktree-aware: resolves .session/ from the command's cd prefix or the
agent prompt's Working directory reference, so each worktree gets its own
session data.

Exit codes:
- 0: Always (PostToolUse hooks should not block)
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

DEBUG_LOG = Path(__file__).parent / "hook_debug.log"


def log_debug(message: str):
    try:
        with open(DEBUG_LOG, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] agent_recorder: {message}\n")
    except Exception:
        pass


def resolve_session_dir(input_data: dict) -> Path:
    """Determine the correct .session/ directory for this tool call.

    Hooks always run from the main repo CWD, but the agent/command may target
    a worktree. We check in order:
    1. Parse 'cd <path>' prefix from Bash commands
    2. Check the agent prompt for 'cd <path>' or 'Working directory: <path>'
    3. Check the 'cwd' field in the hook input (if Claude Code provides it)
    4. Fall back to CWD (main repo)
    """
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # For Bash: extract cd target from command
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        cd_match = re.match(r"cd\s+(~?/[^\s;&|]+)", command)
        if cd_match:
            cd_path = Path(cd_match.group(1)).expanduser()
            if cd_path.is_dir() and (cd_path / ".session").is_dir():
                return cd_path / ".session"

    # For Agent: check the prompt for worktree path
    if tool_name == "Agent":
        prompt = tool_input.get("prompt", "")
        wt_match = re.search(r"(?:Working directory|cd)\s*:?\s*(~/Developer/[^\s.]+)", prompt)
        if wt_match:
            wt_path = Path(wt_match.group(1)).expanduser()
            if wt_path.is_dir() and (wt_path / ".session").is_dir():
                return wt_path / ".session"

    # Check 'cwd' field (may be provided by Claude Code)
    cwd = input_data.get("cwd", "")
    if cwd:
        cwd_path = Path(cwd)
        if (cwd_path / ".session").is_dir():
            return cwd_path / ".session"

    # Fall back to current working directory
    return Path(".session")


def ensure_session_dir(session_dir: Path):
    """Create .session/ if it doesn't exist."""
    session_dir.mkdir(exist_ok=True)


def append_json(filepath: Path, entry: dict):
    """Append an entry to a JSON array file."""
    ensure_session_dir(filepath.parent)
    entries = []
    if filepath.exists():
        try:
            entries = json.loads(filepath.read_text())
        except (json.JSONDecodeError, Exception):
            entries = []
    entries.append(entry)
    filepath.write_text(json.dumps(entries, indent=2))


def record_agent(input_data: dict, session_dir: Path):
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

    agents_file = session_dir / "agents.json"
    append_json(agents_file, entry)
    log_debug(f"Recorded agent: {entry['subagent_type']} (id: {agent_id}) -> {session_dir}")


def record_bash_event(input_data: dict, session_dir: Path):
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

    # gh pr comment with round findings (Automated Review — Round N)
    elif re.search(r"\bgh\s+pr\s+comment\b", command) and re.search(r"Automated Review.*Round \d", command):
        event = {
            "type": "pr_comment_round",
        }

    # gh pr comment with Final Summary
    elif re.search(r"\bgh\s+pr\s+comment\b", command) and "Final Summary" in command:
        event = {
            "type": "final_summary_posted",
        }

    if event:
        event["timestamp"] = datetime.utcnow().isoformat()
        event["command_preview"] = command[:100]
        events_file = session_dir / "events.json"
        append_json(events_file, event)
        log_debug(f"Recorded event: {event['type']} -> {session_dir}")


def main():
    try:
        raw_input = sys.stdin.read()
        input_data = json.loads(raw_input)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    session_dir = resolve_session_dir(input_data)

    if tool_name == "Agent":
        record_agent(input_data, session_dir)
    elif tool_name == "Bash":
        record_bash_event(input_data, session_dir)

    sys.exit(0)


if __name__ == "__main__":
    main()
