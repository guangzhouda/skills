const $ = (id) => document.getElementById(id);

function text(value) {
  return value === undefined || value === null || value === "" ? "-" : String(value);
}

const CHINA_TIME_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  hour12: false,
  hourCycle: "h23",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

function chinaTime(value) {
  const rendered = text(value);
  if (rendered === "-") return rendered;
  const date = new Date(rendered);
  if (Number.isNaN(date.getTime())) return rendered;
  const parts = Object.fromEntries(CHINA_TIME_FORMATTER.formatToParts(date).map((part) => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second} CST`;
}

let selectedTaskId = null;
let lastTimelineFetchAt = 0;
const TIMELINE_REFRESH_MS = 10000;

async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  const contentType = response.headers.get("content-type") || "";
  const raw = await response.text();
  if (!contentType.includes("application/json")) {
    const startsLikeHtml = raw.trimStart().startsWith("<!DOCTYPE") || raw.trimStart().startsWith("<html");
    if (startsLikeHtml) {
      throw new Error("服务返回了 HTML，请重启 dashboard 服务后刷新页面。");
    }
    throw new Error(`接口返回非 JSON 内容：${response.status}`);
  }
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch (error) {
    throw new Error(`JSON 解析失败：${error.message}`);
  }
  if (!response.ok) {
    throw new Error(payload.error || `接口请求失败：${response.status}`);
  }
  return payload;
}

const STATUS_LABELS = {
  missing: "工作树缺失",
  orphaned: "孤立记录",
};

const TEST_STATUS_LABELS = {
  passed: "通过",
  failed: "失败",
  unknown: "未知",
};

const BLOCKED_REASON_LABELS = {
  behind_base: "落后主分支",
  dirty_base: "主分支工作区有未提交修改",
  dirty_source: "任务工作区有未提交修改",
  missing_base_worktree: "缺少主分支工作区",
  missing_source_branch: "缺少任务分支",
  tests_not_passed: "测试未通过",
  not_merge_ready: "任务未标记为可合并",
  nothing_to_merge: "没有可合并提交",
  conflict: "合并冲突",
  "behind base": "落后主分支",
  dirty: "有未提交修改",
  "tests not passed": "测试未通过",
};

const EVENT_TYPE_LABELS = {
  scan: "扫描",
  start: "开始任务",
  update: "更新",
  commit: "提交",
  ready: "就绪",
  merge: "合并",
  merge_blocked: "合并阻塞",
  delete_worktree: "删除工作树",
};

const NODE_PROVENANCE_LABELS = {
  recorded: "已记录",
  derived: "推断",
  missing: "未记录",
};

const NODE_STATUS_LABELS = {
  complete: "完成",
  missing: "未记录",
  retained: "保留",
  warning: "需注意",
};

function classify(status) {
  if (status === "已测试待合并批准") return "ready";
  if (status === "有未提交修改") return "dirty";
  if (status === "合并有冲突需人工处理" || status === "missing" || status === "orphaned" || status === "已落后主分支需同步") return "blocked";
  if (status === "已合并") return "merged";
  if (status === "基线工作区") return "base";
  return "active";
}

function displayStatus(status) {
  const rendered = text(status);
  return STATUS_LABELS[rendered] || rendered;
}

function displayTestStatus(status) {
  const rendered = text(status);
  return TEST_STATUS_LABELS[rendered] || rendered;
}

function blockedReasonLabel(reason) {
  const rendered = text(reason);
  return BLOCKED_REASON_LABELS[rendered] || rendered;
}

function displayMergeSummary(summary) {
  const rendered = text(summary);
  if (rendered === "-") return rendered;
  if (rendered === "ready") return "可合并";
  if (rendered === "awaiting approval") return "等待批准";
  if (rendered === "merged") return "已合并";
  if (rendered.startsWith("merged: ")) return `已合并：${rendered.slice("merged: ".length)}`;
  if (rendered.startsWith("blocked: ")) return `阻塞：${blockedReasonLabel(rendered.slice("blocked: ".length))}`;
  return rendered;
}

function displayEventType(type) {
  const rendered = text(type);
  return EVENT_TYPE_LABELS[rendered] || rendered;
}

function displayNodeProvenance(provenance) {
  const rendered = text(provenance);
  return NODE_PROVENANCE_LABELS[rendered] || rendered;
}

function displayNodeStatus(status) {
  const rendered = text(status);
  return NODE_STATUS_LABELS[rendered] || rendered;
}

function displayTaskTitle(title) {
  const rendered = text(title);
  if (rendered === "Base worktree") return "基线工作区";
  if (rendered.startsWith("Worktree ")) return `工作树 ${rendered.slice("Worktree ".length)}`;
  return rendered;
}

function eventDetail(event) {
  const parts = [];
  if (event.taskId) parts.push(event.taskId);
  if (event.reason) parts.push(blockedReasonLabel(event.reason));
  return parts.join(" ");
}

function clear(element) {
  while (element.firstChild) element.removeChild(element.firstChild);
}

function td(value, className) {
  const cell = document.createElement("td");
  if (className) cell.className = className;
  cell.textContent = text(value);
  return cell;
}

function codeCell(value) {
  const cell = document.createElement("td");
  const code = document.createElement("code");
  code.textContent = text(value);
  cell.appendChild(code);
  return cell;
}

function actionCell(task) {
  const cell = document.createElement("td");
  const button = document.createElement("button");
  button.type = "button";
  button.className = "compact-button";
  button.textContent = "查看";
  button.disabled = !task.taskId;
  button.addEventListener("click", () => {
    selectedTaskId = task.taskId;
    loadCommits(task.taskId);
  });
  cell.appendChild(button);
  return cell;
}

function taskCell(task) {
  const cell = document.createElement("td");
  const title = document.createElement("strong");
  title.textContent = displayTaskTitle(task.title);
  const id = document.createElement("small");
  id.textContent = text(task.taskId);
  cell.append(title, id);
  return cell;
}

function badgeCell(status) {
  const cell = document.createElement("td");
  const badge = document.createElement("span");
  badge.className = "badge";
  badge.textContent = text(status);
  cell.appendChild(badge);
  return cell;
}

function shortSha(value) {
  const rendered = text(value);
  return rendered === "-" ? rendered : rendered.slice(0, 10);
}

function mergeSummary(task) {
  const merge = task.merge || {};
  if (merge.summary) return displayMergeSummary(merge.summary);
  const git = task.git || {};
  if (merge.blockedReason) return displayMergeSummary(`blocked: ${merge.blockedReason}`);
  if (task.status === "已落后主分支需同步") return displayMergeSummary("blocked: behind base");
  if (git.dirty) return displayMergeSummary("blocked: dirty");
  if (task.tests && task.tests.status && task.tests.status !== "passed" && git.ahead > 0) return displayMergeSummary("blocked: tests not passed");
  if (task.status === "已合并") return displayMergeSummary(`merged: ${shortSha(merge.mergeCommit)}`);
  if (merge.ready) return displayMergeSummary("ready");
  if (task.status === "已测试待合并批准") return displayMergeSummary("awaiting approval");
  return "-";
}

function cleanupSummary(task) {
  const cleanup = task.cleanup || {};
  const git = task.git || {};
  if (task.status === "基线工作区") return "不可删除";
  if (task.status !== "已合并") return "保留";
  if (cleanup.worktreeRemoved || git.exists === false) return "已删除";
  return "可删除";
}

function renderState(state) {
  const project = state.project || {};
  const tasks = state.tasks || [];
  $("project-line").textContent = `${text(project.name)} | 基线：${text(project.baseBranch)} | 扫描：${chinaTime(state.lastScanAt)}`;

  const counts = {
    active: tasks.filter((t) => !["已合并", "基线工作区"].includes(t.status)).length,
    dirty: tasks.filter((t) => t.git && t.git.dirty).length,
    ready: tasks.filter((t) => t.status === "已测试待合并批准").length,
    blocked: tasks.filter((t) => ["合并有冲突需人工处理", "missing", "orphaned", "已落后主分支需同步"].includes(t.status)).length,
  };
  $("count-active").textContent = counts.active;
  $("count-dirty").textContent = counts.dirty;
  $("count-ready").textContent = counts.ready;
  $("count-blocked").textContent = counts.blocked;

  const body = $("task-body");
  clear(body);
  if (!tasks.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 13;
    cell.textContent = "未发现工作树。";
    row.appendChild(cell);
    body.appendChild(row);
    return;
  }

  for (const task of tasks) {
    const git = task.git || {};
    const tests = task.tests || {};
    const row = document.createElement("tr");
    row.className = classify(task.status);
    row.append(
      taskCell(task),
      badgeCell(displayStatus(task.status)),
      codeCell(task.branch),
      td(git.dirty ? "有修改" : "干净"),
      td(git.ahead),
      td(git.behind),
      td(displayTestStatus(tests.status)),
      codeCell(shortSha(git.latestCommit)),
      actionCell(task),
      td(mergeSummary(task)),
      td(cleanupSummary(task)),
      td(chinaTime(task.updatedAt)),
      codeCell(task.worktreePath),
    );
    body.appendChild(row);
  }
}

function renderCommits(payload) {
  $("commit-task-line").textContent = `${text(payload.title)} | ${text(payload.branch)} | ${text(payload.range)}`;
  const panel = $("commit-panel");
  clear(panel);

  const commits = payload.commits || [];
  if (payload.merge && payload.merge.mergeCommit) {
    const merge = document.createElement("p");
    merge.className = "commit-meta";
    merge.textContent = `合并提交：${shortSha(payload.merge.mergeCommit)} ${chinaTime(payload.merge.mergedAt)}`;
    panel.appendChild(merge);
  }

  if (!commits.length) {
    const empty = document.createElement("p");
    empty.className = "commit-empty";
    empty.textContent = "没有相对任务范围的提交。";
    panel.appendChild(empty);
  } else {
    const list = document.createElement("ol");
    list.className = "commit-list";
    for (const commit of commits) {
      const item = document.createElement("li");
      const head = document.createElement("div");
      const sha = document.createElement("code");
      const subject = document.createElement("strong");
      const meta = document.createElement("small");
      sha.textContent = shortSha(commit.sha || commit.shortSha);
      subject.textContent = text(commit.subject);
      meta.textContent = `${chinaTime(commit.date)} ${text(commit.author)}`;
      head.append(sha, subject);
      item.append(head, meta);
      list.appendChild(item);
    }
    panel.appendChild(list);
  }

  const events = payload.events || [];
  if (events.length) {
    const title = document.createElement("h3");
    title.textContent = "任务事件";
    const list = document.createElement("ul");
    list.className = "commit-events";
    for (const event of events.slice(-8).reverse()) {
      const item = document.createElement("li");
      item.textContent = `${chinaTime(event.time)} ${displayEventType(event.type)} ${text(eventDetail(event) || event.message || event.tests || "")}`;
      list.appendChild(item);
    }
    panel.append(title, list);
  }
}

async function loadCommits(taskId, silent = false) {
  if (!taskId) return;
  try {
    if (!silent) {
      $("commit-task-line").textContent = taskId;
      $("commit-panel").textContent = "正在加载...";
    }
    const payload = await fetchJson(`/api/commits?taskId=${encodeURIComponent(taskId)}&limit=20`);
    if (payload.error) throw new Error(payload.error);
    renderCommits(payload);
  } catch (error) {
    $("commit-task-line").textContent = taskId;
    $("commit-panel").textContent = error.message || "提交记录加载失败";
  }
}

function renderEvents(events) {
  const list = $("event-list");
  clear(list);
  for (const event of (events || []).slice(-12).reverse()) {
    const item = document.createElement("li");
    item.textContent = `${chinaTime(event.time)} ${displayEventType(event.type)} ${text(eventDetail(event))}`;
    list.appendChild(item);
  }
}

function renderTimeline(payload) {
  const panel = $("timeline-panel");
  const warning = $("timeline-warning");
  clear(panel);
  warning.textContent = "";
  $("timeline-state").textContent = `更新时间：${chinaTime(payload.generatedAt)}`;

  const warnings = payload.warnings || [];
  const warningParts = [];
  if (payload.eventWindowMayBeTruncated) {
    warningParts.push(`事件窗口可能已截断：仅加载最近 ${text(payload.eventLimit)} 条事件，未记录节点也可能是超出加载窗口。`);
  }
  if (warnings.length) {
    warningParts.push(`有 ${warnings.length} 个任务存在时间轴解析警告。`);
  }
  warning.textContent = warningParts.join(" ");

  const tasks = payload.tasks || [];
  if (!tasks.length) {
    panel.textContent = "暂无已合并任务历史。";
    return;
  }

  for (const task of tasks) {
    const card = document.createElement("article");
    card.className = "timeline-card";

    const header = document.createElement("div");
    header.className = "timeline-card-head";
    const title = document.createElement("strong");
    title.textContent = displayTaskTitle(task.title || task.taskId);
    const meta = document.createElement("small");
    meta.textContent = `${text(task.branch)} | ${text(task.taskId)} | 排序：${chinaTime(task.sortTime)} (${text(task.sortBasis)})`;
    header.append(title, meta);

    const nodes = document.createElement("ol");
    nodes.className = "timeline-nodes";
    for (const node of task.nodes || []) {
      const item = document.createElement("li");
      item.className = `timeline-node ${text(node.status)} ${text(node.provenance)}`;
      const label = document.createElement("strong");
      label.textContent = text(node.label);
      const nodeMeta = document.createElement("small");
      nodeMeta.textContent = `${chinaTime(node.time)} | ${displayNodeStatus(node.status)} | ${displayNodeProvenance(node.provenance)}`;
      const summary = document.createElement("span");
      summary.textContent = text(node.summary || (node.status === "missing" ? "未记录" : ""));
      item.append(label, nodeMeta, summary);
      nodes.appendChild(item);
    }

    if ((task.warnings || []).length) {
      const taskWarnings = document.createElement("small");
      taskWarnings.className = "timeline-task-warning";
      taskWarnings.textContent = task.warnings.join("；");
      card.append(header, nodes, taskWarnings);
    } else {
      card.append(header, nodes);
    }
    panel.appendChild(card);
  }
}

async function maybeRefreshTimeline(force = false) {
  const now = Date.now();
  if (!force && now - lastTimelineFetchAt < TIMELINE_REFRESH_MS) return;
  lastTimelineFetchAt = now;
  try {
    $("timeline-state").textContent = "刷新中";
    const payload = await fetchJson("/api/timeline");
    renderTimeline(payload);
  } catch (error) {
    $("timeline-state").textContent = "错误";
    $("timeline-warning").textContent = "";
    $("timeline-panel").textContent = error.message || "时间轴加载失败";
  }
}

async function refresh() {
  try {
    $("refresh-state").textContent = "刷新中";
    const [status, events] = await Promise.all([
      fetchJson("/api/status"),
      fetchJson("/api/events"),
    ]);
    if (status.error) throw new Error(status.error);
    renderState(status);
    renderEvents(events);
    if (selectedTaskId) await loadCommits(selectedTaskId, true);
    await maybeRefreshTimeline();
    $("refresh-state").textContent = "实时";
  } catch (error) {
    $("refresh-state").textContent = "错误";
    const body = $("task-body");
    clear(body);
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 13;
    cell.textContent = error.message || "未知看板错误";
    row.appendChild(cell);
    body.appendChild(row);
  }
}

refresh();
maybeRefreshTimeline(true);
setInterval(refresh, 4000);
