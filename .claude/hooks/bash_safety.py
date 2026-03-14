#!/usr/bin/env python3
"""
Bash safety hook -- blocks dangerous shell commands.

Universal rules (no project-specific logic):
1. Destructive filesystem commands (rm -rf /, ~, .)
2. Destructive git commands (force push main, delete main, reset --hard main)
3. Destructive SQL (DROP TABLE/DATABASE, TRUNCATE, DELETE without WHERE)
4. Dangerous system commands (kill -9 1, killall -9, pkill -9)
5. Insecure permissions (chmod 777 -- warn only)
6. Test→stage→commit gate (blocks commit without fresh test pass marker)
7. Push CI cost warning (warns on >5 unpushed commits)
8. Branch switching block (prevents git checkout/switch to branches)

Exit codes:
- 0: Allow
- 2: Block with error message
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TESTS_PASSED_MARKER = PROJECT_ROOT / ".tests_passed"
DEBUG_LOG = Path(__file__).resolve().parent / "hook_debug.log"

# Source directories that require tests before committing.
# Override with HOOK_SOURCE_DIRS env var (comma-separated).
_default_source_dirs = ("src/", "lib/", "api/", "app/", "services/", "packages/")
SOURCE_DIRS = tuple(
    d.strip()
    for d in os.environ.get("HOOK_SOURCE_DIRS", ",".join(_default_source_dirs)).split(",")
    if d.strip()
)

# Files in source dirs exempt from test-before-commit requirement.
TEST_EXEMPT_PATTERNS = ("__init__.py", "conftest.py")


def log_debug(message: str):
    try:
        with open(DEBUG_LOG, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] bash_safety: {message}\n")
    except Exception:
        pass


def check_command(command: str) -> tuple[bool, str]:
    """Check a bash command for dangerous patterns.

    Returns (blocked, reason). If blocked is False and reason is non-empty,
    it's a warning (added as context but not blocked).
    """
    cmd = command.strip()
    cmd_lower = cmd.lower()

    # ── Rule 1: Destructive filesystem commands ──────────────────────
    # rm -rf / or rm -rf /*
    if re.search(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|(-[a-zA-Z]*f[a-zA-Z]*r))\s+/\s*$", cmd):
        return True, "Blocked: 'rm -rf /' would destroy the entire filesystem."

    if re.search(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|(-[a-zA-Z]*f[a-zA-Z]*r))\s+/\*", cmd):
        return True, "Blocked: 'rm -rf /*' would destroy the entire filesystem."

    # rm -rf ~ or rm -rf $HOME
    if re.search(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|(-[a-zA-Z]*f[a-zA-Z]*r))\s+(~|\$HOME)\b", cmd):
        return True, "Blocked: 'rm -rf ~' would destroy your home directory."

    # rm -rf . (at root of project or unknown context)
    if re.search(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|(-[a-zA-Z]*f[a-zA-Z]*r))\s+\.\s*$", cmd):
        return True, "Blocked: 'rm -rf .' would destroy the current directory tree."

    # ── Rule 2: Destructive git commands ─────────────────────────────
    # git push --force to main/master
    if re.search(r"\bgit\s+push\b", cmd_lower) and re.search(r"--force\b|-f\b", cmd_lower):
        # Check if targeting main or master
        if re.search(r"\b(main|master)\b", cmd_lower):
            return True, (
                "Blocked: force-pushing to main/master is destructive and can lose history.\n"
                "Use a feature branch and create a pull request instead."
            )

    # git checkout -B main/master (force-recreate branch)
    if re.search(r"\bgit\s+checkout\s+-B\s+(main|master)\b", cmd):
        return True, "Blocked: 'git checkout -B main' would overwrite the main branch."

    # git branch -D main/master (force-delete branch)
    if re.search(r"\bgit\s+branch\s+-D\s+(main|master)\b", cmd):
        return True, "Blocked: 'git branch -D main' would delete the main branch."

    # git reset --hard on main/master
    if re.search(r"\bgit\s+reset\s+--hard\b", cmd_lower):
        # Check if we're likely on main (explicit ref to main/master in command)
        if re.search(r"\b(main|master)\b", cmd_lower) or re.search(
            r"\bgit\s+reset\s+--hard\s*$", cmd_lower
        ):
            return True, (
                "Blocked: 'git reset --hard' on main/master discards all uncommitted work.\n"
                "Use 'git stash' to save changes, or work on a feature branch."
            )

    # ── Rule 3: Destructive SQL ──────────────────────────────────────
    # DROP TABLE / DROP DATABASE
    if re.search(r"\bDROP\s+(TABLE|DATABASE)\b", cmd, re.IGNORECASE):
        return True, "Blocked: DROP TABLE/DATABASE is destructive. Use migrations or confirm manually."

    # TRUNCATE TABLE
    if re.search(r"\bTRUNCATE\s+TABLE\b", cmd, re.IGNORECASE):
        return True, "Blocked: TRUNCATE TABLE deletes all rows. Use DELETE with WHERE or confirm manually."

    # DELETE FROM without WHERE
    if re.search(r"\bDELETE\s+FROM\s+\w+\s*;?\s*$", cmd, re.IGNORECASE):
        return True, (
            "Blocked: DELETE FROM without WHERE clause deletes all rows.\n"
            "Add a WHERE clause to target specific rows."
        )

    # ── Rule 4: Dangerous system commands ────────────────────────────
    # kill -9 1 (init process)
    if re.search(r"\bkill\s+-9\s+1\b", cmd):
        return True, "Blocked: 'kill -9 1' would kill the init process."

    # killall -9 (kill all processes matching name with SIGKILL)
    if re.search(r"\bkillall\s+-9\b", cmd):
        return True, "Blocked: 'killall -9' sends SIGKILL to all matching processes. Use a targeted kill instead."

    # pkill -9 (same risk)
    if re.search(r"\bpkill\s+-9\b", cmd):
        return True, "Blocked: 'pkill -9' sends SIGKILL to all matching processes. Use a targeted kill instead."

    # ── Rule 5: Insecure permissions (warn, don't block) ─────────────
    if re.search(r"\bchmod\s+(-R\s+)?777\b", cmd):
        return False, (
            "Warning: chmod 777 grants read/write/execute to everyone. "
            "Consider more restrictive permissions (e.g., 755 or 750)."
        )

    return False, ""


def check_tests_before_commit(command: str) -> tuple[bool, str]:
    """
    Enforce test->stage->commit discipline.

    Blocks git commit when source files are staged but no fresh .tests_passed
    marker exists. The marker is written by pytest_marker.py (PostToolUse hook)
    when pytest exits 0, and has a 10-minute TTL.

    Returns: (should_block, reason)
    """
    if not re.search(r"\bgit\s+commit\b", command):
        return False, ""

    import subprocess

    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return False, ""

        staged_files = result.stdout.strip().splitlines()
        if not staged_files:
            return False, ""

        # Check if any staged file is in a source directory that requires tests
        has_source_files = False
        for f in staged_files:
            if any(f.startswith(d) or ("/" + d) in f for d in SOURCE_DIRS):
                basename = Path(f).name
                if not any(basename == exempt for exempt in TEST_EXEMPT_PATTERNS):
                    has_source_files = True
                    break

        if not has_source_files:
            return False, ""

        # Source files are staged — check for test pass marker
        if not TESTS_PASSED_MARKER.exists():
            return True, (
                "Blocked: source files are staged but tests haven't been run.\n\n"
                "Required sequence: test -> stage -> commit\n"
                "1. Run relevant tests first\n"
                "2. Stage files: git add <files>\n"
                "3. Then commit\n\n"
                "The test pass marker (.tests_passed) is written automatically when pytest exits 0."
            )

        # Check marker age — stale passes (>10 min) don't count
        marker_age = time.time() - TESTS_PASSED_MARKER.stat().st_mtime
        if marker_age > 600:
            return True, (
                "Blocked: test pass marker is stale (>10 minutes old).\n\n"
                "Re-run tests before committing, then stage and commit."
            )

    except Exception as e:
        log_debug(f"check_tests_before_commit error: {e}")
        return False, ""

    return False, ""


def check_push_ci_cost(command: str) -> tuple[bool, str]:
    """
    Warn when pushing many commits to a non-main branch.

    Each push to a PR branch triggers CI workflows. Pushing 10 commits
    one-by-one means 10x the workflow runs vs. pushing once with all 10.

    Returns: (should_warn, reason)
    """
    if not re.search(r"\bgit\s+push\b", command):
        return False, ""

    # Don't warn on force-push (user is intentionally rewriting)
    if re.search(r"--force|-f\b", command):
        return False, ""

    import subprocess

    try:
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()

        if not branch or branch in ("main", "master"):
            return False, ""

        result = subprocess.run(
            ["git", "rev-list", "--count", f"origin/{branch}..HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return False, ""

        ahead_count = int(result.stdout.strip())
        if ahead_count > 5:
            return True, (
                f"CI cost warning: pushing {ahead_count} commits to '{branch}'.\n"
                f"Each push triggers CI workflows. Consider squashing first:\n"
                f"  git rebase -i HEAD~{ahead_count}\n"
                f"Or push anyway if this is intentional."
            )
    except Exception:
        pass

    return False, ""


def check_branch_switching(command: str) -> tuple[bool, str]:
    """
    Block git checkout/switch that would change the current branch.

    Claude sessions should not switch branches — it corrupts work when
    multiple sessions share a local checkout. Use git worktrees instead.

    Allowed (file-level operations):
      git checkout -- <file>           (restore file)
      git checkout <ref> -- <file>     (restore file from ref)
      git checkout -p / --patch        (interactive patch)

    Blocked (branch-level operations):
      git checkout <branch>            (switch branch)
      git checkout -b/-B <branch>      (create + switch)
      git switch <branch>              (switch branch)
      git switch -c/-C <branch>        (create + switch)

    Returns: (should_block, reason)
    """
    cmd = " ".join(command.split())

    # --- git switch: always a branch operation, always blocked ---
    if re.search(r"\bgit\s+switch\b", cmd):
        return True, (
            "Blocked: 'git switch' changes the current branch.\n\n"
            "Claude sessions should not switch branches — it corrupts work\n"
            "when multiple sessions share this checkout.\n\n"
            "Use worktrees instead:\n"
            "  git worktree add ../worktree-name branch-name\n"
            "  cd ../worktree-name"
        )

    # --- git checkout: overloaded, need to distinguish branch vs file ops ---
    checkout_match = re.search(r"\bgit\s+checkout\b", cmd)
    if not checkout_match:
        return False, ""

    after_checkout = cmd[checkout_match.end():].strip()

    # ALLOW: git checkout -- <file>
    if (
        after_checkout.startswith("--")
        and not after_checkout.startswith("---")
        and (after_checkout == "--" or (len(after_checkout) > 2 and after_checkout[2] == " "))
    ):
        return False, ""

    # ALLOW: git checkout -p / --patch
    if re.match(r"(-p|--patch)\b", after_checkout):
        return False, ""

    # ALLOW: git checkout <something> -- <file>
    if re.search(r"\s--\s", after_checkout):
        return False, ""

    # BLOCK: git checkout -b/-B (create + switch branch)
    if re.match(r"-[bB]\b", after_checkout):
        return True, (
            "Blocked: 'git checkout -b' creates and switches to a new branch.\n\n"
            "Use worktrees instead:\n"
            "  git worktree add -b new-branch ../worktree-name\n"
            "  cd ../worktree-name"
        )

    # BLOCK: git checkout <anything-else> (switching to branch/tag/commit)
    if after_checkout and not after_checkout.startswith("-"):
        return True, (
            f"Blocked: 'git checkout {after_checkout.split()[0]}' switches the current branch.\n\n"
            "Use worktrees instead:\n"
            f"  git worktree add ../worktree-name {after_checkout.split()[0]}\n"
            f"  cd ../worktree-name"
        )

    # git checkout with no args — harmless
    if not after_checkout:
        return False, ""

    # Unknown flag patterns — block to be safe
    return True, (
        "Blocked: unrecognized 'git checkout' pattern.\n\n"
        "Allowed patterns:\n"
        "  git checkout -- <file>        (restore file)\n"
        "  git checkout <ref> -- <file>  (restore from ref)\n"
        "  git checkout -p               (interactive patch)\n\n"
        "For branch operations, use worktrees:\n"
        "  git worktree add ../worktree-name branch-name"
    )


def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, Exception):
        # Don't block on hook input errors
        print(json.dumps({"decision": "approve"}))
        return

    tool_input = input_data.get("input", {})
    command = tool_input.get("command", "")

    if not command:
        print(json.dumps({"decision": "approve"}))
        return

    # ── Rule 1-5: Dangerous commands ─────────────────────────────────
    blocked, reason = check_command(command)

    if blocked:
        print(json.dumps({"decision": "block", "reason": reason}))
        sys.exit(2)

    # ── Rule 6: Test→stage→commit gate ───────────────────────────────
    blocked, reason = check_tests_before_commit(command)
    if blocked:
        log_debug(f"Blocked commit without tests: {command[:100]}")
        print(json.dumps({"decision": "block", "reason": reason}))
        sys.exit(2)

    # ── Rule 7: Push CI cost warning ─────────────────────────────────
    should_warn, warn_reason = check_push_ci_cost(command)

    # ── Rule 8: Branch switching block ───────────────────────────────
    blocked, reason = check_branch_switching(command)
    if blocked:
        log_debug(f"Blocked branch switch: {command[:100]}")
        print(json.dumps({"decision": "block", "reason": reason}))
        sys.exit(2)

    # Collect warnings
    warnings = []
    if reason and not blocked:
        warnings.append(reason)
    if should_warn and warn_reason:
        warnings.append(warn_reason)

    if warnings:
        print(json.dumps({"decision": "approve", "additionalContext": "\n\n".join(warnings)}))
        return

    print(json.dumps({"decision": "approve"}))


if __name__ == "__main__":
    main()
