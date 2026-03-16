#!/usr/bin/env python3
"""
Claude Code PreToolUse Hook: Agent dispatch gates.

Enforces model-tier and dispatch rules BEFORE agents are launched:
1. Round 1 review agents (pr-review-toolkit:*) must specify model="sonnet"
2. Round 2+ review agents must use resume, not fresh dispatch
3. Fixer agent cannot dispatch without prior round comment posted to PR
4. Worktree agent prompts must include cd instruction when session exists

Exit codes:
- 0: Allow the dispatch
- 2: Block the dispatch (with error message on stderr)
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

DEBUG_LOG = Path(__file__).parent / "hook_debug.log"


def log_debug(message: str):
    try:
        with open(DEBUG_LOG, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] agent_gate: {message}\n")
    except Exception:
        pass


def resolve_session_dir(input_data: dict) -> Path:
    """Find session dir from agent prompt's cd/Working directory reference."""
    tool_input = input_data.get("tool_input", {})
    prompt = tool_input.get("prompt", "")
    wt_match = re.search(r"(?:Working directory|cd)\s*:?\s*(~/Developer/[^\s.]+)", prompt)
    if wt_match:
        wt_path = Path(wt_match.group(1)).expanduser()
        if wt_path.is_dir() and (wt_path / ".session").is_dir():
            return wt_path / ".session"
    cwd = input_data.get("cwd", "")
    if cwd:
        cwd_path = Path(cwd)
        if (cwd_path / ".session").is_dir():
            return cwd_path / ".session"
    return Path(".session")


def load_json_array(filepath: Path) -> list:
    """Load a JSON array file, returning [] on any error."""
    if not filepath.exists():
        return []
    try:
        return json.loads(filepath.read_text())
    except (json.JSONDecodeError, Exception):
        return []


def load_agents(session_dir: Path) -> list:
    return load_json_array(session_dir / "agents.json")


def load_events(session_dir: Path) -> list:
    return load_json_array(session_dir / "events.json")


def main():
    try:
        raw_input = sys.stdin.read()
        input_data = json.loads(raw_input)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name != "Agent":
        sys.exit(0)

    tool_input = input_data.get("tool_input", {})
    subagent_type = tool_input.get("subagent_type", "")
    model = tool_input.get("model", "")
    prompt = tool_input.get("prompt", "")
    resume_id = tool_input.get("resume", "")

    # ── Gate 1: Review agent model enforcement ─────────────────
    # Fresh dispatch (Round 1) of review agent must specify model="sonnet"
    if re.match(r"pr-review-toolkit:", subagent_type) and not resume_id and model != "sonnet":
        actual = model if model else "(not specified — inherits Opus)"
        log_debug(f"Blocked review agent with wrong model: {subagent_type} model={model}")
        print(
            f"Agent gate: Round 1 review agents must use model='sonnet'.\n"
            f"\n"
            f"  subagent_type: {subagent_type}\n"
            f"  model: {actual}\n"
            f"\n"
            f"Round 1 dispatches fresh Sonnet agents (sufficient for initial review,\n"
            f"saves budget). Round 2+ resumes with inherited Opus.\n"
            f"Use: Agent(subagent_type='...', model='sonnet', prompt='...')\n"
            f"See /worktree-pr Phase C½ Hybrid Model Strategy.",
            file=sys.stderr,
        )
        sys.exit(2)

    # ── Gate 2: Round 2+ review must resume, not fresh dispatch ─
    if re.match(r"pr-review-toolkit:", subagent_type) and not resume_id:
        session_dir = resolve_session_dir(input_data)
        agents = load_agents(session_dir)
        prior_dispatches = [
            a for a in agents if a.get("subagent_type") == subagent_type and a.get("type") == "agent_dispatch"
        ]
        if prior_dispatches:
            prior_id = prior_dispatches[-1].get("agent_id", "unknown")
            log_debug(f"Blocked fresh re-dispatch of {subagent_type} — prior dispatch exists (id: {prior_id})")
            print(
                f"Agent gate: review agent already dispatched — use resume instead.\n"
                f"\n"
                f"  subagent_type: {subagent_type}\n"
                f"  prior agent_id: {prior_id}\n"
                f"\n"
                f"Round 2+ must resume the Round 1 agent, not dispatch fresh.\n"
                f"Use: Agent(resume='{prior_id}', prompt='...')\n"
                f"See /worktree-pr Phase C½ Step 3.",
                file=sys.stderr,
            )
            sys.exit(2)

    # ── Gate 3: Fixer agent requires prior round comment ──────────
    if (
        subagent_type in ("general-purpose", "")
        and not resume_id
        and re.search(r"(?:review findings|Fix ALL items|code fixer)", prompt, re.IGNORECASE)
    ):
        session_dir = resolve_session_dir(input_data)
        events = load_events(session_dir)
        round_comments = [e for e in events if e.get("type") == "pr_comment_round"]
        if not round_comments:
            any_pr_comments = [
                e
                for e in events
                if e.get("type") in ("pr_comment_round", "final_summary_posted")
                or "gh pr comment" in e.get("command_preview", "")
            ]
            if not any_pr_comments:
                log_debug("Blocked fixer agent — no round comment posted to PR yet")
                print(
                    "Agent gate: cannot dispatch fixer before posting round findings to PR.\n"
                    "\n"
                    "The review loop requires: review -> POST findings to PR -> THEN fix.\n"
                    "The fixer reads findings from the PR comment, so it must exist first.\n"
                    "\n"
                    "Post the round findings with gh pr comment, then dispatch the fixer.\n"
                    "See /worktree-pr Phase C½ Step 1 -> Step 2.",
                    file=sys.stderr,
                )
                sys.exit(2)

    # ── Gate 4: Worktree agent prompts must include cd instruction ─
    session_dir = resolve_session_dir(input_data)
    manifest = session_dir / "manifest.json"
    if (
        manifest.exists()
        and subagent_type
        and not re.match(r"pr-review-toolkit:", subagent_type)
        and not resume_id
    ):
        has_cd = re.search(r"(?:cd |Working directory[:\s])\s*~/Developer/", prompt)
        if not has_cd and prompt:
            log_debug(f"Blocked agent without worktree cd: {subagent_type}")
            print(
                f"Agent gate: agent prompt missing worktree directory instruction.\n"
                f"\n"
                f"  subagent_type: {subagent_type}\n"
                f"\n"
                f"Session manifest exists (.session/), which means this is worktree work.\n"
                f"Agent prompts MUST include 'cd ~/Developer/<branch-name>' or\n"
                f"'Working directory: ~/Developer/<branch-name>' to prevent agents\n"
                f"from editing files in the main repo instead of the worktree.\n"
                f"\n"
                f"See /worktree-pr Phase B: Subagent working directory — CRITICAL.",
                file=sys.stderr,
            )
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
