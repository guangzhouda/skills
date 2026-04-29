from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request


SCRIPT = Path(__file__).with_name("worktree_task.py")
spec = importlib.util.spec_from_file_location("worktree_task", SCRIPT)
wt = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(wt)


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class WorktreeTaskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        git(self.root, "init", "-b", "main")
        git(self.root, "config", "user.email", "test@example.com")
        git(self.root, "config", "user.name", "Test User")
        write(self.root / "README.md", "initial\n")
        git(self.root, "add", "README.md")
        git(self.root, "commit", "-m", "初始化")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_cli(self, *args: str, cwd: Path | None = None) -> int:
        return wt.main(["--cwd", str(cwd or self.root), *args])

    def run_cli_capture(self, *args: str, cwd: Path | None = None) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = self.run_cli(*args, cwd=cwd)
        return code, output.getvalue()

    def load_state(self) -> dict:
        project = wt.discover_project(self.root)
        state_path = wt.state_paths(project["commonDir"])["state"]
        return json.loads(state_path.read_text(encoding="utf-8"))

    def test_parse_worktree_porcelain(self) -> None:
        parsed = wt.parse_worktree_porcelain(
            "worktree C:/repo\n"
            "HEAD abc123\n"
            "branch refs/heads/main\n"
            "\n"
            "worktree C:/repo-task\n"
            "HEAD def456\n"
            "branch refs/heads/task/demo\n"
            "locked maintenance\n"
            "prunable stale\n"
        )
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["branch"], "main")
        self.assertEqual(parsed[1]["branch"], "task/demo")
        self.assertTrue(parsed[1]["locked"])
        self.assertTrue(parsed[1]["prunable"])

    def test_scan_uses_shared_common_dir_and_preserves_notes(self) -> None:
        linked = Path(self.tmp.name) / "manual"
        git(self.root, "worktree", "add", "-b", "task/manual", str(linked), "main")

        self.assertEqual(self.run_cli("scan", cwd=self.root), 0)
        state = self.load_state()
        project_id = state["project"]["projectId"]
        manual = next(t for t in state["tasks"] if t["branch"] == "task/manual")

        self.assertEqual(
            self.run_cli("update", "--task-id", manual["taskId"], "--note", "正在处理扫描", cwd=linked),
            0,
        )
        self.assertEqual(self.run_cli("scan", cwd=linked), 0)
        state = self.load_state()
        self.assertEqual(state["project"]["projectId"], project_id)
        manual = next(t for t in state["tasks"] if t["branch"] == "task/manual")
        self.assertEqual(manual["activeUpdate"], "正在处理扫描")
        self.assertGreaterEqual(len(state["tasks"]), 2)

    def test_start_update_commit_and_ready_flow(self) -> None:
        self.assertEqual(self.run_cli("start", "--title", "修复登录状态", "--task-id", "t001"), 0)
        state = self.load_state()
        task = next(t for t in state["tasks"] if t["taskId"] == "t001")
        worktree = Path(task["worktreePath"])
        self.assertTrue(worktree.exists())
        self.assertEqual(task["branch"], "task/t001-task")

        self.assertEqual(
            self.run_cli("update", "--task-id", "t001", "--status", "进行中", "--note", "正在修改入口扫描"),
            0,
        )
        write(worktree / "feature.txt", "hello\n")
        self.assertEqual(self.run_cli("commit", "--task-id", "t001", "--message", "实现入口扫描"), 0)
        log = git(worktree, "log", "-1", "--pretty=%B").stdout
        self.assertIn("实现入口扫描", log)
        events = wt.read_events(wt.discover_project(self.root))
        commit_event = next(e for e in reversed(events) if e.get("type") == "commit" and e.get("taskId") == "t001")
        self.assertIn("A\tfeature.txt", commit_event["stagedFiles"])

        self.assertEqual(self.run_cli("ready", "--task-id", "t001", "--tests", "passed"), 0)
        state = self.load_state()
        task = next(t for t in state["tasks"] if t["taskId"] == "t001")
        self.assertEqual(task["tests"]["status"], "passed")
        self.assertEqual(task["status"], "已测试待合并批准")

    def test_dashboard_api_is_read_only_status_surface(self) -> None:
        self.assertEqual(self.run_cli("start", "--title", "检查仪表盘", "--task-id", "dash1"), 0)
        asset_dir = SCRIPT.parents[1] / "assets" / "dashboard"
        server = wt.ThreadingHTTPServer(("127.0.0.1", 0), wt.dashboard_handler(self.root, asset_dir))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/api/status"
            with urllib.request.urlopen(url, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertIn("project", payload)
            self.assertTrue(any(t["taskId"] == "dash1" for t in payload["tasks"]))
            html = (asset_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn("最新提交", html)
            self.assertIn("提交记录", html)
            self.assertIn("合并状态", html)
            self.assertIn("测试状态", html)
            self.assertIn("清理", html)
            app = (asset_dir / "app.js").read_text(encoding="utf-8")
            self.assertIn("基线工作区", app)
            self.assertIn("等待批准", app)
            self.assertIn("服务返回了 HTML", app)
            self.assertIn("Asia/Shanghai", app)
            self.assertIn("chinaTime(state.lastScanAt)", app)
            self.assertIn("chinaTime(task.updatedAt)", app)
            missing_url = f"http://127.0.0.1:{server.server_address[1]}/api/not-found"
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(missing_url, timeout=5)
            self.assertEqual(raised.exception.code, 404)
            error_payload = json.loads(raised.exception.read().decode("utf-8"))
            self.assertIn("Unknown API endpoint", error_payload["error"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_dashboard_status_serves_stale_payload_when_scan_lock_times_out(self) -> None:
        self.assertEqual(self.run_cli("start", "--title", "锁超时回退", "--task-id", "dashlock1"), 0)
        asset_dir = SCRIPT.parents[1] / "assets" / "dashboard"
        server = wt.ThreadingHTTPServer(("127.0.0.1", 0), wt.dashboard_handler(self.root, asset_dir))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        original_state_lock = wt.state_lock
        original_cache_seconds = wt.DASHBOARD_STATUS_CACHE_SECONDS
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/api/status"
            with urllib.request.urlopen(url, timeout=5) as response:
                warm_payload = json.loads(response.read().decode("utf-8"))
            self.assertFalse(warm_payload["dashboard"]["stale"])

            @contextlib.contextmanager
            def lock_timeout(*_args, **_kwargs):
                raise wt.WorktreeError("Timed out waiting for state lock: test")
                yield

            wt.state_lock = lock_timeout
            wt.DASHBOARD_STATUS_CACHE_SECONDS = -1
            with urllib.request.urlopen(url, timeout=15) as response:
                stale_payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(stale_payload["dashboard"]["stale"], True)
            self.assertIn("Timed out waiting for state lock", stale_payload["dashboard"]["warning"])
            self.assertTrue(any(t["taskId"] == "dashlock1" for t in stale_payload["tasks"]))
        finally:
            wt.state_lock = original_state_lock
            wt.DASHBOARD_STATUS_CACHE_SECONDS = original_cache_seconds
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_commits_command_and_api_show_task_history(self) -> None:
        self.assertEqual(self.run_cli("start", "--title", "查看提交记录", "--task-id", "hist1"), 0)
        task = next(t for t in self.load_state()["tasks"] if t["taskId"] == "hist1")
        worktree = Path(task["worktreePath"])
        write(worktree / "history-a.txt", "one\n")
        self.assertEqual(self.run_cli("commit", "--task-id", "hist1", "--message", "实现提交记录一"), 0)
        write(worktree / "history-b.txt", "two\n")
        self.assertEqual(self.run_cli("commit", "--task-id", "hist1", "--message", "实现提交记录二"), 0)

        code, output = self.run_cli_capture("commits", "--task-id", "hist1", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual(payload["taskId"], "hist1")
        self.assertEqual(payload["range"], "main..task/hist1-task")
        self.assertEqual([commit["subject"] for commit in payload["commits"]], ["实现提交记录二", "实现提交记录一"])
        self.assertTrue(any(event.get("type") == "commit" for event in payload["events"]))

        asset_dir = SCRIPT.parents[1] / "assets" / "dashboard"
        server = wt.ThreadingHTTPServer(("127.0.0.1", 0), wt.dashboard_handler(self.root, asset_dir))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/api/commits?taskId=hist1&limit=1"
            with urllib.request.urlopen(url, timeout=5) as response:
                api_payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(api_payload["taskId"], "hist1")
            self.assertEqual(len(api_payload["commits"]), 1)
            self.assertEqual(api_payload["commits"][0]["subject"], "实现提交记录二")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_dashboard_commits_api_uses_snapshot_without_rescanning(self) -> None:
        self.assertEqual(self.run_cli("start", "--title", "提交记录快照", "--task-id", "histsnap1"), 0)
        task = next(t for t in self.load_state()["tasks"] if t["taskId"] == "histsnap1")
        worktree = Path(task["worktreePath"])
        write(worktree / "snapshot-history.txt", "history\n")
        self.assertEqual(self.run_cli("commit", "--task-id", "histsnap1", "--message", "实现快照提交记录"), 0)

        asset_dir = SCRIPT.parents[1] / "assets" / "dashboard"
        server = wt.ThreadingHTTPServer(("127.0.0.1", 0), wt.dashboard_handler(self.root, asset_dir))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        original_scan_project = wt.scan_project
        try:
            def fail_scan(*_args, **_kwargs):
                raise wt.WorktreeError("scan should not run for dashboard commits")

            wt.scan_project = fail_scan
            url = f"http://127.0.0.1:{server.server_address[1]}/api/commits?taskId=histsnap1&limit=20"
            with urllib.request.urlopen(url, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["taskId"], "histsnap1")
            self.assertEqual([commit["subject"] for commit in payload["commits"]], ["实现快照提交记录"])
        finally:
            wt.scan_project = original_scan_project
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_commits_remain_visible_after_merge_and_worktree_deletion(self) -> None:
        self.assertEqual(self.run_cli("start", "--title", "保留提交记录", "--task-id", "histdel1"), 0)
        task = next(t for t in self.load_state()["tasks"] if t["taskId"] == "histdel1")
        worktree = Path(task["worktreePath"])
        write(worktree / "history-delete.txt", "history\n")
        self.assertEqual(self.run_cli("commit", "--task-id", "histdel1", "--message", "实现删除后查看记录"), 0)
        self.assertEqual(self.run_cli("ready", "--task-id", "histdel1", "--tests", "passed"), 0)
        self.assertEqual(self.run_cli("merge", "--task-id", "histdel1", "--approved"), 0)
        self.assertEqual(self.run_cli("delete-worktree", "--task-id", "histdel1", "--approved"), 0)
        self.assertFalse(worktree.exists())

        code, output = self.run_cli_capture("commits", "--task-id", "histdel1", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual(payload["rangeKind"], "merged_preflight")
        self.assertEqual([commit["subject"] for commit in payload["commits"]], ["实现删除后查看记录"])
        self.assertTrue(payload["merge"]["mergeCommit"])

    def test_merge_summary_variants_are_api_verifiable(self) -> None:
        base = {
            "status": "进行中",
            "git": {"dirty": False, "ahead": 1, "behind": 0},
            "tests": {"status": "unknown"},
            "merge": {"ready": False, "blockedReason": None},
        }
        self.assertEqual(wt.derive_merge_summary({**base, "status": "已落后主分支需同步"}), "blocked: behind base")
        dirty = json.loads(json.dumps(base))
        dirty["git"]["dirty"] = True
        self.assertEqual(wt.derive_merge_summary(dirty), "blocked: dirty")
        self.assertEqual(wt.derive_merge_summary(base), "blocked: tests not passed")
        ready = json.loads(json.dumps(base))
        ready["status"] = "已测试待合并批准"
        ready["tests"]["status"] = "passed"
        ready["merge"]["ready"] = True
        self.assertEqual(wt.derive_merge_summary(ready), "ready")
        blocked = json.loads(json.dumps(base))
        blocked["merge"]["blockedReason"] = "behind_base"
        self.assertEqual(wt.derive_merge_summary(blocked), "blocked: behind_base")

    def test_diverged_branch_is_not_merge_ready(self) -> None:
        self.assertEqual(self.run_cli("start", "--title", "分叉任务", "--task-id", "div1"), 0)
        task = next(t for t in self.load_state()["tasks"] if t["taskId"] == "div1")
        worktree = Path(task["worktreePath"])
        write(worktree / "diverged.txt", "task\n")
        self.assertEqual(self.run_cli("commit", "--task-id", "div1", "--message", "实现分叉任务"), 0)
        write(self.root / "main-change.txt", "main\n")
        git(self.root, "add", "main-change.txt")
        git(self.root, "commit", "-m", "更新主分支")

        self.assertEqual(self.run_cli("ready", "--task-id", "div1", "--tests", "passed"), 0)
        task = next(t for t in self.load_state()["tasks"] if t["taskId"] == "div1")
        self.assertEqual(task["git"]["ahead"], 1)
        self.assertEqual(task["git"]["behind"], 1)
        self.assertEqual(task["status"], "已落后主分支需同步")
        self.assertFalse(task["merge"]["ready"])
        self.assertEqual(task["merge"]["summary"], "blocked: behind base")
        self.assertEqual(self.run_cli("merge", "--task-id", "div1", "--approved"), 2)
        task = next(t for t in self.load_state()["tasks"] if t["taskId"] == "div1")
        self.assertEqual(task["merge"]["blockedReason"], "behind_base")
        self.assertEqual(task["merge"]["summary"], "blocked: behind_base")
        self.assertFalse((self.root / "diverged.txt").exists())

    def test_merge_requires_approval_and_merges_clean_task(self) -> None:
        self.assertEqual(self.run_cli("start", "--title", "合并功能", "--task-id", "merge1"), 0)
        task = next(t for t in self.load_state()["tasks"] if t["taskId"] == "merge1")
        worktree = Path(task["worktreePath"])
        write(worktree / "merge.txt", "merged\n")
        self.assertEqual(self.run_cli("commit", "--task-id", "merge1", "--message", "实现合并功能"), 0)
        self.assertEqual(self.run_cli("ready", "--task-id", "merge1", "--tests", "passed"), 0)

        self.assertEqual(self.run_cli("merge", "--task-id", "merge1"), 2)
        self.assertEqual(self.run_cli("merge", "--task-id", "merge1", "--approved"), 0)
        self.assertEqual((self.root / "merge.txt").read_text(encoding="utf-8"), "merged\n")
        self.assertTrue(worktree.exists())
        task = next(t for t in self.load_state()["tasks"] if t["taskId"] == "merge1")
        self.assertEqual(task["status"], "已合并")

    def test_delete_worktree_requires_approval_and_merged_task(self) -> None:
        self.assertEqual(self.run_cli("start", "--title", "删除工作树", "--task-id", "delete1"), 0)
        task = next(t for t in self.load_state()["tasks"] if t["taskId"] == "delete1")
        worktree = Path(task["worktreePath"])

        self.assertEqual(self.run_cli("delete-worktree", "--task-id", "delete1", "--approved"), 2)
        self.assertTrue(worktree.exists())

        write(worktree / "delete.txt", "delete\n")
        self.assertEqual(self.run_cli("commit", "--task-id", "delete1", "--message", "实现删除工作树"), 0)
        self.assertEqual(self.run_cli("ready", "--task-id", "delete1", "--tests", "passed"), 0)
        self.assertEqual(self.run_cli("merge", "--task-id", "delete1", "--approved"), 0)
        self.assertTrue(worktree.exists())

        self.assertEqual(self.run_cli("delete-worktree", "--task-id", "delete1"), 2)
        self.assertTrue(worktree.exists())
        self.assertEqual(self.run_cli("delete-worktree", "--task-id", "delete1", "--approved"), 0)
        self.assertFalse(worktree.exists())
        task = next(t for t in self.load_state()["tasks"] if t["taskId"] == "delete1")
        self.assertEqual(task["status"], "已合并")
        self.assertTrue(task["cleanup"]["worktreeRemoved"])
        self.assertFalse(task["git"]["exists"])
        self.assertEqual(git(self.root, "show-ref", "--verify", "--quiet", "refs/heads/task/delete1-task", check=False).returncode, 0)
        events = wt.read_events(wt.discover_project(self.root))
        self.assertTrue(any(e.get("type") == "delete_worktree" and e.get("taskId") == "delete1" for e in events))

    def test_delete_worktree_refuses_dirty_after_merge(self) -> None:
        self.assertEqual(self.run_cli("start", "--title", "拒绝脏删除", "--task-id", "deldirty1"), 0)
        task = next(t for t in self.load_state()["tasks"] if t["taskId"] == "deldirty1")
        worktree = Path(task["worktreePath"])
        write(worktree / "clean.txt", "clean\n")
        self.assertEqual(self.run_cli("commit", "--task-id", "deldirty1", "--message", "实现脏删除测试"), 0)
        self.assertEqual(self.run_cli("ready", "--task-id", "deldirty1", "--tests", "passed"), 0)
        self.assertEqual(self.run_cli("merge", "--task-id", "deldirty1", "--approved"), 0)
        write(worktree / "after-merge.txt", "not committed\n")

        self.assertEqual(self.run_cli("delete-worktree", "--task-id", "deldirty1", "--approved"), 2)
        self.assertTrue(worktree.exists())
        task = next(t for t in self.load_state()["tasks"] if t["taskId"] == "deldirty1")
        self.assertFalse(task.get("cleanup", {}).get("worktreeRemoved", False))

    def test_merge_refuses_dirty_source(self) -> None:
        self.assertEqual(self.run_cli("start", "--title", "脏源分支", "--task-id", "dirty1"), 0)
        task = next(t for t in self.load_state()["tasks"] if t["taskId"] == "dirty1")
        write(Path(task["worktreePath"]) / "dirty.txt", "not committed\n")

        self.assertEqual(self.run_cli("merge", "--task-id", "dirty1", "--approved"), 2)
        task = next(t for t in self.load_state()["tasks"] if t["taskId"] == "dirty1")
        self.assertEqual(task["merge"]["blockedReason"], "dirty_source")

    def test_commit_refuses_tampered_worktree_path(self) -> None:
        self.assertEqual(self.run_cli("start", "--title", "路径校验", "--task-id", "path1"), 0)
        other = Path(self.tmp.name) / "other"
        other.mkdir()
        git(other, "init", "-b", "main")
        git(other, "config", "user.email", "test@example.com")
        git(other, "config", "user.name", "Test User")
        write(other / "other.txt", "other\n")
        git(other, "add", "other.txt")
        git(other, "commit", "-m", "初始化")
        write(other / "other.txt", "changed\n")

        project = wt.discover_project(self.root)
        state_path = wt.state_paths(project["commonDir"])["state"]
        state = self.load_state()
        task = next(t for t in state["tasks"] if t["taskId"] == "path1")
        task["worktreePath"] = str(other)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

        self.assertEqual(self.run_cli("commit", "--task-id", "path1", "--message", "拒绝错误路径"), 2)
        self.assertEqual(git(other, "status", "--porcelain").stdout.strip(), "M other.txt")

    def test_scan_marks_existing_unlisted_record_orphaned(self) -> None:
        self.assertEqual(self.run_cli("scan"), 0)
        project = wt.discover_project(self.root)
        state_path = wt.state_paths(project["commonDir"])["state"]
        fake_dir = Path(self.tmp.name) / "orphaned-worktree"
        fake_dir.mkdir()
        state = self.load_state()
        state["tasks"].append(
            {
                "projectId": project["projectId"],
                "taskId": "orphan1",
                "title": "孤立任务",
                "worktreePath": str(fake_dir),
                "branch": "task/orphan1",
                "baseBranch": "main",
                "owner": None,
                "status": "进行中",
                "activeUpdate": "保留备注",
                "git": {},
                "tests": {"status": "unknown", "lastRun": None},
                "merge": {"ready": False, "approved": False, "blockedReason": None},
                "createdAt": "2026-04-28T00:00:00Z",
                "updatedAt": "2026-04-28T00:00:00Z",
            }
        )
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

        self.assertEqual(self.run_cli("scan"), 0)
        task = next(t for t in self.load_state()["tasks"] if t["taskId"] == "orphan1")
        self.assertEqual(task["status"], "orphaned")
        self.assertEqual(task["activeUpdate"], "保留备注")

    def test_merge_tree_unsupported_falls_back_to_real_merge(self) -> None:
        self.assertEqual(self.run_cli("start", "--title", "回退合并", "--task-id", "fallback1"), 0)
        task = next(t for t in self.load_state()["tasks"] if t["taskId"] == "fallback1")
        worktree = Path(task["worktreePath"])
        write(worktree / "fallback.txt", "fallback\n")
        self.assertEqual(self.run_cli("commit", "--task-id", "fallback1", "--message", "实现回退合并"), 0)
        self.assertEqual(self.run_cli("ready", "--task-id", "fallback1", "--tests", "passed"), 0)

        original_run_git = wt.run_git

        def fake_run_git(args, cwd, check=True):
            if args[:2] == ["merge-tree", "--write-tree"]:
                return subprocess.CompletedProcess(["git", *args], 129, "", "usage: git merge-tree")
            return original_run_git(args, cwd, check)

        wt.run_git = fake_run_git
        try:
            self.assertEqual(self.run_cli("merge", "--task-id", "fallback1", "--approved"), 0)
        finally:
            wt.run_git = original_run_git
        self.assertEqual((self.root / "fallback.txt").read_text(encoding="utf-8"), "fallback\n")

    def test_diverged_conflict_scenario_is_blocked_as_behind_base(self) -> None:
        write(self.root / "conflict.txt", "base\n")
        git(self.root, "add", "conflict.txt")
        git(self.root, "commit", "-m", "添加冲突文件")

        self.assertEqual(self.run_cli("start", "--title", "冲突任务", "--task-id", "conf1"), 0)
        task = next(t for t in self.load_state()["tasks"] if t["taskId"] == "conf1")
        worktree = Path(task["worktreePath"])
        write(worktree / "conflict.txt", "task\n")
        self.assertEqual(self.run_cli("commit", "--task-id", "conf1", "--message", "修改冲突任务"), 0)
        write(self.root / "conflict.txt", "main\n")
        git(self.root, "add", "conflict.txt")
        git(self.root, "commit", "-m", "修改主分支")

        self.assertEqual(self.run_cli("merge", "--task-id", "conf1", "--approved"), 2)
        task = next(t for t in self.load_state()["tasks"] if t["taskId"] == "conf1")
        self.assertEqual(task["merge"]["blockedReason"], "behind_base")
        self.assertEqual(task["status"], "已落后主分支需同步")
        self.assertEqual((self.root / "conflict.txt").read_text(encoding="utf-8"), "main\n")

    def test_merge_tree_conflict_stops_without_resolution(self) -> None:
        self.assertEqual(self.run_cli("start", "--title", "预检冲突", "--task-id", "treeconf1"), 0)
        task = next(t for t in self.load_state()["tasks"] if t["taskId"] == "treeconf1")
        worktree = Path(task["worktreePath"])
        write(worktree / "tree-conflict.txt", "task\n")
        self.assertEqual(self.run_cli("commit", "--task-id", "treeconf1", "--message", "实现预检冲突"), 0)
        self.assertEqual(self.run_cli("ready", "--task-id", "treeconf1", "--tests", "passed"), 0)

        original_run_git = wt.run_git

        def fake_run_git(args, cwd, check=True):
            if args[:2] == ["merge-tree", "--write-tree"]:
                return subprocess.CompletedProcess(["git", *args], 1, "simulated conflict", "")
            return original_run_git(args, cwd, check)

        wt.run_git = fake_run_git
        try:
            self.assertEqual(self.run_cli("merge", "--task-id", "treeconf1", "--approved"), 2)
        finally:
            wt.run_git = original_run_git
        task = next(t for t in self.load_state()["tasks"] if t["taskId"] == "treeconf1")
        self.assertEqual(task["status"], "合并有冲突需人工处理")
        self.assertFalse((self.root / "tree-conflict.txt").exists())


if __name__ == "__main__":
    unittest.main()
