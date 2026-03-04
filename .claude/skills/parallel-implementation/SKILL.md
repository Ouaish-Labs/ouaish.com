---
name: parallel-implementation
description: Use when entering plan mode for any multi-file implementation task - enforces tiered model usage (Haiku/Sonnet/Opus) and wave-based parallel execution
---

# Parallel Implementation Skill

Execute multi-file implementations using tiered models and wave-based parallelization.

## Model Assignment Rules

| Task Type | Model | Examples |
|-----------|-------|----------|
| **Orchestration** | Opus (you) | Planning, coordination, final review |
| **Architecture** | Sonnet | `feature-dev:code-architect` — design before implementation |
| **Implementation** | Sonnet | Logic-heavy changes, new features, complex refactors |
| **Mechanical** | Haiku | Import updates, renames, simple edits, file moves |
| **Code Review** | Opus | `pr-review-toolkit:code-reviewer` or manual review |

## Required Workflow

```
┌─────────────────────────────────────────┐
│  PHASE 0: ARCHITECTURE (code-architect) │
│  - Launch feature-dev:code-architect    │
│  - Analyze existing codebase patterns   │
│  - Identify files to create/modify      │
│  - Design component/data flow           │
│  - Output: implementation blueprint     │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  PHASE 1: PLAN (Opus - you)             │
│  - Use architect's blueprint as input   │
│  - Group into waves by dependency       │
│  - Assign model tiers to each task      │
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
│                                         │
│  Wave 2: Dependent tasks (parallel)     │
│  ├─ [Sonnet] Task D (needs A)           │
│  └─ [Haiku] Task E (needs B)            │
│                                         │
│  Wave N: Continue until complete        │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  PHASE 3: REVIEW (Opus)                 │
│  - Run pr-review-toolkit:code-reviewer  │
│  - Fix any issues found                 │
│  - Run typecheck + tests                │
│  - Verify no regressions                │
└─────────────────────────────────────────┘
```

## Phase 0: Architecture (MANDATORY)

**Before writing any plan, launch `feature-dev:code-architect` to design the implementation.**

This agent analyzes existing codebase patterns, conventions, and architecture to produce a blueprint with:
- Specific files to create and modify
- Component designs and data flows
- Build sequences respecting dependencies
- Pattern conformance checks

```
Agent tool call:
  subagent_type: feature-dev:code-architect
  model: sonnet
  prompt: |
    Design the architecture for: [task description]

    Analyze existing patterns in the codebase and provide:
    1. Files to create/modify with specific changes
    2. Component/module design
    3. Data flow and dependencies
    4. Build sequence (what depends on what)
```

**Why this matters:** Without the architect phase, plans are based on assumptions about the codebase rather than analysis. The architect agent reads actual code, traces execution paths, and identifies patterns that inform better task decomposition. Skip this and you risk rework when agents discover the codebase doesn't match expectations.

**When to skip Phase 0:** Only when you already have a detailed, file-level plan from the user (e.g., they've done the architecture work themselves and provided specific instructions per file).

## Plan Template

When planning, structure your output like this:

```markdown
## Architecture Summary
[Key findings from code-architect: patterns, conventions, critical files]

## Scope
- X files to modify
- Y new files to create
- Key changes: [summary]

## Wave 1 (Parallel)
| Task | Model | Files | Reason |
|------|-------|-------|--------|
| [Description] | Sonnet | file1.ts, file2.ts | [Why this model] |
| [Description] | Haiku | file3.ts | Simple import update |

## Wave 2 (Depends on Wave 1)
| Task | Model | Files | Depends On |
|------|-------|-------|------------|
| [Description] | Sonnet | file4.ts | Wave 1 Task 1 |

## Verification
- [ ] TypeScript passes
- [ ] Tests pass
- [ ] Lint passes
- [ ] Code review complete
```

## Dispatching Agents

**Critical:** Launch all tasks in a wave with a SINGLE message containing multiple Task tool calls.

```typescript
// CORRECT - Parallel execution
<Task model="sonnet" description="Implement feature A">...</Task>
<Task model="sonnet" description="Implement feature B">...</Task>
<Task model="haiku" description="Update imports">...</Task>
// All three run concurrently

// WRONG - Sequential execution (wastes time)
<Task>A</Task>
// wait
<Task>B</Task>
// wait
```

## Model Selection Guide

**Use Sonnet when:**
- Writing new functions/components
- Refactoring existing logic
- Complex file modifications
- Anything requiring reasoning about code structure

**Use Haiku when:**
- Updating import statements
- Renaming variables/functions
- Moving files
- Simple find-and-replace patterns
- Deleting unused code

**Use Opus (yourself) when:**
- Planning and coordination
- Fixing TypeScript/test failures after waves complete
- Final code review
- Complex debugging

## Agent Prompt Best Practices

Give agents:
1. **Specific scope** - Exact files to modify
2. **Clear goal** - What success looks like
3. **Context** - Related code patterns, conventions (from architect output)
4. **Constraints** - What NOT to change

### Before writing tests

**Read the project's test style guide before writing any test code.** Check CLAUDE.md for the path (e.g. `docs/test-style-guide.md`). Verify each test conforms to it — don't treat test-writing as a mechanical task that skips convention checks. When dispatching agents to write tests, include the style guide rules in the agent prompt.

```markdown
# Good agent prompt
Migrate `app/src/components/CreateForm.tsx` to use react-number-format.

## Requirements
- Replace TextField numeric inputs with NumericFormat
- Use `onValueChange` with `values.floatValue`
- Currency fields: prefix="$", thousandSeparator
- Preserve existing validation logic

## Files
- Only modify: CreateForm.tsx

## Do NOT
- Change other components
- Modify test files
- Add new dependencies
```

## After All Waves Complete

1. **Run TypeScript check:** `npm run typecheck`
2. **Run tests:** `npm test`
3. **Run lint:** `npm run lint`
4. **Launch code review:**
   ```
   Task: pr-review-toolkit:code-reviewer
   Prompt: Review all changes from this implementation for issues
   ```
5. **Fix any issues found**
6. **Commit only when verification passes**

## Token Efficiency

This workflow optimizes token usage:

| Model | Cost Factor | Use For |
|-------|-------------|---------|
| Haiku | 1x (cheapest) | 30-40% of tasks (mechanical) |
| Sonnet | 5x | 50-60% of tasks (implementation + architecture) |
| Opus | 15x | 10% of tasks (review only) |

**Result:** 50-70% cost reduction vs. Opus-only execution

## Checklist Before Exiting Plan Mode

- [ ] `feature-dev:code-architect` launched and blueprint reviewed (or user provided detailed plan)
- [ ] All files identified and grouped into waves
- [ ] Each task assigned a model tier (Haiku/Sonnet)
- [ ] Dependencies between waves documented
- [ ] Verification steps defined
- [ ] No circular dependencies between waves
- [ ] Test style guide read and rules noted for test-writing waves
