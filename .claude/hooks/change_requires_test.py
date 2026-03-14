#!/usr/bin/env python3
"""
Claude Code PreToolUse Hook: Change-requires-test guard

Blocks commits that modify source files matching configurable patterns
unless corresponding test files are also staged.

Configuration via environment variable HOOK_GUARDED_PAIRS (JSON array):
  [
    {"source": "src/models/", "tests": "tests/test_models/"},
    {"source": "src/api/",    "tests": "tests/test_api/"}
  ]

If HOOK_GUARDED_PAIRS is not set, the hook does nothing (approve all).

Exit codes:
- 0: Allow (output JSON with decision)
- 2: Block with error message
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def get_staged_files() -> set[str]:
    """Get list of staged files from git."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return set(result.stdout.strip().split("\n"))
    except Exception:
        pass
    return set()


def load_guarded_pairs() -> list[dict]:
    """Load source→test mappings from environment."""
    raw = os.environ.get("HOOK_GUARDED_PAIRS", "")
    if not raw:
        return []
    try:
        pairs = json.loads(raw)
        if isinstance(pairs, list):
            return [p for p in pairs if "source" in p and "tests" in p]
    except json.JSONDecodeError:
        pass
    return []


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    if tool_name != "Bash":
        sys.exit(0)

    command = tool_input.get("command", "")

    if "git commit" not in command:
        sys.exit(0)

    # Skip if --no-verify is used
    if "--no-verify" in command:
        print(json.dumps({
            "decision": "approve",
            "additionalContext": "AUDIT: Commit with --no-verify — change-requires-test guard bypassed.",
        }))
        sys.exit(0)

    guarded_pairs = load_guarded_pairs()
    if not guarded_pairs:
        sys.exit(0)

    staged = get_staged_files()
    if not staged:
        sys.exit(0)

    # For each guarded pair, check if source files are staged without test files
    for pair in guarded_pairs:
        source_prefix = pair["source"]
        test_prefix = pair["tests"]

        # Exclude test files from source check
        source_files = [
            f for f in staged
            if f.startswith(source_prefix)
            and "/tests/" not in f
            and not f.startswith("tests/")
            and not Path(f).name.startswith("test_")
        ]

        if not source_files:
            continue

        # Check if any test files matching the test prefix are staged
        test_files = [f for f in staged if f.startswith(test_prefix)]

        if not test_files:
            source_list = "\n".join(f"  - {f}" for f in sorted(source_files)[:10])
            if len(source_files) > 10:
                source_list += f"\n  ... and {len(source_files) - 10} more"

            print(
                f"Blocked: source files in '{source_prefix}' modified without test updates.\n\n"
                f"Staged source files:\n{source_list}\n\n"
                f"Required: include updates to test files in '{test_prefix}'.\n\n"
                f"To proceed:\n"
                f"1. Update the relevant test file(s)\n"
                f"2. Run the tests to verify they pass\n"
                f"3. Stage test files and commit again",
                file=sys.stderr,
            )
            sys.exit(2)

    # All guarded pairs satisfied
    sys.exit(0)


if __name__ == "__main__":
    main()
