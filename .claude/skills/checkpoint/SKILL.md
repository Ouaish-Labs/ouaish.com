---
name: checkpoint
description: Create a checkpoint by committing work, updating TODO.md, and verifying lint and tests
---

# Checkpoint Skill

## When to Use

After completing a wave in a multi-wave implementation, or whenever you need to save progress and document remaining work.

## Step-by-Step Workflow

### 1. Stage and Commit Current Changes

```bash
# Verify current branch
git branch --show-current

# Review what's changed
git status
git diff --stat

# Stage relevant files (never use git add -A)
git add <specific files>

# Commit with descriptive message
git commit -m "checkpoint: <describe what was completed>"
```

**Do NOT commit:**
- `.env` files or credentials
- Unrelated changes from other tasks
- `node_modules/` or `__pycache__/`

### 2. Create/Update TODO.md with Remaining Tasks

Create or update `TODO.md` at the project root with:
- What was just completed (checked off)
- What remains (unchecked)
- Any blockers or open questions

Format:

```markdown
# Implementation Progress

## Completed
- [x] Task that was finished
- [x] Another completed task

## Remaining
- [ ] Next task to do
- [ ] Another pending task

## Blockers / Notes
- Any issues discovered during this wave
```

### 3. Run Checks and Report Issues

```bash
# Backend lint (Python) — must run inside Docker
docker compose exec api ruff check packages/py_common apps/api apps/worker
docker compose exec api ruff format --check packages/py_common apps/api apps/worker

# Backend tests — must run inside Docker
docker compose exec api pytest apps/api/tests/ -v
docker compose exec api pytest packages/py_common/tests/ -v

# Frontend lint (TypeScript)
cd apps/web && pnpm run lint
```

Report any new errors introduced by the current wave's changes.

### 4. Summarize to User

Provide a concise summary:
- **Completed:** What was done in this wave
- **Committed:** The commit hash and message
- **Lint/test issues:** Any new errors (or "clean")
- **Remaining:** What's next per TODO.md
