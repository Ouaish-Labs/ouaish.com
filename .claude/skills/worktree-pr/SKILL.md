---
name: worktree-pr
description: Create a git worktree for isolated feature work, run /parallel-implementation inside it, then submit as a PR. Use when implementing features that should not land directly on main.
---

# Worktree PR Skill

Isolated feature development: worktree → plan → implement → test → PR → cleanup.

All planning, implementation, testing, and commit is delegated to `/parallel-implementation`. This skill owns the **lifecycle** around it — including the review loop after the PR is posted.

**Announce at start:** "I'm using the worktree-pr skill to implement this in an isolated worktree and submit as a PR."

## Required Workflow

```
PHASE A: SETUP WORKTREE ────────────────────────
  1. Derive branch name + fetch issue context
  2. Create worktree at ~/Developer/<branch-name>
     (or resume existing — reconstruct state from git log + TODO.md)
  3. Verify auth, run project setup
                    │
                    ▼
PHASE B: IMPLEMENT (/parallel-implementation) ──
  Phases 0–3 run normally inside the worktree
  (architect → scope gate → plan → waves → verify + commit)
                    │
                    ▼
PHASE B½: CONFLICT CHECK ──────────────────────
  Fetch origin/main, check if branch is behind
  If behind: present merge/rebase/ignore options
  After merge/rebase: re-run tests
                    │
                    ▼
PHASE B¾: COMPLETENESS CHECK (if epic) ────────
  Fetch epic checklist from GitHub
  Compare closed issues against checklist
  Gaps → must be deferred-as-issues or fixed
  *** BLOCKS PR if unchecked items have no resolution ***
                    │
                    ▼
PHASE C: SUBMIT PR ─────────────────────────────
  1. Push branch to origin
  2. Create PR via gh pr create (--draft if requested)
  3. Report PR URL to user
                    │
                    ▼
PHASE C½: AUTOMATED REVIEW LOOP ──────────────
  Round 1: Review (fresh Sonnet) → Fix → push
  Round 2: Re-review (resumed Opus) → Fix (if needed) → push
  Round 3: Re-review (resumed Opus) → STOP (summary only)
  Early exit: any round with 0 findings → APPROVED
  NEVER use Haiku for any review task
                    │
                    ▼
PHASE D: CLEANUP (after merge) ─────────────────
  User runs: git worktree remove ~/Developer/<branch-name>
  Or invokes this skill with "cleanup" argument
```

---

## Phase A: Setup Worktree

### 1. Derive Branch Name + Gather Context

From user input, derive a branch name:

| Input | Branch Name |
|-------|-------------|
| Issue number (#500) | `feature/issue-500-<slug>` |
| Description ("add hotel NOI") | `feature/add-hotel-noi` |
| User specifies branch | Use exactly as given |

Slug rules: lowercase, hyphens, no special chars, max 50 chars.

**If an issue number is provided, fetch it immediately:**

```bash
gh issue view <number> --json title,body,labels,assignees
```

Store the issue title and body — this becomes the requirements input for `/parallel-implementation` Phase 0 (code-architect) and Phase 1 (planning). Include it verbatim in agent prompts so the architect and planners work from real requirements, not a paraphrased summary.

### 2. Verify Starting Point

```bash
# MUST verify current branch — gitStatus snapshot is stale
git branch --show-current

# Ensure main is up to date
git pull origin main
```

### 3. Create Worktree

**Location: `~/Developer/<branch-name>`** — NEVER inside the project folder. The `workflow_gate.py` hook blocks `git worktree add` if the target path is not under `~/Developer/`.

```bash
# Create worktree with new branch off main
git worktree add ~/Developer/<branch-name> -b <branch-name> main

# Verify it exists
ls ~/Developer/<branch-name>
```

**If worktree already exists at that path — resume detection:**

Don't just ask "resume or rename?" — reconstruct state from what's on disk:

```bash
cd ~/Developer/<branch-name>

# What work has been done?
git log main..<branch-name> --oneline

# What does /checkpoint think is left?
cat TODO.md 2>/dev/null || echo "No TODO.md found"

# Any uncommitted work?
git status --short
```

Report a structured summary:

```
Found existing worktree at ~/Developer/<branch-name>

  Commits: 3 (wave 1 complete, wave 2 complete)
  TODO.md: Wave 3 remaining — "add integration tests for NOI calc"
  Uncommitted: 2 modified files (api/services/noi.py, api/tests/test_noi.py)

Options:
  1. Resume from where we left off (continue wave 3)
  2. Start fresh (discard worktree, recreate from main)
  3. Pick a different branch name
```

- **Option 1:** Skip the rest of Phase A, go directly to Phase B at the appropriate wave
- **Option 2:** Requires explicit confirmation. `git worktree remove`, then recreate.
- **Option 3:** Ask for new name, create fresh worktree

**Never delete an existing worktree without confirmation.**

### 4. Verify GitHub Auth

```bash
cd ~/Developer/<branch-name>
gh auth status 2>&1
```

If auth fails, tell the user to fix their GitHub authentication for this directory. Do not prescribe a specific fix — auth setups vary across projects and developers.

### 5. Project Setup

Check for and run your project's setup mechanism:

1. If `CLAUDE.md` documents a setup command → run it
2. If `Makefile` has a `setup` or `install` target → run it
3. If `package.json` exists → `npm install`
4. If `requirements.txt` or `pyproject.toml` exists → create venv + install
5. If `docker-compose.yml` exists → check if services need starting

Report what you found and ran. If nothing is documented, ask the user.

### 6. Verify Clean Baseline

```bash
# Run a quick smoke test appropriate for the project
# (e.g., compile check, import test, or lint)

# Git status should be clean (only untracked like venv, node_modules)
git status --short
```

### 7. Initialize Session Recorder

Initialize the session recorder for workflow gate enforcement:

```bash
cd ~/Developer/<branch-name>

# Detect task type from branch name
if echo "<branch-name>" | grep -qi "epic"; then
  ./scripts/workflow/session_init.sh epic
else
  ./scripts/workflow/session_init.sh standard
fi
```

This creates `.session/manifest.json` with required phases. From this point:
- `agent_recorder.py` (PostToolUse hook) automatically tracks every Agent dispatch and key Bash events
- `workflow_gate.py` (PreToolUse hook) will block `git commit`, `gh pr comment "Final Summary"`, and `gh pr merge` if required phases/CI are not satisfied
- `agent_gate.py` (PreToolUse hook) will block review agents using Haiku, re-dispatches that should be resumes, fixer agents dispatched before findings are posted, and agents missing worktree cd instructions

**If `scripts/workflow/session_init.sh` doesn't exist** (project hasn't installed workflow scripts), skip this step. The workflow gate is backward compatible — no manifest means no enforcement.

Report: "Worktree ready at `~/Developer/<branch-name>`. Session initialized. Starting implementation."

---

## Phase B: Implement

**Invoke `/parallel-implementation` with full context.** All work happens inside the worktree directory.

### Subagent working directory — CRITICAL

`/parallel-implementation` dispatches subagents via the Agent tool. **Subagents inherit the main session's CWD, which is the main repo — NOT the worktree.** Every agent prompt MUST include an explicit `cd` instruction:

```
# In EVERY agent prompt, prepend:
"IMPORTANT: Your working directory is ~/Developer/<branch-name>/. Run `cd ~/Developer/<branch-name>` before any file operations. All file paths are relative to this directory, NOT the main repo."
```

**Failure mode if you skip this:** Agents edit files in the main repo. Tests pass (against main's code), but the worktree has no changes. You push an empty branch.

### Issue context for agents

If an issue was fetched in Phase A step 1, include the issue body in:
- The **code-architect** prompt (Phase 0) — so it understands requirements
- The **plan** (Phase 1) — as a "Requirements" section above the wave table
- **Agent prompts** that implement core logic — so they understand the "why"

Do NOT include the raw issue body in mechanical/haiku tasks (import updates, renames).

### Other integration points

- **Commits land on the feature branch**, not main
- `/parallel-implementation` Phases 0–3 run exactly as documented
- Phase 3's commit step commits to the feature branch (automatic — we're in the worktree)

### Checkpoint discipline

After each wave in `/parallel-implementation`, commit to the feature branch:

```bash
cd ~/Developer/<branch-name>
git add <specific-files>
git commit -m "wave N: <description>"
```

This protects against context compaction losing agent work.

---

## Phase B½: Conflict Check

After `/parallel-implementation` Phase 3 completes but **before pushing**, check if main has advanced:

```bash
cd ~/Developer/<branch-name>
git fetch origin main

# Check if our branch includes all of origin/main
git merge-base --is-ancestor origin/main HEAD
```

**If exit code is 0:** Main hasn't advanced (or we already include it). Proceed to Phase C.

**If exit code is 1:** Main has new commits. Report what changed:

```bash
# Show what's new on main since we branched
git log HEAD..origin/main --oneline
```

Then present options — **do NOT auto-rebase or auto-merge:**

```
Main has advanced since this branch was created:

  <N> new commits on main:
    abc1234 fix: tenant isolation in export
    def5678 feat: add hotel cap rate column

Options:
  1. Merge origin/main into this branch (preserves wave commit history)
  2. Rebase onto origin/main (cleaner history, rewrites commits)
  3. Ignore (GitHub will show conflicts on the PR if any exist)
```

- **Option 1 (merge):** `git merge origin/main`. If conflicts arise, resolve and commit. Re-run tests.
- **Option 2 (rebase):** `git rebase origin/main`. If conflicts arise, resolve. Re-run tests. **Warning:** rewrites commit hashes.
- **Option 3 (ignore):** Proceed to Phase C. GitHub will flag conflicts on the PR page. Fine for small divergences.

After merge/rebase: **re-run the test suite** before proceeding. The merge may have introduced incompatibilities.

---

## Phase B¾: Completeness Check (Epic Only)

**Skip this phase if:** There is no parent epic (single-issue or ad-hoc task). Go directly to Phase C.

**Run this phase if:** The work is linked to an epic. The epic number should have been fetched in Phase A step 1.

This phase prevents the failure mode where a PR is submitted but doesn't fully resolve the epic's stated goal. It validates against the epic's issue checklist — it does NOT re-audit the codebase.

### Step 1: Fetch Epic State

```bash
# Get the epic body (contains the issue checklist)
gh issue view <epic-number> --json body,title -q '.body'

# Get status of all linked issues
gh issue list --label "epic/<epic-slug>" --json number,title,state --jq '.[] | "\(.number) \(.state) \(.title)"'
```

### Step 2: Build Coverage Report

Compare the epic checklist against the implementation:

```
Phase B¾ — Completeness Check for Epic #<number>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Epic: "<epic title>"

Issue Status:
  ✅ #101 — Fix dark mode toggle (closed by this PR)
  ✅ #102 — Button brand color token (closed by this PR)
  ❌ #103 — Settings container tokens (still open)
  ✅ #106 — Theme provider dark mode var (closed by this PR)

Deferred (tracked separately):
  📋 #107 — Text base color (deferred, has own issue)
  📋 #108 — Sidebar gradient (deferred, has own issue)

Coverage: 3/4 in-scope issues resolved (75%)
```

### Step 3: Gate Decision

| Coverage | Action |
|----------|--------|
| **100% in-scope issues closed** | Pass. Proceed to Phase C. |
| **<100% but unchecked items have open issues** | Present to human. Options: fix now, defer-as-issue, or proceed anyway. |
| **Unchecked items with NO issue and NO deferral** | **Block.** This is the exact failure case — work that was scoped but silently dropped. Must be resolved before PR. |

If items are missing and need to be deferred:

```bash
# Create deferred issue for each unresolved item
gh issue create --title "Deferred: [Description from epic checklist]" \
  --label "deferred" \
  --label "audit-finding" \
  --body "## Description
[Item from epic checklist that wasn't completed]

## Context
Deferred from epic #<epic-number> during Phase B¾ completeness check.
PR: #<pr-number-if-known> (or 'pending')
Reason: [human's reason for deferring]

## Original Epic
Part of #<epic-number>"
```

After deferred issues are created, update the epic checklist to reflect the deferral.

### Step 4: Confirm and Proceed

```
Completeness check passed:
  Resolved: 3 issues
  Deferred: 1 issue → #109 (tracked)
  Dropped: 0

Proceeding to Phase C (submit PR).
```

**The rule: nothing is silently dropped.** Every epic checklist item is either closed by the PR, deferred to a tracked issue, or explicitly approved by the human to skip.

---

## Phase C: Submit PR

After completeness check passes (or is skipped for non-epic work):

### 1. Verify Branch State

```bash
# Confirm we're on the feature branch
git branch --show-current

# Confirm all changes are committed
git status --short
# Should show nothing (or only untracked like .venv/)

# Review what we're about to PR
git log main..<branch-name> --oneline
```

### 2. Push to Origin

```bash
git push -u origin <branch-name>
```

**Wait for push to complete.** Report any errors.

### 3. Create PR

If an issue was fetched in Phase A, include `Closes #<number>` in the body. Use the issue title to inform (but not copy verbatim) the PR title.

**Default: ready PR.** The work has been through architect → plan → waves → verify → test → commit. It's complete.

**Use `--draft` only when the user explicitly requests it** (e.g., "create as draft", "I want to review before CI runs"). Draft PRs skip CI review workflows and don't notify reviewers.

```bash
# Ready PR (default)
gh pr create --title "<concise title under 70 chars>" --body "$(cat <<'EOF'
## Summary
<2-4 bullets describing what changed and why>

## Changes
<list of key files modified/created>

## Test Plan
- [ ] Unit tests pass
- [ ] Typecheck passes
- [ ] Lint passes
- [ ] <any task-specific verification>

Closes #<issue-number>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"

# Draft PR (only when user requests --draft)
gh pr create --draft --title "<title>" --body "$(cat <<'EOF'
...same template...
EOF
)"
```

If created as draft, remind the user: `gh pr ready <number>` to convert when ready for CI + review.

### 4. Post Workflow Compliance Report (mandatory)

The compliance report is generated by a script from `.session/` data — **not written by the model.** The script reads the agent dispatch records and event logs that the hooks wrote automatically.

```bash
cd ~/Developer/<branch-name>
./scripts/workflow/session_summary.sh <pr-number> --post
```

This reads `.session/agents.json` and `.session/events.json` (written by `agent_recorder.py` hook throughout the session) and posts the compliance comment to the PR. If Phase 0 wasn't dispatched, the comment shows ❌. If review agents weren't dispatched, the comment shows ❌. The model doesn't choose what to report — the script reports what actually happened.

**If `scripts/workflow/session_summary.sh` doesn't exist** (project hasn't installed workflow scripts), fall back to manually posting a compliance comment with the data you have.

**If the script shows ❌ for any phase, address it before proceeding to Phase C½.**

> **Gate note:** The `agent_gate.py` hook will block fixer agent dispatch if no round comment has been posted to the PR yet. Ensure the Step 1 `gh pr comment` has completed before dispatching the fixer in Step 2.

### 5. Report to User

```
PR created: <URL>
Branch: <branch-name>
Worktree: ~/Developer/<branch-name>

To clean up after merge:
  git worktree remove ~/Developer/<branch-name>
  git branch -d <branch-name>
```

### 6. CI Monitoring

After push, check CI status per CLAUDE.md rules:

```bash
# Wait a moment for CI to trigger, then check
gh run list --branch <branch-name> --limit 3
```

Report CI status. On failure: `gh run view <id> --log-failed`.

After reporting the PR URL, proceed immediately to Phase C½.

---

## Phase C½: Automated Review Loop

After the PR is posted, an automated review loop catches issues that wave gates and pre-commit hooks miss — dead code, silent failures, logic inversions, naming inconsistencies.

### Hybrid Model Strategy

| Round | Dispatch | Model | Rationale |
|-------|----------|-------|-----------|
| **1** | Fresh agents | `model="sonnet"` | No prior context. Sees code cold. Sonnet sufficient for initial review. |
| **2+** | Resume Round 1 agents | Inherits Opus | Natural resolution tracking — agent remembers its own findings. |

**Why this works:**
- **Round 1 fresh:** The coding agent is anchored to its own reasoning. A fresh reviewer sees the code cold and catches ~20-30% more issues.
- **Round 2+ resume:** Review agents didn't *write* the code — the contamination concern doesn't transfer. A resumed agent naturally knows "I flagged X, the fixer rebutted with Y" without needing synthetic prior-round context.

**NEVER use Haiku for any review task.** Model tier is determined by the type of reasoning, not the size of the input.

### Round Limits

| Round | Review runs? | Fixer runs? |
|-------|-------------|-------------|
| 1 | Yes (fresh, Sonnet) | Yes (if findings) |
| 2 | Yes (resumed, Opus) | Yes (if findings) |
| 3 | Yes (resumed, Opus) | **No** — summary only, STOP |

**Early exit:** If any review round returns zero findings → APPROVED, skip to Final Summary.

### Step 0: Check for External Review

```bash
# Phase C½ is additive — it runs alongside, not instead of, human review
gh pr view <number> --json reviewRequests -q '.reviewRequests'
```

Report any required reviewers. Phase C½ does not replace human review.

### Step 1: Dispatch Review Agents (Round 1)

Get the PR diff, then dispatch sub-agents in parallel:

```bash
gh pr diff <number>
```

| Sub-agent | When | Dispatch mode |
|-----------|------|---------------|
| `pr-review-toolkit:code-reviewer` | Always | Parallel |
| `pr-review-toolkit:silent-failure-hunter` | Always | Parallel |
| `pr-review-toolkit:pr-test-analyzer` | Always | Parallel |
| `pr-review-toolkit:type-design-analyzer` | If diff has new types (`class`, `TypedDict`, `@dataclass`) | Parallel |
| `pr-review-toolkit:comment-analyzer` | If diff has new docstrings or block comments | Parallel |

```
# Round 1 — fresh agents with explicit model="sonnet"
# Store the returned agent IDs for resuming in Round 2+
Agent(subagent_type="pr-review-toolkit:code-reviewer", model="sonnet",
      prompt="Review this PR diff for bugs, logic errors, dead code, naming. PR diff:\n<diff content>. Working directory: ~/Developer/<branch-name>/")

Agent(subagent_type="pr-review-toolkit:silent-failure-hunter", model="sonnet",
      prompt="Check this PR diff for silent failures and inadequate error handling. PR diff:\n<diff content>. Working directory: ~/Developer/<branch-name>/")

Agent(subagent_type="pr-review-toolkit:pr-test-analyzer", model="sonnet",
      prompt="Review test coverage for this PR. PR diff:\n<diff content>. Working directory: ~/Developer/<branch-name>/")
```

**Save the agent IDs** — you will resume these in Round 2+.

After all agents complete, aggregate findings and post to PR:

```bash
gh pr comment <number> --body "$(cat <<'EOF'
## Automated Review — Round 1

### Critical
- action_required: `file:line` — description [agent-name]

### Important
- action_required: `file:line` — description [agent-name]

### Optional
- noted: `file:line` — description [agent-name]

**Findings:** X critical, Y important, Z optional
**Status:** NEEDS_FIXES
*Round 1 of 3 — pr-review-toolkit*
EOF
)"
```

**If zero findings:** Post APPROVED comment and skip to Final Summary.

### Step 2: Fixer Agent

Dispatch a general-purpose agent to fix all findings:

```
Agent(subagent_type="general-purpose", model="sonnet",
      prompt="# Fix: Address Phase C½ Review Findings

## Working Directory
cd ~/Developer/<branch-name> before all operations.

## Findings to Fix
<paste the Critical and Important findings verbatim from review agents>

## Fix Approach
For each finding:
1. Locate the relevant code
2. Apply the minimal correct fix
3. Do not refactor surrounding code unless directly required

## Project Checks
After all fixes, run your project's lint, typecheck, and test commands.
Debugging budget: 3 failed attempts on the same check → STOP and report.

## When Done, Report
### Fixes Applied
- [finding summary] → [what was changed] → [verify result]

### Not Fixed (with reason)
- [finding summary] → [reason: false positive / needs human decision / persistent failure]

## Do NOT
- Fix Optional-severity findings
- Refactor code beyond the reported findings
- Stage or commit — the orchestrator handles git operations")
```

After the fixer agent completes, the orchestrator commits and pushes:

```bash
cd ~/Developer/<branch-name>
git add <fixed-files>
git commit -m "review: address Phase C½ round N findings"
git push
```

### Step 3: Re-review (Rounds 2+)

**Resume the Round 1 review agents** using their saved IDs. Do not dispatch fresh agents — resuming preserves memory of prior findings, making resolution tracking natural.

```
Agent(resume="<code-reviewer-agent-id>",
      prompt="Fixes have been applied and pushed. Review the updated PR diff:\n<full diff>\n\nFixer's response:\n<fixer comment>")

Agent(resume="<silent-failure-hunter-agent-id>",
      prompt="Fixes have been applied and pushed. Review the updated PR diff for remaining or new issues:\n<full diff>")
```

**Why resume works better:** The agent already knows what it flagged. It naturally distinguishes "fixed" vs "still present" vs "fix introduced new issue."

Pass the **full PR diff** (not just fix commits) — a fix may interact badly with original code.

### Step 4: Loop Control

```
round = 1
agent_ids = {}  # saved from Round 1 dispatches

while round <= 3:
    # Review
    if round == 1:
        agent_ids = dispatch review sub-agents (model="sonnet", full PR diff)
    else:
        resume agents using agent_ids (full PR diff + fixer response)

    aggregate findings, post to PR

    if APPROVED (zero findings):
        break

    if round < 3:
        dispatch fixer agent → commit → push

    round += 1

# Post Final Summary
```

### Step 5: Final Summary (with mandatory external review recheck)

Always posted, regardless of outcome. **Before writing the summary, run the external comment check and paste the result.** By this point, 2-10 minutes have passed since PR creation — enough time for external review bots to have commented.

```bash
# MANDATORY: Run this and paste the FULL JSON output into the summary
gh api repos/{owner}/{repo}/pulls/{number}/comments --jq '[.[] | {id, user: .user.login, body: .body[:100]}]'

# If the result is [] (empty) and less than 2 minutes have passed since PR creation:
sleep 30
# Then re-run the same command. One retry only — not a polling loop.
```

Then post the final summary with the external review data included:

```bash
gh pr comment <number> --body "$(cat <<'EOF'
## Review Complete — Final Summary

**Result:** APPROVED | NEEDS_HUMAN_REVIEW
**Rounds:** N of 3

### Resolution
- resolved: {count}
- still_open: {count}
- new_in_later_rounds: {count}

### External Review Check (Final)
**Comments found:** N (at <timestamp>)
**From:** <list usernames, e.g., gemini-bot, codex>
**Addressed:** <all addressed in round N / N unaddressed — details below>

<If unaddressed external comments exist, list them here>

### Unresolved Items (if any)
- `file:line` — description. Attempted fix: what was tried.

🤖 Reviewed with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Why the recheck is here and not in Round 1:** Round 1 starts immediately after PR creation — external bots haven't had time to comment. The Final Summary always runs (even on early APPROVED exit), and by this point enough time has passed. One recheck with a 30-second wait if empty. Not a polling loop.

**If external comments are found that weren't addressed:** Change the result to NEEDS_HUMAN_REVIEW and list the unaddressed comments.

### Failure Handling

| Failure | Action |
|---------|--------|
| **A review sub-agent errors or times out** | Re-dispatch that agent once. If it fails again, skip it and note in the final summary. |
| **All review agents fail** | Do not retry. Post a summary noting automated review could not complete. Do not block the PR. |
| **Fixer agent reports persistent failure (3 attempts)** | Accept finding as "not fixed". Add to deferred list in final summary with error details. |
| **`gh pr comment` fails** | Retry once with shortened body. If it fails again, report summary to user in conversation only. |
| **Two consecutive infrastructure failures** (push, gh CLI, worktree access) | Stop Phase C½. Report to user: what succeeded, what failed, and what manual steps remain. |

### What Phase C½ Does NOT Do

- **Replace human review** — it augments, not gates
- **Block the PR** — findings are fixed or noted, never left as blockers
- **Re-run the full test suite** — only runs checks relevant to fix commits
- **Review non-diff code** — agents review only what changed in this PR

---

## Phase D: Merge + Cleanup

### Merging

If the user asks to merge the PR, **run `gh pr merge` from the main repo, not the worktree.** The `--delete-branch` flag triggers a local `git checkout main`, which fails inside a worktree because `main` is already checked out in the main repo — but the remote merge completes silently, causing confusion.

```bash
# CORRECT: merge from the main repo directory
cd <main-repo-path>
gh pr merge <number> --merge --delete-branch

# WRONG: merging from worktree — remote merge succeeds but local cleanup fails
cd ~/Developer/<branch-name>
gh pr merge <number> --merge --delete-branch  # ← silent partial success
```

The `workflow_gate.py` hook independently enforces both rules:
- **CI gate:** blocks `gh pr merge` if any CI checks are failing or still running
- **Worktree gate:** blocks `gh pr merge` if the `cd` target is a worktree (`.git` is a file, not a directory)

NEVER suggest or attempt merge until ALL CI checks are green.

### Cleanup

When user requests cleanup (or after PR merges):

```bash
# Verify PR is merged
gh pr view <branch-name> --json state -q '.state'

# Archive session data for forensics
cd ~/Developer/<branch-name>
./scripts/workflow/session_cleanup.sh 2>/dev/null || true

# Remove worktree (from main repo)
cd <main-repo-path>
git worktree remove ~/Developer/<branch-name>

# Delete local branch
git branch -d <branch-name>

# Prune stale worktree refs
git worktree prune
```

**Never auto-cleanup.** Always wait for user to confirm or request it.

---

## Quick Reference

| Phase | What | Where |
|-------|------|-------|
| A | Create worktree + branch (or resume existing) | Main repo → `~/Developer/<branch>` |
| B | `/parallel-implementation` (scope gate → plan → waves → verify + commit) | Inside worktree |
| B½ | Conflict check against origin/main | Inside worktree |
| B¾ | Completeness check against epic checklist (epic only) | Inside worktree |
| C | Push + `gh pr create` (ready or `--draft`) | Inside worktree |
| C½ | Automated review loop (3 rounds max, Sonnet→Opus) | Inside worktree |
| D | Remove worktree + branch | Main repo |

## Error Handling

| Problem | Action |
|---------|--------|
| Worktree path already exists | Ask user: resume or rename |
| GitHub auth fails in worktree | Run `gh auth status`, tell user to fix their auth config |
| `git push` fails (no remote access) | Check GitHub auth: `gh auth status` |
| `gh pr create` fails | Verify `gh auth status`, check if branch already has a PR |
| CI fails after push | `gh run view <id> --log-failed`, fix in worktree, push again |
| Completeness check finds gaps (B¾) | Present to human: fix now, defer-as-issue, or skip. Never silently drop. |
| Tests fail in Phase B | Handled by `/parallel-implementation` wave gates |
| `gh pr merge` fails with worktree error | Merge succeeded on GitHub but local checkout failed. Run merge from main repo, not worktree. |
| Subagent edits wrong directory | Agent prompt missing `cd ~/Developer/<branch-name>`. Re-dispatch with explicit CWD. |
| Review sub-agent fails (C½) | Post partial findings. Note failed agent. Continue loop. |
| Fixer agent fails (C½) | Post failure comment. Set NEEDS_HUMAN_REVIEW. Skip to summary. |
| Review loop hits 3 rounds (C½) | Post final summary with unresolved items. Surface to user. |

## Integration

**Calls:**
- `/parallel-implementation` — Planning, implementation, testing (scope gate → plan → waves → verify)
- `/checkpoint` — Wave-level commits during implementation
- `pr-review-toolkit:code-reviewer` — Phase C½ review (Round 1: fresh Sonnet, Round 2+: resumed Opus)
- `pr-review-toolkit:silent-failure-hunter` — Phase C½ review (Round 1: fresh Sonnet, Round 2+: resumed Opus)
- `pr-review-toolkit:pr-test-analyzer` — Phase C½ review (Round 1: fresh Sonnet, Round 2+: resumed Opus)
- `pr-review-toolkit:type-design-analyzer` — Phase C½ conditional (new types, Sonnet minimum)
- `pr-review-toolkit:comment-analyzer` — Phase C½ conditional (new docs, Sonnet minimum)

**Called by:**
- User request: "implement X as a PR", "create a PR for issue #N"
- Any task where work should not land directly on main

**Replaces:**
- Manual worktree creation + ad-hoc implementation + manual PR creation
- The push step in `/parallel-implementation` Phase 3 (this skill handles push → PR instead)

## Common Mistakes

### Working in the wrong directory
- **Problem:** Running commands in main repo instead of worktree
- **Fix:** After Phase A, ALL work happens in `~/Developer/<branch-name>/`

### Forgetting to pull main before branching
- **Problem:** Feature branch starts from stale main, merge conflicts later
- **Fix:** Always `git pull origin main` before `git worktree add`

### Pushing after every commit
- **Problem:** Each push triggers ~4 CI workflows (batch pushes to reduce CI cost)
- **Fix:** Commit per wave during Phase B, push ONCE in Phase C

### Merging PR from inside the worktree
- **Problem:** `gh pr merge --delete-branch` from worktree silently merges on GitHub but fails locally (can't checkout `main` — already used by main repo). Looks like an error, but the merge already happened.
- **Fix:** Always `cd <main-repo-path>` before running `gh pr merge`

### Creating worktree inside project
- **Problem:** Violates project convention (memory: NEVER inside project folder)
- **Fix:** Always `~/Developer/<branch-name>`

## Red Flags

**Never:**
- Run `gh pr merge` from inside a worktree (merge from main repo instead)
- Create worktree inside the project directory
- Push before `/parallel-implementation` Phase 3 completes
- Auto-cleanup worktree without user confirmation
- Skip `/parallel-implementation` — it handles planning AND testing
- Push after every wave commit (batch pushes for CI cost)
- Skip Phase C½ for ready PRs — review catches what wave gates miss

**Always:**
- Verify `git branch --show-current` before and after worktree creation
- Run `/parallel-implementation` for ALL implementation work
- Commit after each wave (checkpoint discipline)
- Push once, then create PR
- Report PR URL and cleanup instructions
