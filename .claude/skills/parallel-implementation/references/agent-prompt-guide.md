# Agent Prompt Guide

## Prompt Structure

Give agents:
1. **Specific scope** — Exact files to modify
2. **Clear goal** — What success looks like
3. **Context** — Related code patterns and conventions (from architect output)
4. **Constraints** — What NOT to change
5. **Verification** — Command to run + expected result. Agent MUST run this before reporting done.

## Test-Adjacent Implementation

When a task creates new logic, the SAME agent writes both the implementation AND its tests. The agent's Verify step runs the tests. This avoids:
- A separate "write tests" wave (token cost)
- Tests written by a different agent that misunderstands the implementation
- Implementation without any verification

**Exception:** When tests need fixtures/infrastructure that doesn't exist yet, split into Wave 1 (fixtures) → Wave 2 (implementation + tests).

## Before Writing Tests

**Read the project's test style guide before writing any test code.** Check CLAUDE.md for the path to the project's test style guide. Include the style guide rules in the agent prompt — don't treat test-writing as a mechanical task that skips convention checks.

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

## Verify (run before reporting done)
1. Lint check on modified file → exit 0
2. `python -c "from api.services.validation import validate_email; assert validate_email('a@b.com'); assert not validate_email('invalid')"` → no error
3. `python -m pytest api/tests/test_validation.py -v` → all pass
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
