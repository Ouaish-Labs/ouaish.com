#!/usr/bin/env bash
# test_workflow_gate.sh — End-to-end test for session recorder + workflow gate
#
# Tests that:
# 1. Without session_init, commits work normally (no manifest = no enforcement)
# 2. With session_init, commits are BLOCKED without Phase 0 architect
# 3. After recording a fake architect dispatch, commits are ALLOWED
# 4. Final Summary is BLOCKED without review agents + external check
# 5. After recording those events, Final Summary is ALLOWED
# 6. session_summary.sh generates correct output
# 7. session_cleanup.sh archives properly
# 8. Parallel worktree isolation works (cd prefix resolves to correct .session/)
#
# Usage: ./scripts/workflow/test_workflow_gate.sh
#
# Does NOT require Docker, git, or a real repo — uses temp dirs and
# feeds JSON directly to the hooks via stdin.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WORKFLOW_DIR="$REPO_ROOT/scripts/workflow"

# Find hooks — check installed location first, then source repo location
if [ -d "$REPO_ROOT/.claude/hooks" ] && [ -f "$REPO_ROOT/.claude/hooks/workflow_gate.py" ]; then
    HOOK_DIR="$REPO_ROOT/.claude/hooks"
elif [ -d "$REPO_ROOT/hooks" ] && [ -f "$REPO_ROOT/hooks/workflow_gate.py" ]; then
    HOOK_DIR="$REPO_ROOT/hooks"
else
    echo "ERROR: Hooks not found at .claude/hooks/ or hooks/"
    echo "Install hooks first: bash install.sh --hooks"
    exit 1
fi

# Verify required hook files exist
for f in "$HOOK_DIR/workflow_gate.py" "$HOOK_DIR/agent_recorder.py"; do
    if [ ! -f "$f" ]; then
        echo "ERROR: Hook not found: $f"
        exit 1
    fi
done

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

PASS=0
FAIL=0

assert_exit() {
    local expected=$1
    local actual=$2
    local description=$3
    if [ "$actual" -eq "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC}: $description (exit $actual)"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC}: $description (expected exit $expected, got $actual)"
        FAIL=$((FAIL + 1))
    fi
}

assert_file_exists() {
    local filepath=$1
    local description=$2
    if [ -f "$filepath" ]; then
        echo -e "  ${GREEN}PASS${NC}: $description"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC}: $description (file not found: $filepath)"
        FAIL=$((FAIL + 1))
    fi
}

assert_file_not_exists() {
    local filepath=$1
    local description=$2
    if [ ! -f "$filepath" ]; then
        echo -e "  ${GREEN}PASS${NC}: $description"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC}: $description (file should not exist: $filepath)"
        FAIL=$((FAIL + 1))
    fi
}

assert_contains() {
    local filepath=$1
    local pattern=$2
    local description=$3
    if grep -q "$pattern" "$filepath" 2>/dev/null; then
        echo -e "  ${GREEN}PASS${NC}: $description"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC}: $description (pattern '$pattern' not found in $filepath)"
        FAIL=$((FAIL + 1))
    fi
}

# Create a temp working directory
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT
cd "$TMPDIR"

# Copy workflow scripts to temp dir
mkdir -p scripts/workflow
cp "$WORKFLOW_DIR/session_init.sh" scripts/workflow/
cp "$WORKFLOW_DIR/session_summary.sh" scripts/workflow/
cp "$WORKFLOW_DIR/session_cleanup.sh" scripts/workflow/

echo "================================================="
echo "Session Recorder + Workflow Gate Tests"
echo "Working dir: $TMPDIR"
echo "================================================="

# --- Test 1: No manifest = no enforcement ---
echo ""
echo "${YELLOW}Test 1: No manifest — git commit should pass${NC}"

EXIT_CODE=0
echo '{"tool_name":"Bash","tool_input":{"command":"git commit -m test"}}' | \
    python3 "$HOOK_DIR/workflow_gate.py" 2>/dev/null || EXIT_CODE=$?
assert_exit 0 $EXIT_CODE "git commit allowed without manifest"

# --- Test 2: session_init creates manifest ---
echo ""
echo "${YELLOW}Test 2: session_init.sh creates manifest${NC}"

./scripts/workflow/session_init.sh standard > /dev/null 2>&1
assert_file_exists ".session/manifest.json" "manifest.json created"
assert_contains ".session/manifest.json" "feature-dev:code-architect" "manifest requires architect"
assert_contains ".session/manifest.json" "pr-review-toolkit" "manifest requires review agents"

# --- Test 3: With manifest, commit blocked without Phase 0 ---
echo ""
echo "${YELLOW}Test 3: git commit BLOCKED without Phase 0 architect${NC}"

EXIT_CODE=0
echo '{"tool_name":"Bash","tool_input":{"command":"git commit -m test"}}' | \
    python3 "$HOOK_DIR/workflow_gate.py" 2>/dev/null || EXIT_CODE=$?
assert_exit 2 $EXIT_CODE "git commit blocked (no architect dispatched)"

# --- Test 4: Record architect dispatch ---
echo ""
echo "${YELLOW}Test 4: Record architect dispatch via agent_recorder${NC}"

echo '{
  "tool_name": "Agent",
  "tool_input": {
    "subagent_type": "feature-dev:code-architect",
    "model": "sonnet",
    "description": "Analyze files",
    "prompt": "test prompt"
  },
  "tool_response": "agentId: test-architect-001"
}' | python3 "$HOOK_DIR/agent_recorder.py" 2>/dev/null

assert_file_exists ".session/agents.json" "agents.json created"
assert_contains ".session/agents.json" "feature-dev:code-architect" "architect dispatch recorded"
assert_contains ".session/agents.json" "test-architect-001" "agent ID recorded"

# --- Test 5: Record pytest event ---
echo ""
echo "${YELLOW}Test 5: Record pytest event via agent_recorder${NC}"

echo '{
  "tool_name": "Bash",
  "tool_input": {"command": "python -m pytest tests/ -v"},
  "tool_response": {"stdout": "4 passed in 2.3s", "stderr": "", "exit_code": 0}
}' | python3 "$HOOK_DIR/agent_recorder.py" 2>/dev/null

assert_file_exists ".session/events.json" "events.json created"
assert_contains ".session/events.json" '"type": "pytest"' "pytest event recorded"
assert_contains ".session/events.json" '"passed": 4' "pass count recorded"

# --- Test 6: Commit now allowed (architect + pytest done) ---
echo ""
echo "${YELLOW}Test 6: git commit ALLOWED after Phase 0 + pytest${NC}"

EXIT_CODE=0
echo '{"tool_name":"Bash","tool_input":{"command":"git commit -m test"}}' | \
    python3 "$HOOK_DIR/workflow_gate.py" 2>/dev/null || EXIT_CODE=$?
assert_exit 0 $EXIT_CODE "git commit allowed (architect dispatched + tests passed)"

# --- Test 7: Final Summary blocked without review agents ---
echo ""
echo "${YELLOW}Test 7: Final Summary BLOCKED without review agents${NC}"

EXIT_CODE=0
echo '{"tool_name":"Bash","tool_input":{"command":"gh pr comment 123 --body \"Review Complete — Final Summary\""}}' | \
    python3 "$HOOK_DIR/workflow_gate.py" 2>/dev/null || EXIT_CODE=$?
assert_exit 2 $EXIT_CODE "Final Summary blocked (no review agents)"

# --- Test 8: Record review agent dispatch ---
echo ""
echo "${YELLOW}Test 8: Record review agent dispatch${NC}"

echo '{
  "tool_name": "Agent",
  "tool_input": {
    "subagent_type": "pr-review-toolkit:code-reviewer",
    "model": "sonnet",
    "description": "Review PR"
  },
  "tool_response": "agentId: test-reviewer-001"
}' | python3 "$HOOK_DIR/agent_recorder.py" 2>/dev/null

assert_contains ".session/agents.json" "pr-review-toolkit:code-reviewer" "review agent recorded"

# --- Test 9: Final Summary still blocked (no external check) ---
echo ""
echo "${YELLOW}Test 9: Final Summary BLOCKED without external review check${NC}"

EXIT_CODE=0
echo '{"tool_name":"Bash","tool_input":{"command":"gh pr comment 123 --body \"Review Complete — Final Summary\""}}' | \
    python3 "$HOOK_DIR/workflow_gate.py" 2>/dev/null || EXIT_CODE=$?
assert_exit 2 $EXIT_CODE "Final Summary blocked (no external review check)"

# --- Test 10: Record external review check ---
echo ""
echo "${YELLOW}Test 10: Record external review check${NC}"

echo '{
  "tool_name": "Bash",
  "tool_input": {"command": "gh api repos/owner/repo/pulls/123/comments --jq length"},
  "tool_response": {"stdout": "2", "stderr": "", "exit_code": 0}
}' | python3 "$HOOK_DIR/agent_recorder.py" 2>/dev/null

assert_contains ".session/events.json" '"type": "external_review_check"' "external check recorded"

# --- Test 11: Final Summary now allowed ---
echo ""
echo "${YELLOW}Test 11: Final Summary ALLOWED after all phases complete${NC}"

EXIT_CODE=0
echo '{"tool_name":"Bash","tool_input":{"command":"gh pr comment 123 --body \"Review Complete — Final Summary\""}}' | \
    python3 "$HOOK_DIR/workflow_gate.py" 2>/dev/null || EXIT_CODE=$?
assert_exit 0 $EXIT_CODE "Final Summary allowed (all phases complete)"

# --- Test 12: session_summary generates report ---
echo ""
echo "${YELLOW}Test 12: session_summary.sh generates report${NC}"

SUMMARY_OUTPUT=$(./scripts/workflow/session_summary.sh 123 2>/dev/null || true)
if echo "$SUMMARY_OUTPUT" | grep -q "auto-generated"; then
    echo -e "  ${GREEN}PASS${NC}: session_summary.sh generates output"
    PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC}: session_summary.sh output missing"
    FAIL=$((FAIL + 1))
fi

if echo "$SUMMARY_OUTPUT" | grep -q "feature-dev:code-architect"; then
    echo -e "  ${GREEN}PASS${NC}: summary includes architect agent"
    PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC}: summary missing architect agent"
    FAIL=$((FAIL + 1))
fi

if echo "$SUMMARY_OUTPUT" | grep -q "pr-review-toolkit"; then
    echo -e "  ${GREEN}PASS${NC}: summary includes review agents"
    PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC}: summary missing review agents"
    FAIL=$((FAIL + 1))
fi

# --- Test 13: session_cleanup archives ---
echo ""
echo "${YELLOW}Test 13: session_cleanup.sh archives session${NC}"

./scripts/workflow/session_cleanup.sh > /dev/null 2>&1
assert_file_not_exists ".session/manifest.json" ".session/ cleaned"

ARCHIVE_COUNT=$(ls -d .session_archive/*/ 2>/dev/null | wc -l | tr -d ' ')
if [ "$ARCHIVE_COUNT" -ge 1 ]; then
    echo -e "  ${GREEN}PASS${NC}: session archived to .session_archive/"
    PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC}: no archive created"
    FAIL=$((FAIL + 1))
fi

# --- Test 14: Non-workflow Bash commands pass through ---
echo ""
echo "${YELLOW}Test 14: Non-commit Bash commands not blocked${NC}"

EXIT_CODE=0
echo '{"tool_name":"Bash","tool_input":{"command":"ls -la"}}' | \
    python3 "$HOOK_DIR/workflow_gate.py" 2>/dev/null || EXIT_CODE=$?
assert_exit 0 $EXIT_CODE "ls -la not blocked"

# --- Test 15: Parallel worktree isolation ---
echo ""
echo "${YELLOW}Test 15: Parallel worktree isolation — cd prefix resolves to correct .session/${NC}"

WORKTREE_A="$TMPDIR/worktree-a"
WORKTREE_B="$TMPDIR/worktree-b"
mkdir -p "$WORKTREE_A/.session" "$WORKTREE_B/.session"

# Worktree A: has architect + pytest
(cd "$WORKTREE_A" && "$TMPDIR/scripts/workflow/session_init.sh" standard > /dev/null 2>&1) || true
echo '[{"type":"agent_dispatch","subagent_type":"feature-dev:code-architect","agent_id":"wt-a-001","timestamp":"2026-03-16T10:00:00Z"}]' > "$WORKTREE_A/.session/agents.json"
echo '[{"type":"pytest","passed":5,"failed":0,"exit_code":0,"timestamp":"2026-03-16T10:01:00Z"}]' > "$WORKTREE_A/.session/events.json"

# Worktree B: has manifest but NO architect
cp "$WORKTREE_A/.session/manifest.json" "$WORKTREE_B/.session/manifest.json"

# Commit in worktree A (has architect) should PASS
EXIT_CODE=0
echo "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"cd $WORKTREE_A && git commit -m test\"}}" | \
    python3 "$HOOK_DIR/workflow_gate.py" 2>/dev/null || EXIT_CODE=$?
assert_exit 0 $EXIT_CODE "Worktree A commit allowed (has architect)"

# Commit in worktree B (no architect) should BLOCK
EXIT_CODE=0
echo "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"cd $WORKTREE_B && git commit -m test\"}}" | \
    python3 "$HOOK_DIR/workflow_gate.py" 2>/dev/null || EXIT_CODE=$?
assert_exit 2 $EXIT_CODE "Worktree B commit blocked (no architect)"

# Event recorded to correct worktree
echo "{
  \"tool_name\": \"Bash\",
  \"tool_input\": {\"command\": \"cd $WORKTREE_B && python -m pytest tests/ -v\"},
  \"tool_response\": {\"stdout\": \"3 passed in 1.2s\", \"stderr\": \"\", \"exit_code\": 0}
}" | python3 "$HOOK_DIR/agent_recorder.py" 2>/dev/null

assert_file_exists "$WORKTREE_B/.session/events.json" "Pytest event recorded in worktree B (not main repo)"
if [ -f "$WORKTREE_B/.session/events.json" ]; then
    assert_contains "$WORKTREE_B/.session/events.json" '"type": "pytest"' "Pytest recorded in correct worktree"
fi

# --- Results ---
echo ""
echo "================================================="
echo -e "Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}"
echo "================================================="

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
