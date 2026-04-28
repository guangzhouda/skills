#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import uuid

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows path
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX path
    msvcrt = None


VERSION = 1
STATE_DIR_NAME = "omx-worktrees"
STATUS_VALUES = {
    "进行中",
    "有未提交修改",
    "已提交待测试",
    "已测试待合并批准",
    "已落后主分支需同步",
    "合并有冲突需人工处理",
    "已合并",
    "missing",
    "orphaned",
    "基线工作区",
}


class WorktreeError(RuntimeError):
    pass


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    if check and result.returncode != 0:
        command = "git -C {0} {1}".format(cwd, " ".join(args))
        details = (result.stderr or result.stdout or "").strip()
        raise WorktreeError(f"{command} failed: {details}")
    return result


def normalize_path(path: Path | str) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False
    except FileNotFoundError:
        return normalize_path(child).startswith(normalize_path(parent) + os.sep)


def slugify(text: str) -> str:
    pieces = re.findall(r"[A-Za-z0-9]+", text.lower())
    slug = "-".join(pieces)[:40].strip("-")
    return slug or "task"


def has_cjk(text: str) -> bool:
    return re.search(r"[\u3400-\u4dbf\u4e00-\u9fff]", text) is not None


def parse_worktree_porcelain(text: str) -> list[dict]:
    entries: list[dict] = []
    current: dict | None = None

    def flush() -> None:
        nonlocal current
        if current is not None:
            if "path" not in current:
                raise WorktreeError("Malformed git worktree output: entry without worktree path")
            entries.append(current)
            current = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")
        if not line:
            flush()
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            flush()
            current = {
                "path": value,
                "head": None,
                "branchRef": None,
                "branch": None,
                "detached": False,
                "bare": False,
                "locked": False,
                "lockedReason": None,
                "prunable": False,
            }
            continue
        if current is None:
            raise WorktreeError(f"Malformed git worktree output before worktree line: {line}")
        if key == "HEAD":
            current["head"] = value
        elif key == "branch":
            current["branchRef"] = value
            current["branch"] = value.removeprefix("refs/heads/")
        elif key == "detached":
            current["detached"] = True
        elif key == "bare":
            current["bare"] = True
        elif key == "locked":
            current["locked"] = True
            current["lockedReason"] = value or None
        elif key == "prunable":
            current["prunable"] = True
        else:
            current[key] = value or True
    flush()
    return entries


def git_output(args: list[str], cwd: Path, default: str | None = None) -> str | None:
    result = run_git(args, cwd, check=False)
    if result.returncode != 0:
        return default
    return result.stdout.strip()


def detect_base_branch(cwd: Path) -> str:
    for candidate in ("main", "master", "trunk"):
        result = run_git(["show-ref", "--verify", "--quiet", f"refs/heads/{candidate}"], cwd, check=False)
        if result.returncode == 0:
            return candidate
    branch = git_output(["symbolic-ref", "--quiet", "--short", "HEAD"], cwd)
    return branch or "main"


def discover_project(cwd: Path) -> dict:
    top = git_output(["rev-parse", "--show-toplevel"], cwd)
    common = git_output(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd)
    if not top or not common:
        raise WorktreeError(f"{cwd} is not inside a git worktree")
    worktrees = parse_worktree_porcelain(run_git(["worktree", "list", "--porcelain"], cwd).stdout)
    base_branch = detect_base_branch(cwd)
    return {
        "root": str(Path(top).resolve()),
        "commonDir": str(Path(common).resolve()),
        "projectId": str(Path(common).resolve()),
        "name": Path(top).resolve().name,
        "baseBranch": base_branch,
        "worktrees": worktrees,
    }


def state_paths(common_dir: str | Path) -> dict[str, Path]:
    state_dir = Path(common_dir) / STATE_DIR_NAME
    return {
        "dir": state_dir,
        "state": state_dir / "state.json",
        "events": state_dir / "events.jsonl",
        "lock": state_dir / "state.lock",
    }


@contextlib.contextmanager
def state_lock(paths: dict[str, Path], timeout: float = 10.0):
    paths["dir"].mkdir(parents=True, exist_ok=True)
    deadline = time.time() + timeout
    with paths["lock"].open("a+b") as fh:
        if fh.seek(0, os.SEEK_END) == 0:
            fh.write(b"0")
            fh.flush()
        while True:
            try:
                fh.seek(0)
                if msvcrt is not None:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                elif fcntl is not None:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                else:
                    raise WorktreeError("No supported file locking backend is available")
                break
            except OSError:
                if time.time() >= deadline:
                    raise WorktreeError(f"Timed out waiting for state lock: {paths['lock']}")
                time.sleep(0.1)
        try:
            fh.seek(0)
            fh.truncate()
            fh.write(json.dumps({"pid": os.getpid(), "lockedAt": utc_now()}).encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
            yield
        finally:
            fh.seek(0)
            if msvcrt is not None:
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            elif fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def empty_state(project: dict) -> dict:
    return {
        "version": VERSION,
        "project": {
            "projectId": project["projectId"],
            "name": project["name"],
            "commonDir": project["commonDir"],
            "baseBranch": project["baseBranch"],
        },
        "tasks": [],
        "lastScanAt": None,
    }


def load_state(project: dict) -> dict:
    paths = state_paths(project["commonDir"])
    if not paths["state"].exists():
        return empty_state(project)
    try:
        with paths["state"].open("r", encoding="utf-8") as fh:
            state = json.load(fh)
    except json.JSONDecodeError as exc:
        raise WorktreeError(f"State file is not valid JSON: {paths['state']}: {exc}") from exc
    state.setdefault("version", VERSION)
    state.setdefault("project", {})
    state["project"].update(
        {
            "projectId": project["projectId"],
            "name": project["name"],
            "commonDir": project["commonDir"],
            "baseBranch": state["project"].get("baseBranch") or project["baseBranch"],
        }
    )
    state.setdefault("tasks", [])
    return state


def save_state(project: dict, state: dict) -> None:
    paths = state_paths(project["commonDir"])
    paths["dir"].mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="state-", suffix=".json", dir=str(paths["dir"]))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(temp_name, paths["state"])
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_name)


def append_event(project: dict, event: dict) -> None:
    paths = state_paths(project["commonDir"])
    paths["dir"].mkdir(parents=True, exist_ok=True)
    event = {"time": utc_now(), **event}
    with paths["events"].open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def current_branch(path: Path) -> str | None:
    branch = git_output(["symbolic-ref", "--quiet", "--short", "HEAD"], path)
    return branch or None


def ahead_behind(path: Path, branch: str | None, base: str) -> tuple[int | None, int | None]:
    if not branch:
        return None, None
    result = run_git(["rev-list", "--left-right", "--count", f"{base}...{branch}"], path, check=False)
    if result.returncode != 0:
        return None, None
    parts = result.stdout.strip().split()
    if len(parts) != 2:
        return None, None
    behind, ahead = int(parts[0]), int(parts[1])
    return ahead, behind


def inspect_worktree(entry: dict, base_branch: str) -> dict:
    path = Path(entry["path"])
    exists = path.exists()
    branch = entry.get("branch") or (current_branch(path) if exists else None)
    head = entry.get("head")
    status_text = ""
    dirty = False
    untracked = 0
    if exists and not entry.get("bare"):
        head = git_output(["rev-parse", "--verify", "HEAD"], path, default=head)
        status_text = git_output(["status", "--porcelain=v1", "--untracked-files=all"], path, default="") or ""
        dirty = bool(status_text.strip())
        untracked = sum(1 for line in status_text.splitlines() if line.startswith("??"))
    ahead, behind = ahead_behind(path, branch, base_branch) if exists and branch else (None, None)
    return {
        "exists": exists,
        "dirty": dirty,
        "untracked": untracked,
        "ahead": ahead,
        "behind": behind,
        "latestCommit": head,
        "locked": bool(entry.get("locked")),
        "lockedReason": entry.get("lockedReason"),
        "prunable": bool(entry.get("prunable")),
        "detached": bool(entry.get("detached")),
        "bare": bool(entry.get("bare")),
    }


def generated_task_id(project_id: str, worktree_path: str) -> str:
    digest = hashlib.sha1(f"{project_id}|{normalize_path(worktree_path)}".encode("utf-8")).hexdigest()
    return f"wt-{digest[:8]}"


def find_task(state: dict, task_id: str) -> dict:
    for task in state.get("tasks", []):
        if task.get("taskId") == task_id:
            return task
    raise WorktreeError(f"Task not found: {task_id}")


def validate_project_worktree(project: dict, path: Path, label: str) -> Path:
    resolved = path.resolve()
    allowed = {normalize_path(Path(entry["path"]).resolve()) for entry in project.get("worktrees", [])}
    if normalize_path(resolved) not in allowed:
        raise WorktreeError(f"{label} is not a registered worktree for this project: {resolved}")
    common = git_output(["rev-parse", "--path-format=absolute", "--git-common-dir"], resolved)
    if not common or normalize_path(common) != normalize_path(project["commonDir"]):
        raise WorktreeError(f"{label} git common directory does not match this project: {resolved}")
    return resolved


def derive_status(task: dict, git: dict, base_branch: str) -> str:
    previous = task.get("status")
    if previous == "已合并":
        return previous
    if task.get("merge", {}).get("blockedReason") == "conflict":
        return "合并有冲突需人工处理"
    if not git.get("exists", True):
        return "missing"
    if task.get("branch") == base_branch:
        return "基线工作区"
    if git.get("dirty"):
        return "有未提交修改"
    tests = task.get("tests", {}).get("status", "unknown")
    ahead = git.get("ahead")
    behind = git.get("behind")
    if behind and behind > 0:
        return "已落后主分支需同步"
    if ahead and ahead > 0:
        if tests == "passed":
            return "已测试待合并批准"
        return "已提交待测试"
    if previous in STATUS_VALUES:
        return previous
    return "进行中"


def derive_merge_summary(task: dict) -> str:
    merge = task.get("merge", {})
    git = task.get("git", {})
    tests = task.get("tests", {})
    if merge.get("blockedReason"):
        return f"blocked: {merge['blockedReason']}"
    if task.get("status") == "已落后主分支需同步":
        return "blocked: behind base"
    if git.get("dirty"):
        return "blocked: dirty"
    if tests.get("status") and tests.get("status") != "passed" and git.get("ahead") and git["ahead"] > 0:
        return "blocked: tests not passed"
    if task.get("status") == "已合并":
        commit = merge.get("mergeCommit")
        return f"merged: {commit[:10]}" if commit else "merged"
    if merge.get("ready"):
        return "ready"
    if task.get("status") == "已测试待合并批准":
        return "awaiting approval"
    return "-"


def default_cleanup() -> dict:
    return {"worktreeRemoved": False, "approved": False, "removedAt": None}


def derive_cleanup_summary(task: dict) -> str:
    cleanup = task.get("cleanup", {})
    git = task.get("git", {})
    if task.get("status") == "基线工作区":
        return "不可删除"
    if task.get("status") != "已合并":
        return "保留"
    if cleanup.get("worktreeRemoved") or git.get("exists") is False:
        return "已删除"
    return "可删除"


def reconcile_state(project: dict, state: dict) -> dict:
    now = utc_now()
    base_branch = state.get("project", {}).get("baseBranch") or project["baseBranch"]
    existing_by_path = {normalize_path(t.get("worktreePath", "")): t for t in state.get("tasks", []) if t.get("worktreePath")}
    existing_by_branch = {t.get("branch"): t for t in state.get("tasks", []) if t.get("branch")}
    seen: set[str] = set()
    tasks = state.setdefault("tasks", [])

    for entry in project["worktrees"]:
        path = str(Path(entry["path"]).resolve())
        branch = entry.get("branch") or current_branch(Path(path))
        task = existing_by_path.get(normalize_path(path)) or existing_by_branch.get(branch)
        if task is None:
            task = {
                "projectId": project["projectId"],
                "taskId": generated_task_id(project["projectId"], path),
                "title": "Base worktree" if branch == base_branch else f"Worktree {branch or Path(path).name}",
                "worktreePath": path,
                "branch": branch,
                "baseBranch": base_branch,
                "owner": None,
                "status": "基线工作区" if branch == base_branch else "进行中",
                "activeUpdate": "",
                "git": {},
                "tests": {"status": "unknown", "lastRun": None},
                "merge": {"ready": False, "approved": False, "blockedReason": None},
                "cleanup": default_cleanup(),
                "createdAt": now,
                "updatedAt": now,
            }
            tasks.append(task)
        git = inspect_worktree(entry, base_branch)
        task.update(
            {
                "projectId": project["projectId"],
                "worktreePath": path,
                "branch": branch,
                "baseBranch": base_branch,
                "git": git,
                "updatedAt": now,
            }
        )
        task.setdefault("tests", {"status": "unknown", "lastRun": None})
        task.setdefault("merge", {"ready": False, "approved": False, "blockedReason": None})
        task.setdefault("cleanup", default_cleanup())
        if branch == base_branch:
            task["merge"]["ready"] = False
        else:
            task["merge"]["ready"] = bool(
                git.get("ahead")
                and git.get("ahead") > 0
                and not (git.get("behind") and git.get("behind") > 0)
                and not git.get("dirty")
                and task.get("tests", {}).get("status") == "passed"
            )
        task["status"] = derive_status(task, git, base_branch)
        task["merge"]["summary"] = derive_merge_summary(task)
        seen.add(normalize_path(path))

    for task in tasks:
        if normalize_path(task.get("worktreePath", "")) not in seen:
            task.setdefault("git", {})["exists"] = False
            if task.get("status") not in ("已合并", "orphaned"):
                stored_path = Path(task.get("worktreePath", ""))
                task["status"] = "orphaned" if stored_path.exists() else "missing"
            task.setdefault("merge", {})["summary"] = derive_merge_summary(task)
            task.setdefault("cleanup", default_cleanup())
            task["updatedAt"] = now

    state["lastScanAt"] = now
    return state


def render_markdown(state: dict) -> str:
    lines = [
        "# Worktree Status",
        "",
        f"- Project: `{state.get('project', {}).get('name', '')}`",
        f"- Project ID: `{state.get('project', {}).get('projectId', '')}`",
        f"- Last scan: `{state.get('lastScanAt', '')}`",
        "",
        "| Task | Status | Branch | Dirty | Ahead | Behind | Tests | Cleanup | Worktree |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for task in sorted(state.get("tasks", []), key=lambda t: (t.get("status") == "已合并", t.get("title", ""))):
        git = task.get("git", {})
        tests = task.get("tests", {})
        lines.append(
            "| {title} | {status} | `{branch}` | {dirty} | {ahead} | {behind} | {tests} | {cleanup} | `{path}` |".format(
                title=str(task.get("title", "")).replace("|", "\\|"),
                status=task.get("status", ""),
                branch=task.get("branch", ""),
                dirty="yes" if git.get("dirty") else "no",
                ahead=git.get("ahead") if git.get("ahead") is not None else "",
                behind=git.get("behind") if git.get("behind") is not None else "",
                tests=tests.get("status", "unknown"),
                cleanup=derive_cleanup_summary(task),
                path=task.get("worktreePath", ""),
            )
        )
    lines.append("")
    return "\n".join(lines)


def refresh_markdown(project: dict, state: dict) -> None:
    shared = state_paths(project["commonDir"])["dir"] / "status.md"
    shared.parent.mkdir(parents=True, exist_ok=True)
    shared.write_text(render_markdown(state), encoding="utf-8")
    if os.environ.get("WORKTREE_ORCHESTRATOR_WRITE_WORKTREE_MIRROR") == "1":
        mirror = Path(project["root"]) / ".omx" / "worktrees" / "status.md"
        mirror.parent.mkdir(parents=True, exist_ok=True)
        mirror.write_text(render_markdown(state), encoding="utf-8")


def scan_project(cwd: Path, record_event: bool = True) -> dict:
    project = discover_project(cwd)
    paths = state_paths(project["commonDir"])
    with state_lock(paths):
        state = load_state(project)
        state = reconcile_state(project, state)
        save_state(project, state)
        if record_event:
            append_event(project, {"type": "scan", "projectId": project["projectId"], "taskCount": len(state.get("tasks", []))})
    refresh_markdown(project, state)
    return state


def table(state: dict) -> str:
    rows = []
    for task in state.get("tasks", []):
        git = task.get("git", {})
        rows.append(
            [
                task.get("taskId", ""),
                task.get("status", ""),
                task.get("branch", ""),
                "dirty" if git.get("dirty") else "clean",
                str(git.get("ahead") if git.get("ahead") is not None else ""),
                str(git.get("behind") if git.get("behind") is not None else ""),
                task.get("tests", {}).get("status", "unknown"),
                derive_cleanup_summary(task),
                task.get("title", ""),
            ]
        )
    headers = ["Task", "Status", "Branch", "Tree", "Ahead", "Behind", "Tests", "Cleanup", "Title"]
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = min(max(widths[i], len(cell)), 36)
    fmt = "  ".join("{:<" + str(w) + "}" for w in widths)
    output = [fmt.format(*headers), fmt.format(*["-" * w for w in widths])]
    for row in rows:
        output.append(fmt.format(*[cell[: widths[i]] for i, cell in enumerate(row)]))
    return "\n".join(output)


def primary_worktree_path(project: dict) -> Path:
    if not project["worktrees"]:
        return Path(project["root"])
    return Path(project["worktrees"][0]["path"]).resolve()


def assert_target_path_safe(target: Path, project: dict) -> None:
    if target.exists():
        raise WorktreeError(f"Target worktree path already exists: {target}")
    for entry in project["worktrees"]:
        root = Path(entry["path"]).resolve()
        if is_relative_to(target, root) or is_relative_to(root, target):
            raise WorktreeError(f"Target path overlaps existing worktree: {target} vs {root}")


def cmd_scan(args: argparse.Namespace) -> int:
    state = scan_project(Path(args.cwd), record_event=True)
    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
    else:
        print(table(state))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    state = scan_project(Path(args.cwd), record_event=False)
    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
    else:
        print(table(state))
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd)
    project = discover_project(cwd)
    base_branch = args.base or project["baseBranch"]
    task_id = args.task_id or _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:4]
    slug = slugify(args.title)
    branch = args.branch or f"task/{task_id}-{slug}"
    target = Path(args.path).resolve() if args.path else Path(str(primary_worktree_path(project)) + ".worktrees") / f"{task_id}-{slug}"
    assert_target_path_safe(target, project)
    branch_exists = run_git(["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], cwd, check=False).returncode == 0
    if branch_exists:
        raise WorktreeError(f"Branch already exists: {branch}")
    run_git(["worktree", "add", "-b", branch, str(target), base_branch], cwd)

    project = discover_project(cwd)
    paths = state_paths(project["commonDir"])
    with state_lock(paths):
        state = load_state(project)
        state.setdefault("tasks", []).append(
            {
                "projectId": project["projectId"],
                "taskId": task_id,
                "title": args.title,
                "worktreePath": str(target),
                "branch": branch,
                "baseBranch": base_branch,
                "owner": args.owner,
                "status": "进行中",
                "activeUpdate": args.note or "",
                "git": {},
                "tests": {"status": "unknown", "lastRun": None},
                "merge": {"ready": False, "approved": False, "blockedReason": None},
                "cleanup": default_cleanup(),
                "createdAt": utc_now(),
                "updatedAt": utc_now(),
            }
        )
        state = reconcile_state(project, state)
        save_state(project, state)
        append_event(project, {"type": "start", "taskId": task_id, "branch": branch, "worktreePath": str(target)})
    refresh_markdown(project, state)
    print(json.dumps({"taskId": task_id, "branch": branch, "worktreePath": str(target)}, ensure_ascii=False, indent=2))
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    project = discover_project(Path(args.cwd))
    paths = state_paths(project["commonDir"])
    with state_lock(paths):
        state = reconcile_state(project, load_state(project))
        task = find_task(state, args.task_id)
        if args.status:
            if args.status not in STATUS_VALUES:
                raise WorktreeError(f"Unsupported status: {args.status}")
            task["status"] = args.status
        if args.note is not None:
            task["activeUpdate"] = args.note
        if args.owner is not None:
            task["owner"] = args.owner
        task["updatedAt"] = utc_now()
        save_state(project, state)
        append_event(project, {"type": "update", "taskId": args.task_id, "status": task.get("status"), "note": args.note})
    refresh_markdown(project, state)
    print(json.dumps(task, ensure_ascii=False, indent=2))
    return 0


def cmd_ready(args: argparse.Namespace) -> int:
    if args.tests not in {"passed", "failed", "unknown"}:
        raise WorktreeError("--tests must be passed, failed, or unknown")
    project = discover_project(Path(args.cwd))
    paths = state_paths(project["commonDir"])
    with state_lock(paths):
        state = reconcile_state(project, load_state(project))
        task = find_task(state, args.task_id)
        task["tests"] = {"status": args.tests, "lastRun": utc_now()}
        if args.tests == "failed":
            task["status"] = "进行中"
            task.setdefault("merge", {})["ready"] = False
        task["updatedAt"] = utc_now()
        if args.tests != "failed":
            task["status"] = derive_status(task, task.get("git", {}), task.get("baseBranch") or project["baseBranch"])
            git = task.get("git", {})
            task.setdefault("merge", {})["ready"] = bool(
                args.tests == "passed"
                and git.get("ahead")
                and git.get("ahead") > 0
                and not (git.get("behind") and git.get("behind") > 0)
                and not git.get("dirty")
            )
        task.setdefault("merge", {})["summary"] = derive_merge_summary(task)
        save_state(project, state)
        append_event(project, {"type": "ready", "taskId": args.task_id, "tests": args.tests})
    refresh_markdown(project, state)
    print(json.dumps(task, ensure_ascii=False, indent=2))
    return 0


def cmd_commit(args: argparse.Namespace) -> int:
    if not has_cjk(args.message):
        raise WorktreeError("Commit message must contain Chinese text")
    state = scan_project(Path(args.cwd), record_event=False)
    project = discover_project(Path(args.cwd))
    task = find_task(state, args.task_id)
    worktree = validate_project_worktree(project, Path(task["worktreePath"]), "Task worktree")
    status = git_output(["status", "--porcelain=v1", "--untracked-files=all"], worktree, default="") or ""
    if not status.strip():
        raise WorktreeError("No changes to commit")
    run_git(["add", "-A"], worktree)
    staged = git_output(["diff", "--cached", "--name-status"], worktree, default="") or ""
    staged_files = [line.strip() for line in staged.splitlines() if line.strip()]
    run_git(["commit", "-m", args.message], worktree)
    sha = git_output(["rev-parse", "--verify", "HEAD"], worktree)
    state = scan_project(Path(args.cwd), record_event=False)
    project = discover_project(Path(args.cwd))
    paths = state_paths(project["commonDir"])
    with state_lock(paths):
        state = load_state(project)
        task = find_task(state, args.task_id)
        task.setdefault("git", {})["latestCommit"] = sha
        task["status"] = derive_status(task, task.get("git", {}), task.get("baseBranch") or project["baseBranch"])
        task["updatedAt"] = utc_now()
        save_state(project, state)
        append_event(
            project,
            {"type": "commit", "taskId": args.task_id, "message": args.message, "sha": sha, "stagedFiles": staged_files},
        )
    refresh_markdown(project, state)
    print(json.dumps({"taskId": args.task_id, "commit": sha, "message": args.message, "stagedFiles": staged_files}, ensure_ascii=False, indent=2))
    return 0


def read_events(project: dict, limit: int = 100) -> list[dict]:
    path = state_paths(project["commonDir"])["events"]
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    events = []
    for line in lines:
        with contextlib.suppress(json.JSONDecodeError):
            events.append(json.loads(line))
    return events


def branch_ref(branch: str) -> str:
    return branch if branch.startswith("refs/") else f"refs/heads/{branch}"


def resolve_commit_ref(cwd: Path, ref: str, label: str) -> str:
    commit = git_output(["rev-parse", "--verify", f"{ref}^{{commit}}"], cwd)
    if not commit:
        raise WorktreeError(f"{label} does not resolve to a commit: {ref}")
    return commit


def short_ref(value: str | None) -> str:
    rendered = value or ""
    return rendered[:10] if re.fullmatch(r"[0-9a-fA-F]{40}", rendered) else rendered


def task_commit_range(cwd: Path, task: dict, project: dict) -> dict:
    merge = task.get("merge", {})
    preflight = merge.get("preflight", {})
    if task.get("status") == "已合并" and preflight.get("baseSha") and preflight.get("sourceSha"):
        start = resolve_commit_ref(cwd, preflight["baseSha"], "Merge base commit")
        end = resolve_commit_ref(cwd, preflight["sourceSha"], "Merge source commit")
        return {
            "start": start,
            "end": end,
            "display": f"{short_ref(start)}..{short_ref(end)}",
            "kind": "merged_preflight",
        }

    if task.get("status") == "已合并" and merge.get("mergeCommit"):
        merge_commit = resolve_commit_ref(cwd, merge["mergeCommit"], "Merge commit")
        parents = (git_output(["show", "-s", "--pretty=%P", merge_commit], cwd, default="") or "").split()
        if len(parents) >= 2:
            start = resolve_commit_ref(cwd, parents[0], "Merge first parent")
            end = resolve_commit_ref(cwd, parents[1], "Merge second parent")
            return {
                "start": start,
                "end": end,
                "display": f"{short_ref(start)}..{short_ref(end)}",
                "kind": "merge_parents",
            }

    branch = task.get("branch")
    base_branch = task.get("baseBranch") or project["baseBranch"]
    if not branch:
        raise WorktreeError("Task has no branch recorded")
    start_ref = branch_ref(base_branch)
    end_ref = branch_ref(branch)
    resolve_commit_ref(cwd, start_ref, "Base branch")
    resolve_commit_ref(cwd, end_ref, "Task branch")
    return {
        "start": start_ref,
        "end": end_ref,
        "display": f"{base_branch}..{branch}",
        "kind": "branch",
    }


def read_task_commits(cwd: Path, commit_range: dict, limit: int) -> list[dict]:
    capped_limit = max(1, min(limit, 100))
    result = run_git(
        [
            "log",
            f"--max-count={capped_limit}",
            "--date=iso-strict",
            "--pretty=format:%H%x1f%h%x1f%aI%x1f%an%x1f%s",
            f"{commit_range['start']}..{commit_range['end']}",
        ],
        cwd,
        check=False,
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout or "").strip()
        raise WorktreeError(f"git log failed: {details}")
    commits = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f", 4)
        if len(parts) != 5:
            raise WorktreeError("Unexpected git log output format")
        sha, short_sha, date, author, subject = parts
        commits.append({"sha": sha, "shortSha": short_sha, "date": date, "author": author, "subject": subject})
    return commits


def task_events(project: dict, task_id: str, limit: int = 20) -> list[dict]:
    events = [event for event in read_events(project, limit=500) if event.get("taskId") == task_id]
    return events[-limit:]


def build_commits_payload(cwd: Path, task_id: str, limit: int = 20) -> dict:
    state = scan_project(cwd, record_event=False)
    project = discover_project(cwd)
    task = find_task(state, task_id)
    commit_range = task_commit_range(cwd, task, project)
    commits = read_task_commits(cwd, commit_range, limit)
    merge = task.get("merge", {})
    return {
        "taskId": task_id,
        "title": task.get("title"),
        "status": task.get("status"),
        "branch": task.get("branch"),
        "baseBranch": task.get("baseBranch") or project["baseBranch"],
        "range": commit_range["display"],
        "rangeKind": commit_range["kind"],
        "limit": max(1, min(limit, 100)),
        "commits": commits,
        "merge": {
            "approved": bool(merge.get("approved")),
            "mergedAt": merge.get("mergedAt"),
            "mergeCommit": merge.get("mergeCommit"),
            "summary": merge.get("summary"),
        },
        "events": task_events(project, task_id),
    }


def render_commits(payload: dict) -> str:
    lines = [
        f"任务: {payload.get('title') or payload.get('taskId')} ({payload.get('taskId')})",
        f"分支: {payload.get('branch') or '-'}",
        f"范围: {payload.get('range') or '-'}",
    ]
    merge = payload.get("merge", {})
    if merge.get("mergeCommit"):
        lines.append(f"合并: {short_ref(merge.get('mergeCommit'))} {merge.get('mergedAt') or ''}".rstrip())
    lines.append("")

    commits = payload.get("commits", [])
    if not commits:
        lines.append("没有相对任务范围的提交。")
    else:
        headers = ["Commit", "Date", "Author", "Subject"]
        rows = [
            [commit["shortSha"], commit.get("date", "")[:19], commit.get("author", ""), commit.get("subject", "")]
            for commit in commits
        ]
        widths = [len(header) for header in headers]
        for row in rows:
            for index, cell in enumerate(row):
                widths[index] = min(max(widths[index], len(cell)), 48)
        fmt = "  ".join("{:<" + str(width) + "}" for width in widths)
        lines.append(fmt.format(*headers))
        lines.append(fmt.format(*["-" * width for width in widths]))
        for row in rows:
            lines.append(fmt.format(*[cell[: widths[index]] for index, cell in enumerate(row)]))

    events = payload.get("events", [])
    if events:
        lines.append("")
        lines.append("最近事件:")
        for event in events[-8:]:
            detail = event.get("message") or event.get("reason") or event.get("tests") or ""
            lines.append(f"- {event.get('time', '')} {event.get('type', '')} {detail}".rstrip())
    return "\n".join(lines)


def cmd_commits(args: argparse.Namespace) -> int:
    payload = build_commits_payload(Path(args.cwd), args.task_id, args.limit)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_commits(payload))
    return 0


def dashboard_handler(cwd: Path, asset_dir: Path):
    class Handler(http.server.SimpleHTTPRequestHandler):
        server_version = "WorktreeDashboard/1.0"

        def log_message(self, fmt: str, *args) -> None:
            sys.stderr.write("[dashboard] " + fmt % args + "\n")

        def send_json(self, payload: dict | list, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/api/status":
                try:
                    self.send_json(scan_project(cwd, record_event=False))
                except Exception as exc:
                    self.send_json({"error": str(exc)}, status=500)
                return
            if parsed.path == "/api/project":
                try:
                    project = discover_project(cwd)
                    self.send_json({k: project[k] for k in ("projectId", "name", "root", "commonDir", "baseBranch")})
                except Exception as exc:
                    self.send_json({"error": str(exc)}, status=500)
                return
            if parsed.path == "/api/events":
                try:
                    project = discover_project(cwd)
                    self.send_json(read_events(project))
                except Exception as exc:
                    self.send_json({"error": str(exc)}, status=500)
                return
            if parsed.path == "/api/commits":
                query = urllib.parse.parse_qs(parsed.query)
                task_id = (query.get("taskId") or [""])[0]
                if not task_id:
                    self.send_json({"error": "Missing taskId"}, status=400)
                    return
                try:
                    limit = int((query.get("limit") or ["20"])[0])
                except ValueError:
                    limit = 20
                try:
                    self.send_json(build_commits_payload(cwd, task_id, limit))
                except Exception as exc:
                    self.send_json({"error": str(exc)}, status=500)
                return
            if parsed.path.startswith("/api/"):
                self.send_json({"error": f"Unknown API endpoint: {parsed.path}"}, status=404)
                return
            rel = "index.html" if parsed.path in ("", "/") else parsed.path.lstrip("/")
            candidate = (asset_dir / rel).resolve()
            if not is_relative_to(candidate, asset_dir):
                self.send_error(403)
                return
            if not candidate.exists() or candidate.is_dir():
                self.send_error(404)
                return
            content = candidate.read_bytes()
            mime = "text/html; charset=utf-8"
            if candidate.suffix == ".js":
                mime = "text/javascript; charset=utf-8"
            elif candidate.suffix == ".css":
                mime = "text/css; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    return Handler


class ThreadingHTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def cmd_dashboard(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd)
    scan_project(cwd, record_event=True)
    asset_dir = Path(__file__).resolve().parents[1] / "assets" / "dashboard"
    if not asset_dir.exists():
        raise WorktreeError(f"Dashboard assets missing: {asset_dir}")
    server = ThreadingHTTPServer((args.host, args.port), dashboard_handler(cwd, asset_dir))
    host, port = server.server_address
    print(f"Dashboard: http://{host}:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


def block_merge(project: dict, state: dict, task: dict, reason: str, status: str | None = None) -> None:
    task.setdefault("merge", {})["blockedReason"] = reason
    task.setdefault("merge", {})["ready"] = False
    if status:
        task["status"] = status
    task["merge"]["summary"] = derive_merge_summary(task)
    task["updatedAt"] = utc_now()
    save_state(project, state)
    append_event(project, {"type": "merge_blocked", "taskId": task.get("taskId"), "reason": reason})


def find_base_worktree(project: dict, base_branch: str) -> Path | None:
    for entry in project["worktrees"]:
        if entry.get("branch") == base_branch and Path(entry["path"]).exists():
            return Path(entry["path"])
    return None


def merge_tree_unavailable(result: subprocess.CompletedProcess) -> bool:
    text = f"{result.stdout}\n{result.stderr}".lower()
    unsupported_markers = (
        "usage: git merge-tree",
        "unknown option",
        "unknown switch",
        "not a git command",
        "invalid option",
    )
    return result.returncode in {128, 129} and any(marker in text for marker in unsupported_markers)


def cmd_merge(args: argparse.Namespace) -> int:
    if not args.approved:
        raise WorktreeError("Merge requires explicit --approved")
    state = scan_project(Path(args.cwd), record_event=False)
    project = discover_project(Path(args.cwd))
    paths = state_paths(project["commonDir"])
    with state_lock(paths):
        state = reconcile_state(project, load_state(project))
        task = find_task(state, args.task_id)
        source = validate_project_worktree(project, Path(task["worktreePath"]), "Source worktree")
        source_branch = task.get("branch")
        base_branch = args.base or task.get("baseBranch") or project["baseBranch"]
        base_path = find_base_worktree(project, base_branch)
        if not source_branch:
            block_merge(project, state, task, "missing_source_branch")
            raise WorktreeError("Task has no source branch")
        if base_path is None:
            block_merge(project, state, task, "missing_base_worktree")
            raise WorktreeError(f"Base branch is not checked out in a worktree: {base_branch}")
        base_path = validate_project_worktree(project, base_path, "Base worktree")
        source_status = git_output(["status", "--porcelain=v1", "--untracked-files=all"], source, default="") or ""
        base_status = git_output(["status", "--porcelain=v1", "--untracked-files=all"], base_path, default="") or ""
        if source_status.strip():
            block_merge(project, state, task, "dirty_source")
            raise WorktreeError(f"Source worktree has uncommitted changes: {source}")
        if base_status.strip():
            block_merge(project, state, task, "dirty_base")
            raise WorktreeError(f"Base worktree has uncommitted changes: {base_path}")
        git_state = task.get("git", {})
        if git_state.get("behind") and git_state["behind"] > 0:
            block_merge(project, state, task, "behind_base", "已落后主分支需同步")
            raise WorktreeError(f"Task branch is behind {base_branch}; sync and retest before merge")
        if task.get("tests", {}).get("status") != "passed":
            block_merge(project, state, task, "tests_not_passed")
            raise WorktreeError("Task tests are not marked as passed")
        if not task.get("merge", {}).get("ready"):
            block_merge(project, state, task, "not_merge_ready")
            raise WorktreeError("Task is not marked merge-ready")
        commits = git_output(["rev-list", "--count", f"{base_branch}..{source_branch}"], base_path, default="0") or "0"
        if int(commits) == 0:
            block_merge(project, state, task, "nothing_to_merge")
            raise WorktreeError(f"No commits to merge from {source_branch} into {base_branch}")
        base_sha = git_output(["rev-parse", "--verify", base_branch], base_path)
        source_sha = git_output(["rev-parse", "--verify", source_branch], base_path)
        task.setdefault("merge", {})["preflight"] = {"baseSha": base_sha, "sourceSha": source_sha, "checkedAt": utc_now(), "method": "merge-tree"}
        merge_tree = run_git(["merge-tree", "--write-tree", base_branch, source_branch], base_path, check=False)
        if merge_tree.returncode != 0 and merge_tree_unavailable(merge_tree):
            task.setdefault("merge", {})["preflight"]["method"] = "merge-fallback"
        elif merge_tree.returncode != 0:
            block_merge(project, state, task, "conflict", "合并有冲突需人工处理")
            raise WorktreeError((merge_tree.stdout or merge_tree.stderr or "Merge conflict detected").strip())
        message = args.message or f"合并任务：{task.get('title') or source_branch}"
        result = run_git(["merge", "--no-ff", source_branch, "-m", message], base_path, check=False)
        if result.returncode != 0:
            run_git(["merge", "--abort"], base_path, check=False)
            block_merge(project, state, task, "conflict", "合并有冲突需人工处理")
            raise WorktreeError((result.stdout or result.stderr or "Merge failed").strip())
        merged_sha = git_output(["rev-parse", "--verify", "HEAD"], base_path)
        state = reconcile_state(project, state)
        task = find_task(state, args.task_id)
        task["status"] = "已合并"
        task.setdefault("merge", {}).update(
            {
                "ready": False,
                "approved": True,
                "blockedReason": None,
                "mergedAt": utc_now(),
                "mergeCommit": merged_sha,
                "preflight": {"baseSha": base_sha, "sourceSha": source_sha, "checkedAt": utc_now()},
            }
        )
        task["merge"]["summary"] = derive_merge_summary(task)
        task["updatedAt"] = utc_now()
        save_state(project, state)
        append_event(project, {"type": "merge", "taskId": args.task_id, "mergeCommit": merged_sha, "message": message})
    refresh_markdown(project, state)
    print(json.dumps({"taskId": args.task_id, "mergeCommit": merged_sha, "message": message}, ensure_ascii=False, indent=2))
    return 0


def cmd_delete_worktree(args: argparse.Namespace) -> int:
    if not args.approved:
        raise WorktreeError("Worktree deletion requires explicit --approved")
    cwd = Path(args.cwd).resolve()
    scan_project(cwd, record_event=False)
    project = discover_project(cwd)
    project_after = project
    removed_path: Path | None = None
    already_removed = False
    paths = state_paths(project["commonDir"])
    with state_lock(paths):
        state = reconcile_state(project, load_state(project))
        task = find_task(state, args.task_id)
        source_branch = task.get("branch")
        base_branch = task.get("baseBranch") or project["baseBranch"]
        if task.get("status") == "基线工作区" or source_branch == base_branch:
            raise WorktreeError("Base worktree cannot be deleted")
        if task.get("status") != "已合并":
            raise WorktreeError("Worktree can only be deleted after the task has been merged")
        merge = task.get("merge", {})
        if not merge.get("approved") or not merge.get("mergeCommit"):
            raise WorktreeError("Task merge record is incomplete; refusing to delete worktree")
        if not task.get("worktreePath"):
            raise WorktreeError("Task has no worktree path recorded")
        removed_path = Path(task["worktreePath"]).resolve()
        cleanup = task.setdefault("cleanup", default_cleanup())

        if cleanup.get("worktreeRemoved") or task.get("git", {}).get("exists") is False:
            already_removed = True
            cleanup.update(
                {
                    "worktreeRemoved": True,
                    "approved": True,
                    "removedAt": cleanup.get("removedAt") or utc_now(),
                    "worktreePath": str(removed_path),
                }
            )
            task.setdefault("git", {})["exists"] = False
            task["updatedAt"] = utc_now()
        else:
            if not source_branch:
                raise WorktreeError("Task has no source branch")
            source = validate_project_worktree(project, removed_path, "Task worktree")
            if is_relative_to(cwd, source):
                raise WorktreeError("Cannot delete the current worktree; run this command from another worktree")
            source_status = git_output(["status", "--porcelain=v1", "--untracked-files=all"], source, default="") or ""
            if source_status.strip():
                raise WorktreeError(f"Task worktree has uncommitted changes: {source}")
            ancestor = run_git(["merge-base", "--is-ancestor", source_branch, base_branch], source, check=False)
            if ancestor.returncode != 0:
                raise WorktreeError(f"Task branch is not confirmed merged into {base_branch}; refusing to delete worktree")
            result = run_git(["worktree", "remove", str(source)], cwd, check=False)
            if result.returncode != 0:
                details = (result.stderr or result.stdout or "").strip()
                raise WorktreeError(f"git worktree remove failed: {details}")

            project_after = discover_project(cwd)
            state = reconcile_state(project_after, state)
            task = find_task(state, args.task_id)
            cleanup = task.setdefault("cleanup", default_cleanup())
            cleanup.update(
                {
                    "worktreeRemoved": True,
                    "approved": True,
                    "removedAt": utc_now(),
                    "worktreePath": str(source),
                }
            )
            task.setdefault("git", {})["exists"] = False
            task["updatedAt"] = utc_now()

        save_state(project_after, state)
        append_event(
            project_after,
            {
                "type": "delete_worktree",
                "taskId": args.task_id,
                "worktreePath": str(removed_path),
                "alreadyRemoved": already_removed,
            },
        )
    refresh_markdown(project_after, state)
    print(
        json.dumps(
            {"taskId": args.task_id, "worktreePath": str(removed_path), "alreadyRemoved": already_removed},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Coordinate git task worktrees with shared state and a local dashboard.")
    parser.add_argument("--cwd", default=os.getcwd(), help="Project/worktree directory to operate in")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Scan project worktrees and reconcile shared state")
    scan.add_argument("--json", action="store_true")
    scan.set_defaults(func=cmd_scan)

    status = sub.add_parser("status", help="Print current project worktree status")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    start = sub.add_parser("start", help="Create a task branch and worktree")
    start.add_argument("--title", required=True)
    start.add_argument("--task-id")
    start.add_argument("--branch")
    start.add_argument("--base")
    start.add_argument("--path")
    start.add_argument("--owner")
    start.add_argument("--note")
    start.set_defaults(func=cmd_start)

    update = sub.add_parser("update", help="Update task progress")
    update.add_argument("--task-id", required=True)
    update.add_argument("--status")
    update.add_argument("--note")
    update.add_argument("--owner")
    update.set_defaults(func=cmd_update)

    ready = sub.add_parser("ready", help="Mark test readiness")
    ready.add_argument("--task-id", required=True)
    ready.add_argument("--tests", required=True, choices=["passed", "failed", "unknown"])
    ready.set_defaults(func=cmd_ready)

    commit = sub.add_parser("commit", help="Stage and commit task work with a Chinese message")
    commit.add_argument("--task-id", required=True)
    commit.add_argument("--message", required=True)
    commit.set_defaults(func=cmd_commit)

    commits = sub.add_parser("commits", help="Show read-only commit history for a task")
    commits.add_argument("--task-id", required=True)
    commits.add_argument("--limit", type=int, default=20)
    commits.add_argument("--json", action="store_true")
    commits.set_defaults(func=cmd_commits)

    dashboard = sub.add_parser("dashboard", help="Serve the local worktree dashboard")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8765)
    dashboard.set_defaults(func=cmd_dashboard)

    merge = sub.add_parser("merge", help="Merge an approved task branch into the base branch")
    merge.add_argument("--task-id", required=True)
    merge.add_argument("--approved", action="store_true")
    merge.add_argument("--base")
    merge.add_argument("--message")
    merge.set_defaults(func=cmd_merge)

    delete_worktree = sub.add_parser("delete-worktree", help="Delete a merged task worktree after explicit approval")
    delete_worktree.add_argument("--task-id", required=True)
    delete_worktree.add_argument("--approved", action="store_true")
    delete_worktree.set_defaults(func=cmd_delete_worktree)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except WorktreeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
