---
name: create-issue
description: GitHub issue creation, epic creation with audit-first workflow, project linking, and closing workflow
---

# Create Issue Skill

## When to Create Issues

- Bug discovered during testing
- Issue found during code review
- Edge case or error handling gap
- TODO/FIXME that represents real work
- Regression during integration testing
- Performance issues

**Create IMMEDIATELY when discovered.** Don't wait.

## Bug Issue Template

```bash
gh issue create --title "Bug: [Brief description]" \
  --body "## Description
[Detailed description]

## Steps to Reproduce
1. [Step 1]
2. [Step 2]

## Expected Behavior
[What should happen]

## Actual Behavior
[What actually happens]

## Discovery Context
Found during: [testing/code review/development]
Related file(s): [file paths]"
```

## Enhancement Issue Template

```bash
gh issue create --title "Enhancement: [Brief description]" \
  --body "## Description
[What needs improvement]

## Current Behavior
[How it works now]

## Proposed Change
[What should change]"
```

## Link to Projects

```bash
# List projects
gh project list

# Add to project
gh project item-add <PROJECT_NUMBER> --owner @me --url <ISSUE_URL>
```

| Project | When to Use |
|---------|-------------|
| `API` | FastAPI routes, auth, rate limiting, middleware |
| `Infrastructure` | GCP, Cloud Run, Alembic migrations, Docker |
| `Frontend` | React, Vite, TailwindCSS, Shadcn components |
| `Worker` | Background jobs, queue mechanics, job types |
| `Performance` | Caching, query optimization, storage throughput |

## Add Labels

```bash
gh issue edit <NUMBER> --add-label "bug"
gh issue edit <NUMBER> --add-label "enhancement"
```

## Close After Implementation

**Always close with a comment:**

```bash
gh issue close <NUMBER> --comment "Completed in commit <SHA> - <brief description>"
```

## Best Practices

- Create issue IMMEDIATELY when discovered
- Reference in commits: `fix: Description (#123)`
- Link related issues: "Related to #122" or "Blocks #124"
- If fixing same session, still create first for traceability

## Implementation Issues (CRITICAL)

For features/enhancements, create **self-contained specs** so any future Claude session can implement without context:

**Required sections:**

```markdown
## Context
- Parent epic: #NNN
- Depends on: #NNN (must be merged first)
- Blocks: #NNN

## Files to Modify
- `apps/api/routes/jobs.py:45-67` — Add new route handler
- `packages/py_common/py_common/schemas/jobs.py:12` — Add response schema

## Implementation Details

### CURRENT (apps/api/routes/jobs.py:45)
```python
@router.get("/{job_id}")
async def get_job(job_id: UUID, ...):
    ...
```

### NEW
```python
@router.get("/{job_id}/result")
async def get_job_result(job_id: UUID, ...):
    ...
```

## Imports to Add
- `from py_common.schemas import JobResultRead`

## Verification Steps
```bash
docker compose exec api pytest apps/api/tests/test_jobs.py -v -k test_get_result
docker compose exec api ruff check apps/api/routes/jobs.py
```

## Acceptance Criteria
- [ ] Returns 200 with output_payload when job succeeded
- [ ] Returns 404 when job not found
- [ ] Returns 409 when job still running

## Anti-patterns (Do NOT)
- Do NOT return raw dict — use Pydantic schema
- Do NOT skip auth check
- Do NOT modify the existing GET /{job_id} route
```

**Why:** Claude sessions compact after ~50 messages. Vague issues lead to improvised solutions that break conventions. Self-contained specs survive context loss.

---

## Epic Creation (Audit-First Workflow)

Epics group multiple related issues into a single trackable unit. The key difference from single issues: **epics require an audit step before the issue list is finalized.** This prevents the failure mode where an agent executes the filed issues but misses systemic problems that were discovered but never tracked.

### When to Create Epics

- Multi-issue feature work (3+ related changes)
- Bug clusters where fixing one may reveal others
- Design system changes, refactors, or audit-driven work
- Any work where "look at this area" may surface more issues than originally reported

### Two-Phase Workflow

Epics are created in two phases with a mandatory human review between them.

```
PHASE 1: DRAFT ──────────────────────────────────
  1. User provides: bug reports, feature request, or area to audit
  2. Agent runs scoped audit (read affected files, identify ALL problems)
  3. Agent creates DRAFT epic issue with structured findings
  4. *** HUMAN REVIEW GATE ***
  User reviews draft, approves/removes/defers items
                    │
                    ▼
PHASE 2: FINALIZE ───────────────────────────────
  1. Create individual issues from approved findings
  2. Tag and link all issues to the epic
  3. Create deferred issues for explicitly deferred items
  4. Epic checklist becomes the scope contract
```

### Phase 1: Draft Epic

Run a scoped audit of the affected area, then create a draft epic issue.

**Audit step:** Read the files related to the user's request. Don't just list the problems the user reported — look for systemic issues in the same area. The goal is to surface everything NOW so nothing gets discovered mid-implementation and lost as a comment.

```bash
gh issue create --title "Epic: [Brief description]" \
  --label "epic" \
  --body "$(cat <<'EOF'
## Goal
[What this epic achieves when complete — this is the definition of done]

## Mode
<!-- fixed-scope: only filed issues are in scope -->
<!-- discovery: Phase 0 audit may expand scope within budget -->
**fixed-scope** | **discovery**

## Reported Issues (from user)
- [ ] [Description of reported bug/feature 1]
- [ ] [Description of reported bug/feature 2]

## Audit Findings (from code review)
- [ ] [Systemic issue found during audit 1]
- [ ] [Systemic issue found during audit 2]

## Proposed Deferrals
- [Issue that's related but out of scope — will become a tracked issue]

---
**Status: DRAFT — awaiting human review before issues are filed.**
Approve items → agent files individual issues.
Remove items → they won't be implemented.
Move to Deferrals → agent files as deferred issues for future work.
EOF
)"
```

**Then STOP.** Tell the user:

```
Epic draft created: <URL>

Please review the checklist:
  - Check/uncheck items to approve or remove
  - Move anything to "Proposed Deferrals" that's out of scope
  - Edit descriptions if they're wrong or unclear

When you're satisfied, tell me to finalize.
```

### Phase 2: Finalize Epic

After the user reviews and approves the draft:

**Step 1: Create individual issues for each approved item.**

```bash
# For each checked item in "Reported Issues" and "Audit Findings":
gh issue create --title "[Type]: [Brief description]" \
  --label "epic/<epic-slug>" \
  --body "## Description
[Detailed description from audit]

## Parent Epic
Part of #<epic-number>

## Files Affected
[List from audit]

## Acceptance Criteria
[Specific, testable criteria]"
```

Use the Implementation Issues format (above) for each — self-contained specs.

**Step 2: Create deferred issues.**

```bash
# For each item in "Proposed Deferrals":
gh issue create --title "[Type]: [Brief description]" \
  --label "audit-finding" \
  --label "deferred" \
  --body "## Description
[What was found]

## Discovery Context
Found during audit for epic #<epic-number>.
Deferred because: [reason from user]

## Files Affected
[List from audit]"
```

Deferred issues are **never silent.** They exist in the tracker, they're labeled, and they're discoverable via `gh issue list --label deferred`.

**Step 3: Update the epic with issue links.**

```bash
# Replace the checklist items with linked issue references:
gh issue edit <epic-number> --body "$(cat <<'EOF'
## Goal
[Same as draft]

## Mode
**fixed-scope** | **discovery**

## Issues
- [ ] #101 — Fix dark mode toggle regression
- [ ] #102 — Button brand color token
- [ ] #103 — Settings container tokens

## Deferred (tracked separately)
- #104 — Settings page full redesign
- #105 — Accessibility audit for dark mode

---
**Status: ACTIVE — issues filed, ready for implementation.**
EOF
)"
```

The epic's checklist is now the **scope contract.** `/parallel-implementation` reads it at Phase 0. `/worktree-pr` validates against it at Phase B¾.

### Audit-Finding Issues (Auto-Created by Phase 0)

During `/parallel-implementation` Phase 0½, the architect may discover additional problems beyond the epic's issue list. These are auto-created as issues:

```bash
gh issue create --title "Audit: [Brief description]" \
  --label "audit-finding" \
  --label "needs-triage" \
  --body "## Description
[What was found]

## Discovery Context
Found during Phase 0 of epic #<epic-number>.
The architect identified this while analyzing files for the implementation plan.

## Files Affected
[List from architect output]

## Recommendation
[Fix now (directly related to epic work) | Defer to future epic]"
```

These issues are **not automatically added to the epic.** The human decides during the Phase 0½ gate whether to expand scope or defer.

### Labels Reference

| Label | Meaning |
|-------|---------|
| `epic` | Tracking issue for a group of related issues |
| `epic/<slug>` | Links an issue to its parent epic |
| `audit-finding` | Discovered during code audit, not originally reported |
| `needs-triage` | Awaiting human decision on priority/scope |
| `deferred` | Explicitly out of scope for current epic, tracked for future |

### Quick Commands

```bash
# View all untriaged audit findings
gh issue list --label "audit-finding" --label "needs-triage"

# View all deferred work
gh issue list --label "deferred"

# View epic progress (checklist in issue body)
gh issue view <epic-number>

# View all issues for an epic
gh issue list --label "epic/<slug>"
```
