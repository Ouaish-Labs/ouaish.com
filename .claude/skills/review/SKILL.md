---
name: review
description: Code review workflows using pr-review-toolkit agents
---

# Code Review Skill

## Full PR Review

**Preferred method:**

```
/pr-review-toolkit:review-pr <PR_NUMBER>
```

Or with options:
```
/pr-review-toolkit:review-pr <PR_NUMBER> tests errors
/pr-review-toolkit:review-pr <PR_NUMBER> all parallel
```

## Available Agents

| Agent | Purpose | When to Use |
|-------|---------|-------------|
| `code-reviewer` | CLAUDE.md compliance, general review | After any code changes |
| `silent-failure-hunter` | Inadequate error handling | After try/except, fallback logic |
| `code-simplifier` | Duplication, complexity | After significant changes |
| `type-design-analyzer` | Type safety, invariants | After modifying types/schemas |
| `pr-test-analyzer` | Test coverage gaps | Before PR creation |
| `comment-analyzer` | Comment accuracy, stale docs | After adding docs |

## When to Run Agents

| Trigger | Agent |
|---------|-------|
| After writing/modifying code | `code-reviewer` |
| After adding error handling | `silent-failure-hunter` |
| After significant changes | `code-simplifier` |
| Before committing (type/schema changes) | `type-design-analyzer` |
| Before creating PR | `pr-test-analyzer` |
| After writing comments/docs | `comment-analyzer` |

## Parallel Execution

**Run independent agents in parallel** (single message with multiple Agent tool calls):

```
# GOOD - Parallel
Agent: pr-review-toolkit:code-reviewer
Agent: pr-review-toolkit:silent-failure-hunter
Agent: pr-review-toolkit:type-design-analyzer

# BAD - Sequential (wastes time)
Agent: code-reviewer → wait → Agent: silent-failure-hunter → wait
```

## After Review Completes

1. Post findings: `gh pr review <PR_NUMBER> --comment --body "..."`
2. Categorize: Critical > Important > Suggestions
3. Include file:line references

## Creating Issues from Findings

| Finding | Action |
|---------|--------|
| High confidence (>=80%) | Fix immediately OR create issue |
| Test coverage gap | Create issue with specific test cases |
| Type design issue | Fix if simple, issue if architectural |

```bash
gh issue create --title "Bug: Silent failure in X" --body "Found by silent-failure-hunter..."
gh issue create --title "Test: Add coverage for Y" --body "Found by pr-test-analyzer..."
```

## CI Monitoring After Push

**Hook enforced:** `.claude/hooks/ci_monitor.py` monitors CI after `git push`.

After pushing, always report CI status:
```
# GOOD
"Pushed to main. CI pipeline: passed (run 21303308130)"

# GOOD (failure)
"Pushed to main. CI FAILED: Build failed in 'test' job.
 Run `gh run view 21303308130 --log-failed` to see details."

# BAD
"Done! Pushed 2 commits."  ← Missing CI status!
```

## Commit Workflow

Stage specific files, never `git add -A`. Follow conventional commits:

```bash
git add <specific files>
git commit -m "feat(scope): add job retry logic (#42)"
```

Prefix reference: `feat`, `fix`, `chore`, `refactor`, `test`, `docs`.
