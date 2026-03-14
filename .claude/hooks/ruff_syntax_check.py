#!/usr/bin/env python3
"""
Claude Code PostToolUse Hook: Ruff syntax check after file edits.

Runs `ruff check --select E,F` on Python files after Edit/Write operations.
Catches syntax errors (E) and undefined names (F) immediately — before the
next agent step builds on broken code.

Returns additionalContext with errors (never blocks edits).
If ruff is not installed, silently approves.

Hook protocol (PostToolUse on Edit|Write):
  stdin:  JSON with tool_name, tool_input (file_path), tool_output
  stdout: {"decision": "approve"} or
          {"decision": "approve", "additionalContext": "ruff found errors: ..."}

Stdlib only — no third-party imports.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def find_ruff() -> str | None:
    """Find ruff on PATH. Returns None if not installed."""
    return shutil.which("ruff")


def main():
    # Parse hook input from stdin
    try:
        input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, Exception):
        print(json.dumps({"decision": "approve"}))
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # Only check Edit and Write on Python files
    if tool_name not in ("Edit", "Write"):
        print(json.dumps({"decision": "approve"}))
        sys.exit(0)

    file_path = tool_input.get("file_path", "")
    if not file_path.endswith(".py"):
        print(json.dumps({"decision": "approve"}))
        sys.exit(0)

    # Find ruff — if not installed, silently approve
    ruff = find_ruff()
    if not ruff:
        print(json.dumps({"decision": "approve"}))
        sys.exit(0)

    # Run ruff: E = syntax/pyflakes errors, F = undefined names
    try:
        result = subprocess.run(
            [ruff, "check", "--select", "E,F", "--no-fix", "--force-exclude", file_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print(json.dumps({"decision": "approve"}))
        sys.exit(0)

    if result.returncode == 0:
        # Clean — no issues
        print(json.dumps({"decision": "approve"}))
        sys.exit(0)

    # Parse errors from stdout
    errors = result.stdout.strip()
    if not errors:
        print(json.dumps({"decision": "approve"}))
        sys.exit(0)

    # Count errors (exclude "Found N errors" summary line)
    error_lines = [
        line for line in errors.split("\n")
        if line.strip() and not line.startswith("Found")
    ]
    error_count = len(error_lines)

    # Return as additionalContext so Claude sees the errors
    context = (
        f"ruff found {error_count} syntax/import error(s) in {Path(file_path).name}:\n"
        f"{errors}\n"
        f"Fix these before proceeding."
    )

    output = {
        "decision": "approve",
        "additionalContext": context,
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
