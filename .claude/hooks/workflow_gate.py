#!/usr/bin/env python3
"""
Claude Code PreToolUse Hook: Workflow gate — blocks commit/PR if required phases missing.

Reads .session/manifest.json (created by session_init.sh) and
.session/agents.json + .session/events.json (written by agent_recorder.py).

Gates:
- git commit: blocks if Phase 0 architect was not dispatched or tests not run
- gh pr comment "Final Summary": blocks if review agents not dispatched or
  external review not checked
- gh pr merge: blocks if CI checks are failing or pending
- gh pr merge: blocks if run from feature worktree (must use main repo)
- git worktree add: blocks if target is inside the project (must use ~/Developer/)

Does NOT fire if .session/manifest.json doesn't exist (non-workflow commits).

Worktree-aware: resolves .session/ from the command's cd prefix so each
worktree's gates are independent.

Exit codes:
- 0: Allow the command
- 2: Block the command (with error message on stderr)
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

DEBUG_LOG = Path(__file__).parent / "hook_debug.log"


def resolve_session_dir_from_command(command: str) -> Path:
    """Extract the worktree path from a 'cd <path> &&' prefix in a Bash command.

    Hooks run from the main repo CWD, but git commit/gh pr comment commands
    target a worktree via 'cd ~/Developer/<name> && ...'. We need to find
    the .session/ directory in that worktree, not in the main repo.
    """
    cd_match = re.match(r"cd\s+(~?/[^\s;&|]+)", command)
    if cd_match:
        cd_path = Path(cd_match.group(1)).expanduser()
        session = cd_path / ".session"
        if session.is_dir():
            return session
    return Path(".session")


def log_debug(message: str):
    try:
        with open(DEBUG_LOG, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] workflow_gate: {message}\n")
    except Exception:
        pass


def load_json(filepath: Path) -> "list | dict":
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


def check_gate(gate_name: str, manifest: dict, agents: list, events: list) -> "str | None":
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

    # Resolve the correct .session/ directory from the command's cd prefix
    session_dir = resolve_session_dir_from_command(command)
    manifest_file = session_dir / "manifest.json"
    agents_file = session_dir / "agents.json"
    events_file = session_dir / "events.json"

    # Only enforce manifest-based gates if a session manifest exists
    if manifest_file.exists():
        manifest = load_json(manifest_file)
        agents = load_json(agents_file)
        events = load_json(events_file)

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
                    f"Session data: {session_dir}/",
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

    # Gate: gh pr merge — block if CI is not green (always active, no manifest needed)
    if re.search(r"\bgh\s+pr\s+merge\b", command):
        pr_ref_match = re.search(r"gh\s+pr\s+merge\s+(\S+)", command)
        pr_ref = pr_ref_match.group(1) if pr_ref_match else ""

        if pr_ref:
            try:
                import subprocess

                result = subprocess.run(
                    ["gh", "pr", "checks", pr_ref, "--json", "state,name"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode == 0:
                    checks = json.loads(result.stdout)
                    failing = [c for c in checks if c.get("state") not in ("SUCCESS", "SKIPPED", "NEUTRAL")]
                    pending = [c for c in checks if c.get("state") in ("PENDING", "IN_PROGRESS", "QUEUED")]

                    if failing and not pending:
                        names = ", ".join(c.get("name", "?") for c in failing)
                        log_debug(f"Blocked merge — CI failing: {names}")
                        print(
                            f"Workflow gate: cannot merge — CI checks are failing.\n"
                            f"\n"
                            f"Failing checks: {names}\n"
                            f"\n"
                            f"Fix the failing checks before merging.\n"
                            f"  gh pr checks {pr_ref}\n"
                            f"  gh run view <id> --log-failed",
                            file=sys.stderr,
                        )
                        sys.exit(2)

                    if pending:
                        names = ", ".join(c.get("name", "?") for c in pending)
                        log_debug(f"Blocked merge — CI still running: {names}")
                        print(
                            f"Workflow gate: cannot merge — CI checks still running.\n"
                            f"\n"
                            f"Pending checks: {names}\n"
                            f"\n"
                            f"Wait for CI to complete before merging.\n"
                            f"  gh pr checks {pr_ref} --watch",
                            file=sys.stderr,
                        )
                        sys.exit(2)
            except Exception as e:
                log_debug(f"CI check failed (allowing merge): {e}")

    # Gate: gh pr merge must run from main worktree, not feature worktree
    if re.search(r"\bgh\s+pr\s+merge\b", command):
        cd_match = re.match(r"cd\s+(~?/[^\s;&|]+)", command)
        if cd_match:
            merge_path = Path(cd_match.group(1)).expanduser()
            git_marker = merge_path / ".git"
            if git_marker.is_file():
                log_debug(f"Blocked merge from worktree: {merge_path}")
                print(
                    f"Workflow gate: cannot run gh pr merge from a feature worktree.\n"
                    f"\n"
                    f"  Target: {merge_path}\n"
                    f"  .git is a file (worktree), not a directory (main repo)\n"
                    f"\n"
                    f"gh pr merge tries to 'git checkout main' locally, which fails in\n"
                    f"a worktree because main is checked out in the parent repo.\n"
                    f"Run from the main worktree instead:\n"
                    f"  MAIN=$(git worktree list | head -1 | awk '{{print $1}}')\n"
                    f"  cd $MAIN && gh pr merge <number> --squash",
                    file=sys.stderr,
                )
                sys.exit(2)

    # Gate: git worktree add must NOT target inside the project directory
    if re.search(r"\bgit\s+worktree\s+add\b", command):
        wt_target_match = re.search(r"git\s+worktree\s+add\s+(~?/[^\s]+)", command)
        if wt_target_match:
            wt_target = wt_target_match.group(1)
            if "/Developer/" not in wt_target and "~/" not in wt_target:
                log_debug(f"Blocked worktree inside project: {wt_target}")
                print(
                    f"Workflow gate: worktree must be at ~/Developer/<name>, not inside the project.\n"
                    f"\n"
                    f"  Target: {wt_target}\n"
                    f"\n"
                    f"Create worktrees as siblings: git worktree add ~/Developer/<branch-name>",
                    file=sys.stderr,
                )
                sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
