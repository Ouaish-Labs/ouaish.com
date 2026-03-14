#!/usr/bin/env python3
"""
Claude Code PostToolUse Hook: Write test pass marker after pytest succeeds.

Works with bash_safety.py's check_tests_before_commit gate:
- This hook: writes .tests_passed marker when pytest exits 0
- bash_safety.py: blocks git commit if source files staged without marker
- bash_safety.py: deletes marker on git add (staging invalidates prior test run)

This enforces the sequence: test -> stage -> commit.

Hook protocol (PostToolUse on Bash):
- stdin: JSON with tool_name, input.command, output (stdout from bash)
- stdout: {"decision": "approve"} or {"decision": "approve", "additionalContext": "..."}

Exit codes:
- 0: Always (PostToolUse hooks should not block)
"""

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TESTS_PASSED_MARKER = PROJECT_ROOT / ".tests_passed"
DEBUG_LOG = Path(__file__).resolve().parent / "hook_debug.log"

# Marker expires after 10 minutes (stale test results should not gate commits)
MARKER_TTL_SECONDS = 600


def log_debug(message: str):
    try:
        with open(DEBUG_LOG, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] pytest_marker: {message}\n")
    except Exception:
        pass


def marker_is_fresh() -> bool:
    """Check if the marker file exists and is less than MARKER_TTL_SECONDS old."""
    if not TESTS_PASSED_MARKER.exists():
        return False
    try:
        age = time.time() - TESTS_PASSED_MARKER.stat().st_mtime
        return age < MARKER_TTL_SECONDS
    except OSError:
        return False


def main():
    try:
        raw_input = sys.stdin.read()
        input_data = json.loads(raw_input)
    except (json.JSONDecodeError, Exception):
        print(json.dumps({"decision": "approve"}))
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("input", {})
    tool_output = input_data.get("output", "")
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""

    if tool_name != "Bash":
        print(json.dumps({"decision": "approve"}))
        sys.exit(0)

    # Only care about pytest commands
    if not re.search(r"\bpytest\b", command):
        # If marker exists but is stale, clean it up
        if TESTS_PASSED_MARKER.exists() and not marker_is_fresh():
            try:
                TESTS_PASSED_MARKER.unlink()
                log_debug("Stale marker removed (TTL expired)")
            except OSError:
                pass
        print(json.dumps({"decision": "approve"}))
        sys.exit(0)

    # Extract stdout from output
    stdout = tool_output if isinstance(tool_output, str) else str(tool_output)

    # pytest success patterns: "X passed" with no "failed" or "error"
    has_passed = re.search(r"\d+\s+passed", stdout)
    has_failed = re.search(r"\d+\s+failed", stdout)
    has_error = re.search(r"\d+\s+error", stdout)

    if has_passed and not has_failed and not has_error:
        try:
            TESTS_PASSED_MARKER.write_text(
                f"Tests passed at {datetime.now().isoformat()}\n"
                f"Command: {command}\n"
            )
            log_debug(f"Marker written after: {command[:80]}")
            print(json.dumps({
                "decision": "approve",
                "additionalContext": "Tests passed - .tests_passed marker written."
            }))
        except OSError as e:
            log_debug(f"Failed to write marker: {e}")
            print(json.dumps({"decision": "approve"}))
    elif (has_failed or has_error) and TESTS_PASSED_MARKER.exists():
        # Tests failed - remove any stale marker
        try:
            TESTS_PASSED_MARKER.unlink()
            log_debug("Marker removed after test failure")
        except OSError:
            pass
        print(json.dumps({
            "decision": "approve",
            "additionalContext": "Tests failed - .tests_passed marker removed."
        }))
    else:
        print(json.dumps({"decision": "approve"}))

    sys.exit(0)


if __name__ == "__main__":
    main()
