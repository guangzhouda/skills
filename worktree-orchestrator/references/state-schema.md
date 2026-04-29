# Worktree Orchestrator State Schema

`worktree-orchestrator` stores source-of-truth state under the shared git common directory so sibling worktrees for the same project read and write one status model.

```text
<git-common-dir>/omx-worktrees/state.json
<git-common-dir>/omx-worktrees/events.jsonl
```

The Markdown file below is the default generated human-readable mirror and can be regenerated:

```text
<git-common-dir>/omx-worktrees/status.md
```

The worktree-local Markdown mirror is optional because writing into a checked-out worktree can make it dirty:

```text
.omx/worktrees/status.md
```

## Project Identity

Use this command to identify the project:

```text
git rev-parse --path-format=absolute --git-common-dir
```

Use this command to enumerate the worktrees that belong to that project:

```text
git worktree list --porcelain
```

Do not use folder name or remote URL as the primary identity.

## State Shape

```json
{
  "version": 1,
  "project": {
    "projectId": "absolute git common dir",
    "name": "repo name",
    "commonDir": "absolute git common dir",
    "baseBranch": "main"
  },
  "tasks": [
    {
      "projectId": "absolute git common dir",
      "taskId": "20260428120000-abcd",
      "title": "修复登录状态",
      "worktreePath": "C:/repo.worktrees/20260428120000-abcd-task",
      "branch": "task/20260428120000-abcd-task",
      "baseBranch": "main",
      "owner": "terminal-or-agent-id",
      "status": "进行中",
      "activeUpdate": "正在修改入口扫描",
      "git": {
        "exists": true,
        "dirty": false,
        "untracked": 0,
        "ahead": 1,
        "behind": 0,
        "latestCommit": "sha",
        "locked": false,
        "prunable": false
      },
      "tests": {
        "status": "unknown",
        "lastRun": null
      },
      "merge": {
        "ready": true,
        "approved": false,
        "blockedReason": null,
        "summary": "ready"
      },
      "cleanup": {
        "worktreeRemoved": false,
        "approved": false,
        "removedAt": null,
        "worktreePath": null
      },
      "createdAt": "2026-04-28T00:00:00Z",
      "updatedAt": "2026-04-28T00:00:00Z"
    }
  ],
  "lastScanAt": "2026-04-28T00:00:00Z"
}
```

## Status Values

- `进行中`
- `有未提交修改`
- `已提交待测试`
- `已测试待合并批准`
- `已落后主分支需同步`
- `合并有冲突需人工处理`
- `已合并`
- `missing`
- `orphaned`
- `基线工作区`

## Mutation Rules

- Scans may refresh git-derived fields and mark missing/orphaned records.
- Scans must preserve `activeUpdate`, `owner`, and explicit test status.
- Worktrees must not be deleted automatically.
- `delete-worktree --approved` may remove only a task already marked `已合并`; it does not delete branches.
- Worktree deletion must refuse dirty task worktrees, current-worktree deletion, and branches not confirmed as merged into the base branch.
- Merge must require explicit approval.
- Merge conflicts must not be resolved automatically.
- Every mutation should append a JSON object to `events.jsonl`.
- Only write `.omx/worktrees/status.md` when `WORKTREE_ORCHESTRATOR_WRITE_WORKTREE_MIRROR=1`.

## Read-only Views

- `commits --task-id <id>` and `/api/commits?taskId=<id>` derive task commit history from `git log`.
- Unmerged tasks use `baseBranch..taskBranch`.
- Merged tasks use the recorded merge preflight range (`baseSha..sourceSha`) when available, so history remains visible after the task worktree is deleted.
- `/api/timeline` is a read-only, derived dashboard view for merged task lifecycle history. It uses only orchestrator-owned `state.json`, `events.jsonl`, and recorded merge/test/cleanup fields; it does not infer arbitrary Git history.
- Timeline payloads include `source: "orchestrator"`, `eventLimit`, and `eventWindowMayBeTruncated`. When the event window may be truncated, missing nodes mean “not recorded or outside the loaded event window”.
- Timeline nodes expose `status` (`complete`, `missing`, `retained`, `warning`) and `provenance` (`recorded`, `derived`, `missing`) so derived approval, inferred cleanup, and absent historical facts are visible instead of hidden.
- Timeline sorting uses `sortTime` and `sortBasis` (`merged`, `cleanup`, `preflight`, `tests`, `created`, `updated`, `none`). `updated` is a low-confidence fallback because scans can refresh `updatedAt`.
- A merged task with `git.exists == false` is treated as an inferred deleted worktree even when explicit cleanup fields are absent.
