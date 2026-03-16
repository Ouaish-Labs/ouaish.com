#!/usr/bin/env bash
# session_cleanup.sh — Archive session data after PR merges
#
# Usage:
#   ./scripts/workflow/session_cleanup.sh
#
# Moves .session/ to .session_archive/<timestamp>/ for forensic retention.
# Called during /worktree-pr Phase D (cleanup).

set -euo pipefail

SESSION_DIR=".session"

if [ ! -d "$SESSION_DIR" ]; then
    echo "No session data to clean up."
    exit 0
fi

ARCHIVE_DIR=".session_archive/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$ARCHIVE_DIR"
cp -r "$SESSION_DIR"/* "$ARCHIVE_DIR"/ 2>/dev/null || true
rm -rf "$SESSION_DIR"

echo "Session archived to $ARCHIVE_DIR"
echo "Session directory cleaned."
