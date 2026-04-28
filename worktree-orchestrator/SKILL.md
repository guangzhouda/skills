---
name: worktree-orchestrator
description: Coordinate parallel git worktree tasks in one project. Use when Codex needs to start a new task in a dedicated worktree, scan all worktrees for a project, update task progress, show a local dashboard, create Chinese git commits, or perform an approved safe merge back to the base branch without deleting worktrees or resolving conflicts automatically.
---

# Worktree Orchestrator

Use this skill to manage one git worktree per task while keeping progress visible across terminals and agents.

The deterministic operations live in `scripts/worktree_task.py`. Prefer running the script instead of reimplementing git/state/dashboard logic in the chat.

## Safety Contract

- Always run a project entry scan before acting on project state.
- Identify one project by its shared git common directory, not folder name or remote URL.
- Store source-of-truth state under `<git-common-dir>/omx-worktrees/`.
- Preserve human/agent progress notes when refreshing git-derived fields.
- Use Chinese git commit messages for automated task commits.
- Do not merge without explicit approval.
- Do not delete or prune worktrees automatically.
- Delete merged task worktrees only through an explicit user-approved command.
- Do not resolve merge conflicts automatically.
- Do not rewrite history with reset, rebase, or force-push.
- Do not add MCP behavior in v1.

## Quick Commands

From any worktree in the project:

```powershell
python C:\Users\aojing\.codex\skills\worktree-orchestrator\scripts\worktree_task.py --cwd . scan
python C:\Users\aojing\.codex\skills\worktree-orchestrator\scripts\worktree_task.py --cwd . status
python C:\Users\aojing\.codex\skills\worktree-orchestrator\scripts\worktree_task.py --cwd . dashboard
```

Start a new task worktree:

```powershell
python C:\Users\aojing\.codex\skills\worktree-orchestrator\scripts\worktree_task.py --cwd . start --title "修复登录状态"
```

Update progress from a terminal or agent:

```powershell
python C:\Users\aojing\.codex\skills\worktree-orchestrator\scripts\worktree_task.py --cwd . update --task-id <id> --status 进行中 --note "正在修改入口扫描"
```

Commit task work with a Chinese message:

```powershell
python C:\Users\aojing\.codex\skills\worktree-orchestrator\scripts\worktree_task.py --cwd . commit --task-id <id> --message "实现入口扫描"
```

View task commit history:

```powershell
python C:\Users\aojing\.codex\skills\worktree-orchestrator\scripts\worktree_task.py --cwd . commits --task-id <id>
```

Mark tests:

```powershell
python C:\Users\aojing\.codex\skills\worktree-orchestrator\scripts\worktree_task.py --cwd . ready --task-id <id> --tests passed
```

Merge only after explicit user approval:

```powershell
python C:\Users\aojing\.codex\skills\worktree-orchestrator\scripts\worktree_task.py --cwd . merge --task-id <id> --approved
```

Delete a merged task worktree only after explicit user approval:

```powershell
python C:\Users\aojing\.codex\skills\worktree-orchestrator\scripts\worktree_task.py --cwd . delete-worktree --task-id <id> --approved
```

## Workflow

1. Run `scan` when entering a project.
2. Use `start` for each new task. The script creates a task branch and a worktree outside existing worktree roots.
3. Use `update` whenever a terminal or agent reaches a meaningful progress point.
4. Use `status` or `dashboard` to view all project worktrees.
5. Use `commit` with a Chinese message when a task has a coherent checkpoint.
6. Use `ready --tests passed` only after the relevant tests were actually run.
7. Ask the user before merge. After approval, run `merge --approved`; the script verifies source/base cleanliness and stops on conflicts.
8. After a successful merge, optionally ask the user whether to keep or delete the task worktree. Deletion is never automatic; run `delete-worktree --approved` only after approval.

## Dashboard

`dashboard` serves a local read-only page on `127.0.0.1:8765` by default. It refreshes from the shared state and git scans every few seconds. It shows task status, branch, dirty state, ahead/behind counts, test state, merge blockers, cleanup status, task commit history, and recent events.

The dashboard must not be used as a destructive control surface. Route merge, delete, push, rebase, and conflict handling through explicit skill/CLI flows.

## State Schema

Read `references/state-schema.md` when changing state fields, writing migration logic, or debugging reconciliation.

Important files:

```text
<git-common-dir>/omx-worktrees/state.json
<git-common-dir>/omx-worktrees/events.jsonl
<git-common-dir>/omx-worktrees/status.md
.omx/worktrees/status.md    # optional mirror when WORKTREE_ORCHESTRATOR_WRITE_WORKTREE_MIRROR=1
```

## Validation

Run these checks after editing the skill:

```powershell
python C:\Users\aojing\.codex\skills\.system\skill-creator\scripts\quick_validate.py C:\Users\aojing\.codex\skills\worktree-orchestrator
python -m unittest discover C:\Users\aojing\.codex\skills\worktree-orchestrator\scripts
```
