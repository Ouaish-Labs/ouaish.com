# Parallel Implementation Checklists

## Before Exiting Plan Mode

- [ ] **Phase 0 completed** — code-architect agent dispatched and returned file analysis (including scope findings)
- [ ] **Phase 0½ completed (if epic)** — scope findings classified, dependency issues auto-created, systemic findings presented to human, scope confirmed
- [ ] All files identified and grouped into waves (using architect output, not guesses)
- [ ] Each task assigned a model tier (Haiku/Sonnet)
- [ ] **Every task has a Verify column** with a runnable command and expected result
- [ ] Implementation tasks that create logic are paired with tests (test-adjacent)
- [ ] Dependencies between waves documented
- [ ] No circular dependencies between waves
- [ ] Test style guide path confirmed from CLAUDE.md and rules noted for test-writing waves

## After All Waves Complete (Phase 3 Gate)

- [ ] **Plan reconciliation completed** — every Verify item from Phase 1 plan confirmed executed (not just "tests pass" — the SPECIFIC tests/checks listed in the plan)
- [ ] **All wave gates passed** — every task's Verify command exited successfully
- [ ] **Global checks passed at every wave gate** — lint, typecheck, and affected tests all green
- [ ] **Progress table shows all checkmarks** — no unresolved failures
- [ ] **No plan-execution divergence** — if the plan promised equivalence tests, integration tests, or specific assertions, they were actually written and run (not silently dropped from agent prompts)
- [ ] **Typecheck passes** — run after all waves, before staging anything
- [ ] **Lint passes** — run after all waves, before staging anything
- [ ] **All relevant tests pass** — run after all waves, before staging anything
- [ ] **Commit sequence followed**: tests pass → `git add` → `git commit` — never staged before testing
- [ ] THEN and ONLY THEN: commit
- [ ] **Review agents** — if not using /worktree-pr Phase C½, dispatch code-reviewer and silent-failure-hunter inline now

## Red Flags — You Are About to Skip Review

| Thought | Reality |
|---------|---------|
| "Pre-commit hooks passed, good enough" | Hooks check syntax. Review checks logic. Different things. |
| "The diffs look correct to me" | You wrote the code. You have blind spots. That's why review exists. |
| "It's a small change" | Small changes have inverted defaults and dead code too. |
| "I'll review after pushing" | Review catches issues BEFORE they go to CI, not after. |
| "The agents will just say LGTM" | Then it takes 2 minutes and costs nothing. Run them. |

## Red Flags — You're About to Drop Planned Work

| Thought | Reality |
|---------|---------|
| "The deadline is tight, skip the equivalence tests" | Tell the user it takes longer. Don't silently drop verification. |
| "Golden path tests cover it" | Golden path tests hit 3-4 code paths. The service may have 17. |
| "I already know these files, skip Phase 0" | You know what you read. You don't know what you didn't look for. |
| "This is mechanical / low risk" | You're classifying risk BEFORE the investigation that would reveal risk. |
| "Lint + typecheck pass, we're good" | Lint checks syntax. Tests check behavior. Not interchangeable. |
| "I'll mention it to the user later" | You won't. File an issue or add to the plan NOW. |
