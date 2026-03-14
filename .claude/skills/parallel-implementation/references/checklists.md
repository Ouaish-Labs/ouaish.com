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

- [ ] **All wave gates passed** — every task's Verify command exited successfully
- [ ] **Global checks passed at every wave gate** — lint, typecheck, and affected tests all green
- [ ] **Progress table shows all checkmarks** — no unresolved failures
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
