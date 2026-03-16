#!/usr/bin/env bash
# session_init.sh — Initialize .session/ with a manifest of required events
#
# Usage:
#   ./scripts/workflow/session_init.sh epic       # Epic work: full Phase 0 + 0½ + B¾ + review
#   ./scripts/workflow/session_init.sh standard   # Single issue: Phase 0 + review
#   ./scripts/workflow/session_init.sh            # Defaults to standard
#
# Creates .session/manifest.json listing what the workflow_gate hook will enforce.
# Clears any stale markers from previous sessions.

set -euo pipefail

SESSION_DIR=".session"
MANIFEST="$SESSION_DIR/manifest.json"
TASK_TYPE="${1:-standard}"

# Clean slate — remove stale session data
if [ -d "$SESSION_DIR" ]; then
    # Archive previous session if it had data
    if [ -f "$SESSION_DIR/manifest.json" ]; then
        ARCHIVE_DIR=".session_archive/$(date -u +%Y%m%dT%H%M%SZ)"
        mkdir -p "$ARCHIVE_DIR"
        cp -r "$SESSION_DIR"/* "$ARCHIVE_DIR"/ 2>/dev/null || true
        echo "Previous session archived to $ARCHIVE_DIR"
    fi
    rm -rf "$SESSION_DIR"
fi

mkdir -p "$SESSION_DIR"

# Write manifest based on task type
case "$TASK_TYPE" in
    epic)
        cat > "$MANIFEST" << 'MANIFEST'
{
  "task_type": "epic",
  "created_at": "TIMESTAMP",
  "required_agents": [
    {
      "phase": "phase_0",
      "subagent_type_pattern": "feature-dev:code-architect",
      "description": "Architect analysis with scope findings"
    },
    {
      "phase": "phase_c_half",
      "subagent_type_pattern": "pr-review-toolkit:.*",
      "description": "At least one review agent in Phase C½"
    }
  ],
  "required_events": [
    {
      "phase": "phase_3",
      "event_type": "pytest",
      "description": "Tests must pass before commit"
    },
    {
      "phase": "phase_c_half",
      "event_type": "external_review_check",
      "description": "External reviewer comments must be checked"
    }
  ],
  "gates": {
    "git_commit": {
      "require_agents": ["phase_0"],
      "require_events": ["phase_3:pytest"]
    },
    "final_summary": {
      "require_agents": ["phase_0", "phase_c_half"],
      "require_events": ["phase_c_half:external_review_check"]
    }
  }
}
MANIFEST
        ;;

    standard|*)
        cat > "$MANIFEST" << 'MANIFEST'
{
  "task_type": "standard",
  "created_at": "TIMESTAMP",
  "required_agents": [
    {
      "phase": "phase_0",
      "subagent_type_pattern": "feature-dev:code-architect",
      "description": "Architect analysis"
    },
    {
      "phase": "phase_c_half",
      "subagent_type_pattern": "pr-review-toolkit:.*",
      "description": "At least one review agent in Phase C½"
    }
  ],
  "required_events": [
    {
      "phase": "phase_3",
      "event_type": "pytest",
      "description": "Tests must pass before commit"
    },
    {
      "phase": "phase_c_half",
      "event_type": "external_review_check",
      "description": "External reviewer comments must be checked"
    }
  ],
  "gates": {
    "git_commit": {
      "require_agents": ["phase_0"],
      "require_events": ["phase_3:pytest"]
    },
    "final_summary": {
      "require_agents": ["phase_0", "phase_c_half"],
      "require_events": ["phase_c_half:external_review_check"]
    }
  }
}
MANIFEST
        ;;
esac

# Replace TIMESTAMP placeholder with actual time
if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/TIMESTAMP/$(date -u +%Y-%m-%dT%H:%M:%SZ)/" "$MANIFEST"
else
    sed -i "s/TIMESTAMP/$(date -u +%Y-%m-%dT%H:%M:%SZ)/" "$MANIFEST"
fi

echo "Session initialized: $TASK_TYPE"
echo "Manifest: $MANIFEST"
echo "Gates will enforce: $(python3 -c "
import json
m = json.load(open('$MANIFEST'))
for gate, reqs in m['gates'].items():
    agents = ', '.join(reqs.get('require_agents', []))
    events = ', '.join(reqs.get('require_events', []))
    print(f'  {gate}: agents=[{agents}] events=[{events}]')
")"
