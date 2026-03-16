#!/usr/bin/env python3
"""
Claude Code PreToolUse Hook: File protection rules

Blocks edits to critical files that should not be modified by Claude.
Patterns are configurable via the HOOK_PROTECTED_PATTERNS env var.

Hook protocol:
- stdin:  JSON with tool_name, tool_input (containing file_path)
- stdout: {"decision": "approve"} or {"decision": "block", "reason": "..."}

Exit codes:
- 0: Allow
- 2: Block with error message
"""

import json
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Default protected patterns (relative to project root)
DEFAULT_PROTECTED_PATTERNS = [
    # .env files contain secrets
    (
        r"(^|/)\.env(\..+)?$",
        ".env files contain secrets and must not be modified by hooks. "
        "Edit them manually.",
    ),
    # Prevent hooks from modifying their own configuration
    (
        r"\.claude/settings\.json$",
        ".claude/settings.json is protected to prevent self-modification by hooks.",
    ),
    # Prevent model from disabling its own enforcement
    (
        r"\.claude/hooks/.*\.py$",
        "Hook files are protected — the model cannot disable its own enforcement.",
    ),
]


def _load_extra_patterns() -> list[tuple[str, str]]:
    """
    Load additional patterns from HOOK_PROTECTED_PATTERNS env var.

    Format: comma-separated regexes. Each gets a generic block reason.
    Example: HOOK_PROTECTED_PATTERNS=migrations/applied/.*\\.sql$,config/prod\\.yml$
    """
    raw = os.environ.get("HOOK_PROTECTED_PATTERNS", "")
    if not raw.strip():
        return []
    patterns = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            patterns.append(
                (part, f"File matches protected pattern: {part}")
            )
    return patterns


def check_file_protection(file_path: str) -> tuple[bool, str]:
    """
    Check if a file path is protected from modification.

    Returns: (should_block, reason)
    """
    # Normalize path separators
    path = file_path.replace("\\", "/")

    # Make relative to project root if absolute
    try:
        abs_path = Path(file_path).resolve()
        if abs_path.is_relative_to(PROJECT_ROOT):
            path = str(abs_path.relative_to(PROJECT_ROOT))
    except (ValueError, OSError):
        pass

    all_patterns = DEFAULT_PROTECTED_PATTERNS + _load_extra_patterns()

    for pattern, reason in all_patterns:
        if re.search(pattern, path):
            return True, reason

    return False, ""


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"Error parsing hook input: {e}", file=sys.stderr)
        sys.exit(1)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # Only check Edit and Write tools
    if tool_name not in ("Edit", "Write"):
        print(json.dumps({"decision": "approve"}))
        sys.exit(0)

    # Get file path from tool input
    file_path = tool_input.get("file_path", "")
    if not file_path:
        print(json.dumps({"decision": "approve"}))
        sys.exit(0)

    # Check protection rules
    should_block, reason = check_file_protection(file_path)
    if should_block:
        print(json.dumps({"decision": "block", "reason": reason}))
        sys.exit(2)

    # File is not protected
    print(json.dumps({"decision": "approve"}))
    sys.exit(0)


if __name__ == "__main__":
    main()
