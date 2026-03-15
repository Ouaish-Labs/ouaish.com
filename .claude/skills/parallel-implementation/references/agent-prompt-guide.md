# Agent Prompt Guide

## Prompt Structure

Give agents:
1. **Specific scope** — Exact files to modify
2. **Clear goal** — What success looks like
3. **Context** — Related code patterns and conventions (from architect output)
4. **Constraints** — What NOT to change
5. **Verification** — Command to run + expected result. Agent MUST run this before reporting done.
6. **Debugging budget** — 3 failed attempts → STOP and report. Do not keep retrying.

## Test-Adjacent Implementation

When a task creates new logic, the SAME agent writes both the implementation AND its tests. The agent's Verify step runs the tests. This avoids:
- A separate "write tests" wave (token cost)
- Tests written by a different agent that misunderstands the implementation
- Implementation without any verification

**Exception:** When tests need fixtures/infrastructure that doesn't exist yet, split into Wave 1 (fixtures) → Wave 2 (implementation + tests).

## Before Writing Tests

**Read the project's test style guide before writing any test code.** Check CLAUDE.md for the path to the project's test style guide. Include the style guide rules in the agent prompt — don't treat test-writing as a mechanical task that skips convention checks.

## Task Compliance Report (mandatory in every agent prompt)

Every agent prompt MUST include this block at the end. The agent fills it out by **pasting command output**, not writing yes/no.

    ## Task Compliance (fill before reporting done)
    - **Verify results** — paste the output of each Verify command:
      ```
      [paste actual command output here — not "pass" or "exit 0", the real output]
      ```
    - **Files modified:** [paste output of `git diff --name-only`]
    - **Skipped:** [anything from the prompt you didn't do — state NONE if nothing was skipped. If you skipped something, explain WHY.]

**Why paste, not report:** An agent can write "tests pass" without running tests. It cannot fabricate test output that matches the test suite. Pasted output is fabrication-resistant.

**The orchestrator MUST read this section** from every agent's response before proceeding to the next wave. If any agent reports skipped work, address it before the wave gate. If verify output is missing or looks fabricated (e.g., no test names, generic "all pass"), re-run the command yourself.

## Example Agent Prompt

```markdown
# Task: Add validate_email() to api/services/validation.py

## Requirements
- Accept a string, return bool
- Must handle: valid emails, missing @, empty string, None
- Raise TypeError for non-string input

## Files
- Modify: api/services/validation.py
- Create: api/tests/test_validation.py

## Do NOT
- Change other services
- Add new dependencies

## Debugging Budget
If a verify step fails: fix and retry. After 3 failed attempts on the same check, STOP. Report what you tried, what the error was, and what you believe the root cause is. Do not keep retrying.

## Verify (run before reporting done)
1. Lint check on modified file → exit 0
2. `python -c "from api.services.validation import validate_email; assert validate_email('a@b.com'); assert not validate_email('invalid')"` → no error
3. `python -m pytest api/tests/test_validation.py -v` → all pass

## Task Compliance (fill before reporting done)
- **Verify results** — paste actual output:
  ```
  [paste lint output here]
  [paste pytest output here]
  [paste import check output here]
  ```
- **Files modified:** [paste `git diff --name-only` output]
- **Skipped:** NONE (or: what you skipped and why)
```

## Model Selection Guide

**Use Sonnet when:**
- Writing new functions or components
- Refactoring existing logic
- Complex file modifications
- Anything requiring reasoning about code structure

**Use Haiku when:**
- Updating import statements
- Renaming variables or functions
- Moving files
- Simple find-and-replace patterns
- Deleting unused code

**Use Opus (yourself) when:**
- Planning and coordination
- Running wave gates and fixing failures
- Final code review
- Complex debugging

## Token Efficiency

| Model | Cost Factor | Use For |
|-------|-------------|---------|
| Haiku | 1x (cheapest) | 30–40% of tasks (mechanical) |
| Sonnet | 5x | 50–60% of tasks (implementation + architecture) |
| Opus | 15x | 10% of tasks (orchestration + review only) |

**Result:** 50–70% cost reduction vs. Opus-only execution

**This table applies to implementation tasks only.** Code review (Phase C½ of `/worktree-pr`) requires Sonnet minimum — see the hybrid model strategy in that skill. "Small diff" ≠ "mechanical task." Model tier is determined by the type of reasoning, not input size. **Never use Haiku for any review task.**
