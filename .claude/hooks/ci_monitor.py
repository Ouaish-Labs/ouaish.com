#!/usr/bin/env python3
"""
Claude Code PostToolUse Hook: CI/CD Monitoring after git push

After a successful git push, this hook monitors the CI pipeline status
and reports back to Claude. This ensures Claude doesn't claim success
without verifying the deployment actually worked.

Hook protocol (PostToolUse on Bash):
- stdin: JSON with tool_name, input (command), output (stdout from bash)
- stdout: {"decision": "approve"} or {"decision": "approve", "additionalContext": "CI status: ..."}
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Project root: hooks/ lives under .claude/ which lives under the project
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Debug logging
DEBUG_LOG = Path(__file__).resolve().parent / "hook_debug.log"

# Configuration
MAX_WAIT_SECONDS = 600  # 10 minutes max wait
POLL_INTERVAL_SECONDS = 10
INITIAL_DELAY_SECONDS = 5  # Wait for CI to register the push


def log_debug(message: str):
    """Append debug message to log file."""
    try:
        with open(DEBUG_LOG, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] ci_monitor: {message}\n")
    except Exception:
        pass


def is_git_push_command(command: str) -> bool:
    """Check if command is a git push."""
    return bool(re.search(r"\bgit\s+push\b", command))


def was_push_successful(tool_response: dict | str) -> bool:
    """Check if the push command succeeded."""
    if isinstance(tool_response, str):
        return "error" not in tool_response.lower() and "rejected" not in tool_response.lower()
    elif isinstance(tool_response, dict):
        exit_code = tool_response.get("exit_code", tool_response.get("exitCode", 0))
        return exit_code == 0
    return True


def get_latest_run() -> dict | None:
    """Get the most recent CI run for current branch."""
    try:
        result = subprocess.run(
            ["gh", "run", "list", "--limit", "1", "--json", "databaseId,status,conclusion,name,headBranch,event"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode == 0:
            runs = json.loads(result.stdout)
            if runs:
                return runs[0]
    except Exception as e:
        log_debug(f"Error getting runs: {e}")
    return None


def get_run_status(run_id: int) -> dict | None:
    """Get status of a specific run."""
    try:
        result = subprocess.run(
            ["gh", "run", "view", str(run_id), "--json", "status,conclusion,name"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception as e:
        log_debug(f"Error getting run status: {e}")
    return None


def get_failed_jobs(run_id: int) -> str:
    """Get summary of failed jobs for a run."""
    try:
        result = subprocess.run(
            ["gh", "run", "view", str(run_id), "--json", "jobs"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            failed_jobs = [j for j in data.get("jobs", []) if j.get("conclusion") == "failure"]
            if failed_jobs:
                return ", ".join(j.get("name", "unknown") for j in failed_jobs[:3])
    except Exception as e:
        log_debug(f"Error getting failed jobs: {e}")
    return "unknown"


def monitor_ci() -> tuple[str, bool]:
    """
    Monitor CI status after push.

    Returns: (status_message, success)
    """
    print("Monitoring CI pipeline...", file=sys.stderr)
    log_debug("Starting CI monitoring")

    # Initial delay for CI to register
    time.sleep(INITIAL_DELAY_SECONDS)

    # Get the run that was triggered by our push
    initial_run = get_latest_run()
    if not initial_run:
        return "Could not find CI run. Check manually: gh run list", False

    run_id = initial_run["databaseId"]
    run_name = initial_run.get("name", "CI")
    log_debug(f"Monitoring run {run_id}: {run_name}")

    # Poll until complete or timeout
    start_time = time.time()
    last_status = None

    while time.time() - start_time < MAX_WAIT_SECONDS:
        status_data = get_run_status(run_id)
        if not status_data:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        status = status_data.get("status", "unknown")
        conclusion = status_data.get("conclusion", "")

        # Report status changes
        if status != last_status:
            elapsed = int(time.time() - start_time)
            print(f"   CI status: {status} ({elapsed}s elapsed)", file=sys.stderr)
            last_status = status
            log_debug(f"Status update: {status}, conclusion: {conclusion}")

        # Check if complete
        if status == "completed":
            if conclusion == "success":
                return f"CI passed: {run_name} (run {run_id})", True
            elif conclusion == "failure":
                failed_jobs = get_failed_jobs(run_id)
                return (
                    f"CI FAILED: {run_name} (run {run_id})\n"
                    f"   Failed jobs: {failed_jobs}\n"
                    f"   View details: gh run view {run_id} --log-failed",
                    False,
                )
            elif conclusion == "cancelled":
                return f"CI cancelled: {run_name} (run {run_id})", False
            else:
                return f"CI completed with: {conclusion} (run {run_id})", False

        time.sleep(POLL_INTERVAL_SECONDS)

    # Timeout
    return (
        f"CI still running after {MAX_WAIT_SECONDS}s. Check: gh run view {run_id}",
        False,
    )


def main():
    log_debug("Hook started")

    try:
        raw_input = sys.stdin.read()
        input_data = json.loads(raw_input)
    except json.JSONDecodeError as e:
        log_debug(f"JSON parse error: {e}")
        # Pass through on parse error
        print(json.dumps({"decision": "approve"}))
        sys.exit(0)
    except Exception as e:
        log_debug(f"Error reading stdin: {e}")
        print(json.dumps({"decision": "approve"}))
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    tool_response = input_data.get("tool_response", {})

    # Only process Bash commands
    if tool_name != "Bash":
        print(json.dumps({"decision": "approve"}))
        sys.exit(0)

    command = tool_input.get("command", "")

    # Only monitor git push commands
    if not is_git_push_command(command):
        log_debug(f"Not a git push: {command[:50]}")
        print(json.dumps({"decision": "approve"}))
        sys.exit(0)

    # Only monitor successful pushes
    if not was_push_successful(tool_response):
        log_debug("Push was not successful, skipping CI monitor")
        print(json.dumps({"decision": "approve"}))
        sys.exit(0)

    log_debug(f"Detected successful git push: {command[:100]}")

    # Monitor CI
    ci_message, ci_success = monitor_ci()

    # Print CI status to stderr (visible in terminal)
    print(f"\n{ci_message}", file=sys.stderr)

    # Return approval with CI status as additional context
    result = {"decision": "approve", "additionalContext": f"CI status: {ci_message}"}

    log_debug(f"CI monitoring complete: success={ci_success}")
    print(json.dumps(result))
    sys.exit(0)


if __name__ == "__main__":
    main()
