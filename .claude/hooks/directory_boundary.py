#!/usr/bin/env python3
"""
Claude Code PreToolUse Hook: Directory boundary enforcement

Restricts file operations to the current working directory and its children.
Prevents accidental modifications to files outside this project.

Worktree-aware mode:
- If .worktree-root marker exists in the git toplevel, Read operations are
  never blocked (agents need to reference main repo patterns), but Write/Edit
  operations must be within the worktree boundary.
- In normal mode, all file operations are restricted to CWD.
- ~/.claude/ is always allowed (hooks, settings).

Protocol:
- stdin:  JSON with tool_name and input (file_path for Read/Edit/Write)
- stdout: {"decision": "approve"} or {"decision": "block", "reason": "..."}

Exit codes:
- 0: Allow
- 2: Block with error message
"""

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def is_within_directory(file_path: str, base_dir: Path) -> bool:
    """
    Check if file_path is within base_dir or its subdirectories.

    Handles:
    - Absolute paths
    - Relative paths
    - Symlinks (resolved)
    - Path traversal attempts (../)
    """
    try:
        # Resolve to absolute path, following symlinks
        resolved_path = Path(file_path).resolve()
        resolved_base = base_dir.resolve()

        # Check if the resolved path starts with the base directory
        return resolved_path.is_relative_to(resolved_base)
    except (ValueError, OSError):
        # If we can't resolve, be conservative and block
        return False


def find_worktree_root() -> "Path | None":
    """
    Look for .worktree-root marker in git toplevel directory.
    Returns the worktree root path if found, None otherwise.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            toplevel = Path(result.stdout.strip())
            marker = toplevel / ".worktree-root"
            if marker.exists():
                return toplevel
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"Error parsing hook input: {e}", file=sys.stderr)
        sys.exit(1)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # Only check file operation tools
    if tool_name not in ("Read", "Write", "Edit", "NotebookEdit"):
        print(json.dumps({"decision": "approve"}))
        sys.exit(0)

    # Get file path from tool input
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path", "")
    if not file_path:
        print(json.dumps({"decision": "approve"}))
        sys.exit(0)

    # ~/.claude/ is always allowed (hooks, settings)
    home = Path.home()
    claude_dir = home / ".claude"
    if is_within_directory(file_path, claude_dir):
        print(json.dumps({"decision": "approve"}))
        sys.exit(0)

    # Determine boundary: worktree root (if marker exists) or CWD
    worktree_root = find_worktree_root()

    if worktree_root:
        # Worktree mode: Read is never blocked (agents reference main repo)
        if tool_name == "Read":
            print(json.dumps({"decision": "approve"}))
            sys.exit(0)

        # Write/Edit/NotebookEdit must be within worktree
        if not is_within_directory(file_path, worktree_root):
            reason = (
                f"Directory boundary violation: file writes restricted to worktree at {worktree_root}. "
                f"Attempted path: {file_path}. "
                f"Did the agent forget to cd to the worktree?"
            )
            print(json.dumps({"decision": "block", "reason": reason}))
            print(f"   Worktree root: {worktree_root}", file=sys.stderr)
            print(f"   Attempted:     {file_path}", file=sys.stderr)
            sys.exit(2)
    else:
        # No worktree marker — use CWD boundary (original behavior)
        cwd = Path.cwd()

        if not is_within_directory(file_path, cwd):
            reason = (
                f"Directory boundary violation: file operations restricted to {cwd}. "
                f"Attempted path: {file_path}. "
                f"Use a separate Claude session in the target directory."
            )
            print(json.dumps({"decision": "block", "reason": reason}))
            print(f"   Restricted to: {cwd}", file=sys.stderr)
            print(f"   Attempted:     {file_path}", file=sys.stderr)
            sys.exit(2)

    # File is within allowed directory
    print(json.dumps({"decision": "approve"}))
    sys.exit(0)


if __name__ == "__main__":
    main()
