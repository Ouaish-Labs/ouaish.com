---
name: parallel-implementation
description: Use when entering plan mode for any multi-file implementation task - enforces tiered model usage (Haiku/Sonnet/Opus) and wave-based parallel execution
---

# Parallel Implementation Skill

Execute multi-file implementations using tiered models, wave-based parallelization, and verified outcomes.

## Enforcement Layers

| Layer | What it catches | When it runs |
|-------|----------------|--------------|
| **PostToolUse hooks** (project-configured) | Syntax errors, undefined names | Every file edit, if configured |
| **Wave gates** (this skill) | Logic errors, missing imports, failing tests | Between each wave |
| **Pre-commit** (linters, type checkers) | Type errors, lint violations | At commit time (Phase 3) |
| **Test→Stage→Commit gate** (this skill) | Untested code reaching commits | Phase 3 — never stage before testing |
| **Review agents** (optional) | Dead code, silent failures, logic bugs | After commit — Phase C½ of /worktree-pr if used, otherwise run inline |

> If your project has PostToolUse syntax hooks configured in `.claude/settings.json`, they run automatically on every edit.

## Model Assignment

| Task Type | Model | Examples |
|-----------|-------|----------|
| **Orchestration** | Opus (you) | Planning, coordination, wave gates, final review |
| **Implementation** | Sonnet | Logic-heavy changes, new features, complex refactors |
| **Mechanical** | Haiku | Import updates, renames, simple edits, file moves |
| **Code review** | Sonnet minimum | PR review agents, re-review of fix commits, any judgment task |

> Model tier reflects the **type of reasoning required**, not the size of the input. A 3-line fix commit still requires judgment about correctness, intent, and side effects — that's Sonnet-minimum work. **Never use Haiku for any form of code review.**

## Required Workflow

```
PHASE 0: ARCHITECT ──────────────────────────────
  Dispatch feature-dev:code-architect
  Agent reads ALL affected files
  Returns: current state, imports, deps, wave grouping
  + Returns scope findings (problems beyond filed issues)
  YOU DO NOT SKIP THIS PHASE
                    │
                    ▼
PHASE 0½: SCOPE VALIDATION + DISCOVERY GATE ────
  Compare architect findings against epic issue list
  Directly related gaps → auto-create issues (audit-finding)
  Systemic findings → present to human for decision
  *** HUMAN GATE: confirm scope before Wave 1 ***
  (Skip if no parent epic — single-issue or ad-hoc task)
                    │
                    ▼
PHASE 1: PLAN (Opus) ───────────────────────────
  Use architect output to build plan
  Group into waves by dependency
  Assign model tiers + Verify commands
                    │
                    ▼
PHASE 2: EXECUTE WAVES ─────────────────────────
  Wave 1: Independent tasks (parallel)
  *** WAVE GATE: run Verify commands ***
  Wave 2: Dependent tasks (parallel)
  *** WAVE GATE: run Verify commands ***
  Wave N: Continue until complete
                    │
                    ▼
PHASE 3: VERIFY + COMMIT (MANDATORY) ──────────
  1. Run typecheck + lint
  2. Run ALL relevant tests → confirm pass
  3. Fix any failures, re-run checks
  4. ONLY THEN: stage → commit
  ⚠️  Order: test → stage → commit. NEVER stage then test.
  Review agents run in /worktree-pr Phase C½ (not here)
```

## Phase 0: Architecture (MANDATORY)

**Before writing any plan, dispatch `feature-dev:code-architect` to design the implementation.**

Without it, you're planning blind. You don't know line numbers, imports, or current state. Skip this and you risk rework when agents discover the codebase doesn't match expectations.

**When working from an epic or issue list**, the architect prompt MUST include scope discovery:

```
Agent(subagent_type="feature-dev:code-architect", model="sonnet",
      prompt="Analyze these N files for [task].

## Requirements
[Issue list from epic, or single issue body]

## Return
1. Exact current state at relevant lines
2. Needed imports
3. Dependencies between changes
4. Recommended wave grouping
5. **Scope findings:** While analyzing these files, note ANY problems you see
   that are NOT covered by the requirements above. Categorize each as:
   - (a) DEPENDENCY: Can't complete a filed issue without fixing this
   - (b) SYSTEMIC: Related problem in the same files, but not required
   Report these in a separate 'Scope Findings' section at the end.")
```

**When working from a single task (no epic):** The scope findings section is optional. Phase 0½ is skipped.

**When to skip Phase 0:** Only when you already have a detailed, file-level plan from the user.

## Phase 0½: Scope Validation + Discovery Gate

**Skip this phase if:** There is no parent epic (single-issue or ad-hoc task). Go directly to Phase 1.

**Run this phase if:** The work is linked to an epic with a checklist of issues (created via `/create-issue` epic workflow).

After the architect returns, compare its scope findings against the epic's issue list:

**Step 1: Fetch the epic checklist.**

```bash
gh issue view <epic-number> --json body -q '.body'
```

Parse the `## Issues` checklist to get the list of filed issues.

**Step 2: Classify architect findings.**

| Category | Criteria | Action |
|----------|----------|--------|
| **(a) DEPENDENCY** | Architect says "can't complete issue #X without fixing this" | Auto-create issue, tag `audit-finding`, add to epic checklist |
| **(b) SYSTEMIC** | Related problem, not required for filed issues | Present to human for decision |
| **Already covered** | Finding matches an existing filed issue | No action needed |

**Step 3: Auto-create dependency issues.**

For category (a) findings — these are scope correction, not scope expansion:

```bash
gh issue create --title "Audit: [Brief description]" \
  --label "audit-finding" \
  --label "epic/<epic-slug>" \
  --body "## Description
[Finding from architect]

## Discovery Context
Found during Phase 0 of epic #<epic-number>.
This is a dependency — cannot complete #<blocked-issue> without fixing this.

## Files Affected
[From architect output]"
```

Update the epic checklist to include the new issue.

**Step 4: Present systemic findings to human (BLOCKING GATE).**

For category (b) findings:

```
Phase 0 Scope Validation — Epic #<number>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Filed issues (in scope):
  ✅ #101 — Fix dark mode toggle regression
  ✅ #102 — Button brand color token
  🆕 #106 — Theme provider needs dark mode var (auto-created, dependency of #101)

Systemic findings (need your decision):
  1. Text base color uses hardcoded value instead of theme token
     Files: src/components/Text.tsx:14
     → Add to epic? [yes/defer]

Options:
  a) Add selected findings to epic (creates issues, adds to checklist)
  b) Defer all to follow-up (creates issues tagged 'deferred', not in epic)
  c) Proceed without changes (filed issues only)
```

**Wait for human response.** Do not proceed to Phase 1 until this gate resolves.

- **"yes" on specific items:** Create issues, add to epic checklist, include in Phase 1 plan.
- **"defer":** Create issues tagged `deferred` + `audit-finding`. They exist in the tracker but are NOT in this epic's scope.
- **"proceed without changes":** Go to Phase 1 with original issue list only. Systemic findings are still created as deferred issues so they're tracked.

**The principle: nothing discovered is ever silently dropped.** Every finding becomes a GitHub issue — the only question is whether it's in THIS epic or deferred to a future one.

**Step 5: Confirm final scope.**

```
Scope confirmed for Epic #<number>:
  In scope: #101, #102, #103, #106 (4 issues)
  Deferred: #107, #108 (2 issues, tracked separately)

Proceeding to Phase 1 (planning).
```

### Epic Mode: fixed-scope vs discovery

The epic body includes a `## Mode` field set during `/create-issue` epic creation:

- **fixed-scope:** Phase 0½ only auto-creates dependency issues (category a). Systemic findings (category b) are auto-deferred without prompting the human. Default for bug-fix epics.
- **discovery:** Phase 0½ presents all findings to the human. For audit-driven or exploratory work.

If the epic has no Mode field, default to **fixed-scope** (safer).

## Plan Template

```markdown
## Architecture Summary
[Key findings from code-architect: patterns, conventions, critical files]

## Scope
- X files to modify, Y new files to create
- Key changes: [summary]

## Wave 1 (Parallel)
| Task | Model | Files | Conflicts | Verify |
|------|-------|-------|-----------|--------|
| [Description] | Sonnet | file1, file2 | none | run unit tests for file1 → all pass |
| [Description] | Haiku | file3 | none | grep for expected string in file3 → found |

## Wave 2 (Depends on Wave 1)
| Task | Model | Files | Conflicts | Verify |
|------|-------|-------|-----------|--------|
| [Description + tests] | Sonnet | file4, tests/test_file4 | none | run unit tests for file4 → all pass |

## Verification (global)
- [ ] All wave gates passed (lint + typecheck + tests at each gate)
- [ ] Typecheck passes
- [ ] Full test suite passes
- [ ] Lint passes
- [ ] Code review complete (via /worktree-pr Phase C½, or inline if not using worktrees)
```

### Verify Column Rules

- Every task MUST have a Verify command that Opus can run after the wave completes
- Verify must be a **runnable command with an observable exit code or output** — not a description of intent
- "Looks correct" is NOT verification. `pytest tests/test_foo.py -v` exits 0 IS verification.
- For implementation tasks: lint + import check at minimum
- For tasks that include tests: run the specific test file
- For mechanical tasks: `grep` for the expected change

### Conflicts Column Rules

- Every task MUST have a Conflicts entry
- List any file that also appears in another task's Files column in the same wave
- If two tasks in the same wave list the same file, the plan is invalid — move one task to the next wave
- If no overlap exists, write `none`

## Commit Sequence is Non-Negotiable

Tests pass → `git add` → `git commit`

**NEVER** stage before testing. **NEVER** commit without running tests first.

If you have already staged files and need to re-test, unstage first:

```
git restore --staged .
```

Then re-run tests. Only after they pass: stage → commit.

## Dispatching Agents

**Critical:** Launch all tasks in a wave with a SINGLE message containing multiple Agent tool calls.

```
// CORRECT - Parallel execution (single message, multiple tool calls)
Agent(model="sonnet", description="Implement feature A", prompt="...")
Agent(model="sonnet", description="Implement feature B", prompt="...")
Agent(model="haiku", description="Update imports", prompt="...")

// WRONG - Sequential execution (wastes time)
Agent(...A...)  // wait for result
Agent(...B...)  // wait for result
```

### Test-Adjacent Implementation

When a task creates new logic, the SAME agent writes both the implementation AND its tests. The agent's Verify step runs the tests. This avoids:
- A separate "write tests" wave (token cost)
- Tests written by a different agent that misunderstands the implementation
- Implementation without any verification

**Exception:** When tests need fixtures/infrastructure that doesn't exist yet, split into Wave 1 (fixtures) → Wave 2 (implementation + tests).

### Before Writing Tests

**Read the project's test style guide before writing any test code.** Check CLAUDE.md for the path to the project's test style guide. Include the style guide rules in every agent prompt that writes tests.

## Wave Gate

After each wave's agents complete, Opus runs every task's Verify command before starting the next wave.

```
Wave N agents complete
        │
        ▼
  WAVE GATE (Opus - you)
  1. Run each task's Verify command
  2. Run global checks (use your project's tools):
     a. Lint and format
     b. Typecheck (catches type errors before they
        cascade to the next wave)
     c. Run affected tests
  3. Update progress table
  4. If any fail:
     - Attempt fix (max 2 tries)
     - Re-run the failed check
     - If still failing: ask user
  5. ALL verifications pass → next wave
```

### Progress Table

After each wave gate, update this table in your response:

```markdown
## Progress
| Wave | Task | Status | Verify Result |
|------|------|--------|---------------|
| 1 | Add validation service | ✅ | lint: pass, import: pass, pytest: 3/3 |
| 1 | Update route handler | ✅ | lint: pass, grep: found expected pattern |
| 2 | Integration tests | ❌ | pytest: 2/4 fail — KeyError on line 42 |
```

## Phase 3: Verify + Commit (MANDATORY)

Phase 3 runs plan reconciliation, execution-based checks, then commits. Review agents (code-reviewer, silent-failure-hunter, etc.) run later — in `/worktree-pr` Phase C½ with fresh context, if you are using that skill. If you are not using worktree-pr, dispatch them inline after committing but before pushing.

```
0. PLAN RECONCILIATION (mandatory — catches plan-execution divergence):
   a. Re-read the Phase 1 plan's Verify column for every task
   b. For each Verify item: confirm it was actually executed and passed
   c. If any Verify item was NOT run (agent prompt omitted it,
      wave gate skipped it, etc.) → run it now
   d. Report: "Plan had N verify items. N executed during waves.
      M executed now in reconciliation. K still failing."
   e. If K > 0: fix failures before proceeding

1. Run your project's typecheck command
2. Run your project's lint command
3. Run ALL relevant tests — confirm pass
4. Fix any failures, then re-run typecheck + lint + tests
5. ONLY THEN: git add <files> → git commit
```

**Plan reconciliation is non-negotiable.** This catches the failure mode where the plan promises verification steps (equivalence tests, integration tests, specific assertions) but agent prompts silently dropped them. The plan's Verify column is a contract — Phase 3 enforces it.

Common plan-execution divergences to watch for:
- Plan says "equivalence tests" → agent prompt said "golden path tests only"
- Plan says "test all N converted queries" → agent tested 3 of 17
- Plan says "verify Docker execution" → agent verified imports only
- Plan says "check external reviewer comments" → agent skipped review loop

⚠️ Order is: **test → stage → commit**. NEVER stage then test.

## References

For detailed guidance, see `references/` in this skill directory:
- `references/agent-prompt-guide.md` — Agent prompt structure, model selection guide, token efficiency, example prompts
- `references/checklists.md` — Pre-plan checklist, post-implementation checklist, review skip red flags
