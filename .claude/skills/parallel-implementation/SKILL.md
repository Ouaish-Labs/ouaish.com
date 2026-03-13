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
┌─────────────────────────────────────────┐
│  PHASE 0: ARCHITECTURE (code-architect) │
│  - Dispatch feature-dev:code-architect  │
│  - Agent reads ALL affected files       │
│  - Returns: current state, imports,     │
│    deps, recommended wave grouping      │
│  YOU DO NOT SKIP THIS PHASE             │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  PHASE 1: PLAN (Opus - you)            │
│  - Use architect output to build plan   │
│  - Group into waves by dependency       │
│  - Assign model tiers + Verify commands │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  PHASE 2: EXECUTE WAVES                 │
│                                         │
│  Wave 1: Independent tasks (parallel)   │
│  ├─ [Sonnet] Implementation task A      │
│  ├─ [Sonnet] Implementation task B      │
│  └─ [Haiku] Mechanical task C           │
│  *** WAVE GATE: run Verify commands *** │
│                                         │
│  Wave 2: Dependent tasks (parallel)     │
│  ├─ [Sonnet] Task D (needs A)           │
│  └─ [Haiku] Task E (needs B)            │
│  *** WAVE GATE: run Verify commands *** │
│                                         │
│  Wave N: Continue until complete        │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  PHASE 3: VERIFY + COMMIT (MANDATORY)   │
│  1. Run your project's typecheck + lint │
│  2. Run ALL relevant tests — confirm    │
│     pass                                │
│  3. Fix any failures, re-run checks     │
│  4. ONLY THEN: stage → commit           │
│  ⚠️ Order: test → stage → commit        │
│  (Review agents run in /worktree-pr     │
│   Phase C½, if used)                    │
└─────────────────────────────────────────┘
```

## Phase 0: Architecture (MANDATORY)

**Before writing any plan, dispatch `feature-dev:code-architect` to design the implementation.**

Without it, you're planning blind. You don't know line numbers, imports, or current state. Skip this and you risk rework when agents discover the codebase doesn't match expectations.

```
Agent(
  subagent_type="feature-dev:code-architect",
  model="sonnet",
  prompt="Analyze these N files for [task]. Return: exact current state at relevant lines, needed imports, dependencies between changes, recommended wave grouping."
)
```

**When to skip Phase 0:** Only when you already have a detailed, file-level plan from the user (e.g., they've done the architecture work themselves and provided specific instructions per file).

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

Phase 3 runs execution-based checks only. Review agents (code-reviewer, silent-failure-hunter, etc.) run later — in `/worktree-pr` Phase C½ with fresh context, if you are using that skill. If you are not using worktree-pr, dispatch them inline after committing but before pushing.

1. Run your project's typecheck command
2. Run your project's lint command
3. Run ALL relevant tests — confirm pass
4. Fix any failures, then re-run typecheck + lint + tests
5. ONLY THEN: `git add <files>` → `git commit`

⚠️ Order is: **test → stage → commit**. NEVER stage then test.

## References

For detailed guidance, see `references/` in this skill directory:
- `references/agent-prompt-guide.md` — Agent prompt structure, model selection guide, token efficiency, example prompts
- `references/checklists.md` — Pre-plan checklist, post-implementation checklist, review skip red flags
