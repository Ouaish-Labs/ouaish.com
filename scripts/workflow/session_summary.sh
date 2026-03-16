#!/usr/bin/env bash
# session_summary.sh — Generate PR compliance comment from session data
#
# Usage:
#   ./scripts/workflow/session_summary.sh <pr-number>
#   ./scripts/workflow/session_summary.sh <pr-number> --post   # Also post as PR comment
#
# Reads .session/agents.json and .session/events.json to generate
# the compliance report. The model doesn't write this — the script does.

set -euo pipefail

PR_NUMBER="${1:-}"
POST_FLAG="${2:-}"
SESSION_DIR=".session"

if [ -z "$PR_NUMBER" ]; then
    echo "Usage: session_summary.sh <pr-number> [--post]"
    exit 1
fi

if [ ! -d "$SESSION_DIR" ]; then
    echo "No session data found at $SESSION_DIR/"
    exit 1
fi

# Parse session data with Python (json parsing in bash is painful)
SUMMARY=$(python3 << 'PYEOF'
import json
from pathlib import Path
from datetime import datetime

session = Path(".session")
agents = json.loads((session / "agents.json").read_text()) if (session / "agents.json").exists() else []
events = json.loads((session / "events.json").read_text()) if (session / "events.json").exists() else []
manifest = json.loads((session / "manifest.json").read_text()) if (session / "manifest.json").exists() else {}

# Categorize agents by phase-relevant types
architect_agents = [a for a in agents if "code-architect" in a.get("subagent_type", "")]
review_agents = [a for a in agents if "pr-review-toolkit" in a.get("subagent_type", "")]

# Categorize events
pytest_events = [e for e in events if e.get("type") == "pytest"]
external_checks = [e for e in events if e.get("type") == "external_review_check"]
pr_created = [e for e in events if e.get("type") == "pr_created"]

# Build report lines
lines = []
lines.append("## Workflow Compliance (auto-generated)")
lines.append("")
lines.append("| Phase | Status | Evidence |")
lines.append("|-------|--------|----------|")

# Phase 0
if architect_agents:
    a = architect_agents[0]
    lines.append(f"| Phase 0 (architect) | ✅ dispatched | agent: `{a.get('agent_id', 'unknown')[:12]}` type: `{a['subagent_type']}` |")
else:
    lines.append("| Phase 0 (architect) | ❌ **NOT DISPATCHED** | no code-architect agent found in session |")

# Tests
if pytest_events:
    last = pytest_events[-1]
    passed = last.get("passed", 0)
    failed = last.get("failed", 0)
    status = "✅" if failed == 0 and passed > 0 else "❌"
    lines.append(f"| pytest | {status} {passed} passed, {failed} failed | exit: `{last.get('exit_code', '?')}` |")
else:
    lines.append("| pytest | ❌ **NOT RUN** | no pytest execution recorded |")

# Review agents
if review_agents:
    types = set(a["subagent_type"] for a in review_agents)
    lines.append(f"| Review loop (C½) | ✅ {len(review_agents)} agents dispatched | types: {', '.join(f'`{t}`' for t in types)} |")
else:
    lines.append("| Review loop (C½) | ❌ **NOT RUN** | no review agents dispatched |")

# External review check
if external_checks:
    last = external_checks[-1]
    lines.append(f"| External review check | ✅ checked | response length: {last.get('response_length', '?')} at `{last.get('timestamp', '?')[:19]}` |")
else:
    lines.append("| External review check | ❌ **NOT CHECKED** | no gh api .../comments call recorded |")

# Total agents
lines.append("")
lines.append(f"**Total agents dispatched:** {len(agents)}")
lines.append(f"**Total tracked events:** {len(events)}")
lines.append(f"**Task type:** {manifest.get('task_type', 'unknown')}")
lines.append(f"**Session started:** {manifest.get('created_at', 'unknown')}")
lines.append("")
lines.append("_Auto-generated from `.session/` by `session_summary.sh` — not model-written_")

print("\n".join(lines))
PYEOF
)

echo "$SUMMARY"

if [ "$POST_FLAG" = "--post" ]; then
    gh pr comment "$PR_NUMBER" --body "$SUMMARY"
    echo ""
    echo "Posted compliance report to PR #$PR_NUMBER"
fi
