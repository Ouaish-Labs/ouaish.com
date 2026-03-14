#!/usr/bin/env python3
"""
Claude Code PostToolUse Hook: Output size limiter

Prevents freezing by truncating large command output.
This is a safety net - catches all large output regardless of command.

Exit codes:
- 0 with JSON: Return modified output
- 0 without JSON: Pass through as-is
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Portable project root derivation: hooks/ -> .claude/ -> project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Debug logging - writes to file for diagnosis
DEBUG_LOG = PROJECT_ROOT / ".claude" / "hooks" / "hook_debug.log"


def log_debug(message: str):
    """Append debug message to log file."""
    try:
        with open(DEBUG_LOG, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] output_limiter: {message}\n")
    except Exception:
        pass  # Don't fail on logging errors


# Configurable output limit (default 50KB)
MAX_OUTPUT_BYTES = int(os.environ.get("HOOK_OUTPUT_LIMIT", 50000))
MAX_OUTPUT_CHARS = MAX_OUTPUT_BYTES  # Approximate, assuming ~1 byte per char


def format_size(size_bytes: int) -> str:
    """Format byte size as human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} bytes"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def truncate_output(output: str) -> tuple:
    """
    Truncate output if it exceeds the limit.

    Returns: (output, was_truncated)
    """
    if len(output) <= MAX_OUTPUT_CHARS:
        return output, False

    original_size = len(output)

    # Keep first portion, add truncation notice
    truncated = output[:MAX_OUTPUT_CHARS]

    # Try to truncate at a newline for cleaner output
    last_newline = truncated.rfind("\n", MAX_OUTPUT_CHARS - 1000, MAX_OUTPUT_CHARS)
    if last_newline > MAX_OUTPUT_CHARS - 1000:
        truncated = truncated[:last_newline]

    notice = (
        f"\n\n[OUTPUT TRUNCATED: {format_size(original_size)} → {format_size(len(truncated))}]\n"
        f"[To avoid truncation: use --top N, | head -N, | jq '.[:N]', or write to file]"
    )

    return truncated + notice, True


def main():
    log_debug("Hook started")
    try:
        raw_input = sys.stdin.read()
        log_debug(f"Raw input length: {len(raw_input)}")
        input_data = json.loads(raw_input)
    except json.JSONDecodeError as e:
        log_debug(f"JSON parse error: {e}")
        print(f"Error parsing hook input: {e}", file=sys.stderr)
        sys.exit(0)  # Don't block on parse errors
    except Exception as e:
        log_debug(f"Unexpected error reading stdin: {type(e).__name__}: {e}")
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    # API uses "tool_response" not "tool_result"
    tool_response = input_data.get("tool_response", {})

    # Only process Bash output
    if tool_name != "Bash":
        log_debug(f"Skipping non-Bash tool: {tool_name}")
        sys.exit(0)

    # Handle both string and dict responses
    if isinstance(tool_response, str):
        stdout = tool_response
        stderr = ""
        log_debug(f"String response, length: {len(stdout)}")
    elif isinstance(tool_response, dict):
        stdout = tool_response.get("stdout", "") or tool_response.get("output", "") or ""
        stderr = tool_response.get("stderr", "") or ""
        log_debug(f"Dict response, stdout len: {len(stdout)}, stderr len: {len(stderr)}")
    else:
        log_debug(f"Unknown response type: {type(tool_response)}")
        sys.exit(0)

    # Check if truncation needed
    stdout_truncated, stdout_was_truncated = truncate_output(stdout)
    stderr_truncated, stderr_was_truncated = truncate_output(stderr)

    if not stdout_was_truncated and not stderr_was_truncated:
        # No changes needed
        log_debug("No truncation needed")
        sys.exit(0)

    # Build modified response
    if isinstance(tool_response, str):
        modified_response = stdout_truncated
    else:
        modified_response = {**tool_response}
        if stdout_was_truncated:
            if "stdout" in modified_response:
                modified_response["stdout"] = stdout_truncated
            elif "output" in modified_response:
                modified_response["output"] = stdout_truncated
        if stderr_was_truncated:
            modified_response["stderr"] = stderr_truncated

    if stdout_was_truncated:
        log_debug(f"Truncated stdout: {format_size(len(stdout))} -> {format_size(len(stdout_truncated))}")
        print(
            f"stdout truncated: {format_size(len(stdout))} -> {format_size(len(stdout_truncated))}", file=sys.stderr
        )
    if stderr_was_truncated:
        log_debug(f"Truncated stderr: {format_size(len(stderr))} -> {format_size(len(stderr_truncated))}")
        print(
            f"stderr truncated: {format_size(len(stderr))} -> {format_size(len(stderr_truncated))}", file=sys.stderr
        )

    # Return modified output
    result = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolResponse": modified_response}}
    log_debug("Returning truncated result")
    print(json.dumps(result))
    sys.exit(0)


if __name__ == "__main__":
    main()
