const AUTO_REFRESH_INTERVALS = [15000, 30000, 60000, 300000];

const state = {
  snapshot: null,
  actions: null,
  results: {},
  loading: false,
  runningAction: null,
  autoRefreshEnabled: window.localStorage.getItem("asyncResearchAutoRefreshEnabled") === "true",
  autoRefreshIntervalMs: storedAutoRefreshInterval(),
  autoRefreshTimer: null,
  taskFilter: "all",
  selectedTaskId: null,
  outcomeFilter: "all",
  selectedProjectId: null,
  selectedPromptId: null,
  selectedScheduleId: null,
  pendingDecision: null,
};

const el = (id) => document.getElementById(id);

function storedAutoRefreshInterval() {
  const value = Number.parseInt(window.localStorage.getItem("asyncResearchAutoRefreshIntervalMs") || "", 10);
  return AUTO_REFRESH_INTERVALS.includes(value) ? value : 30000;
}

function intervalLabel(ms) {
  if (ms >= 60000) {
    return `${Math.round(ms / 60000)}m`;
  }
  return `${Math.round(ms / 1000)}s`;
}

function refreshTimeLabel(date) {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function setRefreshStatus(text) {
  const node = el("refresh-status");
  if (node) {
    node.textContent = text;
  }
}

function updateAutoRefreshControls() {
  const toggle = el("auto-refresh-toggle");
  const interval = el("auto-refresh-interval");
  if (!toggle || !interval) {
    return;
  }
  toggle.checked = state.autoRefreshEnabled;
  interval.value = String(state.autoRefreshIntervalMs);
  interval.disabled = !state.autoRefreshEnabled;
  if (state.autoRefreshEnabled && !state.snapshot) {
    setRefreshStatus(`Auto ${intervalLabel(state.autoRefreshIntervalMs)}`);
  } else if (!state.snapshot) {
    setRefreshStatus("Manual");
  }
}

function clearAutoRefreshTimer() {
  if (state.autoRefreshTimer !== null) {
    window.clearTimeout(state.autoRefreshTimer);
    state.autoRefreshTimer = null;
  }
}

function scheduleAutoRefresh() {
  clearAutoRefreshTimer();
  updateAutoRefreshControls();
  if (!state.autoRefreshEnabled) {
    return;
  }
  state.autoRefreshTimer = window.setTimeout(async () => {
    if (!state.runningAction) {
      await refresh({ source: "auto" });
    }
    scheduleAutoRefresh();
  }, state.autoRefreshIntervalMs);
}

function setAutoRefreshEnabled(enabled) {
  state.autoRefreshEnabled = enabled;
  window.localStorage.setItem("asyncResearchAutoRefreshEnabled", String(enabled));
  scheduleAutoRefresh();
}

function setAutoRefreshInterval(value) {
  const parsed = Number.parseInt(value, 10);
  state.autoRefreshIntervalMs = AUTO_REFRESH_INTERVALS.includes(parsed) ? parsed : 30000;
  window.localStorage.setItem("asyncResearchAutoRefreshIntervalMs", String(state.autoRefreshIntervalMs));
  scheduleAutoRefresh();
}

function valueOrUnavailable(value) {
  if (value === null || value === undefined || value === "") {
    return "unavailable";
  }
  return value;
}

function statusLabel(value) {
  return String(valueOrUnavailable(value)).replaceAll("_", " ");
}

function asNumber(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function money(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "unavailable";
  }
  return `$${value.toFixed(2)}`;
}

function percent(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "unavailable";
  }
  return `${Math.round(value * 100)}%`;
}

function badgeClass(readiness) {
  const exitCode = readiness && readiness.exit_code;
  if (exitCode === 0) {
    return "badge good";
  }
  if (exitCode === 2) {
    return "badge warn";
  }
  if (exitCode === undefined || exitCode === null) {
    return "badge neutral";
  }
  return "badge bad";
}

function setBadge(readiness) {
  const badge = el("readiness-badge");
  badge.className = badgeClass(readiness);
  badge.textContent = readiness && readiness.verdict ? readiness.verdict : "unavailable";
}

function resultBadgeClass(result) {
  if (!result) {
    return "badge neutral";
  }
  if (result.status === "success" || result.exit_code === 0) {
    return "badge good";
  }
  if (result.status === "warning") {
    return "badge warn";
  }
  return "badge bad";
}

function metric(label, value, note) {
  const card = document.createElement("article");
  card.className = "metric-card";
  card.innerHTML = `
    <div class="metric-label"></div>
    <div class="metric-value"></div>
    <div class="metric-note"></div>
  `;
  card.querySelector(".metric-label").textContent = label;
  card.querySelector(".metric-value").textContent = valueOrUnavailable(value);
  card.querySelector(".metric-note").textContent = note || "";
  return card;
}

function renderMetrics(snapshot) {
  const tasks = snapshot.tasks || {};
  const decisions = snapshot.human_decisions || {};
  const accepted = snapshot.accepted_outputs || {};
  const delivered = snapshot.delivered_projects || {};
  const deliverables = snapshot.deliverables || {};
  const deliverableSummary = deliverables.summary || {};
  const rejected = snapshot.rejected_results || {};
  const cost = snapshot.cost || {};
  const readiness = snapshot.readiness || {};
  const health = snapshot.health || {};
  const runtime = snapshot.runtime || {};
  const runtimeSummary = runtime.summary || {};
  const warnings = snapshot.warnings || [];
  const grid = el("dashboard");
  grid.replaceChildren(
    metric("Readiness", statusLabel(readiness.verdict || readiness.status), readiness.next_step),
    metric("Health", statusLabel(health.verdict || health.status), health.next_step),
    metric("Active tasks", (tasks.active || []).length, `${asNumber(tasks.total)} total tasks`),
    metric("Blocked tasks", (tasks.blocked || []).length, `${asNumber(decisions.open_count)} human decisions`),
    metric("Delivered projects", asNumber((delivered.summary || {}).project_count || accepted.count), `${asNumber((delivered.summary || {}).accepted_count)} accepted outputs`),
    metric("Deliverables", asNumber(deliverables.count), `${asNumber(deliverableSummary.target_ready_count)} ready / ${asNumber(deliverableSummary.blocked_count)} blocked`),
    metric("Rejected results", asNumber(rejected.count), "recent rejected ledger rows"),
    metric("Runtime evidence", asNumber(runtimeSummary.evidence_object_count), `${asNumber(runtimeSummary.runtime_trace_count)} traces / ${asNumber(runtimeSummary.unsupported_or_stale_evidence_count)} gaps`),
    metric("Cost this month", money(cost.month_spend_usd), `this week ${money(cost.week_spend_usd)}`),
    metric("Warnings", warnings.length, `${(tasks.stale_locks || []).length} stale locks`)
  );
}

function record(title, meta, extra) {
  const row = document.createElement("div");
  row.className = "record-row";
  const titleNode = document.createElement("div");
  titleNode.className = "record-title";
  titleNode.textContent = title;
  const metaNode = document.createElement("div");
  metaNode.className = "record-meta";
  metaNode.textContent = meta;
  row.append(titleNode, metaNode);
  if (extra) {
    const extraNode = document.createElement("div");
    extraNode.className = "record-meta";
    extraNode.textContent = extra;
    row.append(extraNode);
  }
  return row;
}

function actionLabel(action) {
  if (!action || typeof action !== "object") {
    return "";
  }
  return action.label || action.action || action.description || "";
}

function sourceActionSummary(source) {
  const actions = Array.isArray(source.available_actions) ? source.available_actions : [];
  const labels = actions.map(actionLabel).filter(Boolean).slice(0, 4);
  return labels.length > 0 ? `Actions: ${labels.join(" / ")}` : "";
}

function empty(label) {
  const node = document.createElement("div");
  node.className = "empty";
  node.textContent = label;
  return node;
}

function renderList(target, rows, emptyText, renderer) {
  const list = el(target);
  if (!rows || rows.length === 0) {
    list.replaceChildren(empty(emptyText));
    return;
  }
  list.replaceChildren(...rows.map(renderer));
}

function taskStatusClass(task) {
  if ((task.status_validation || {}).valid === false || task.status === "invalid") {
    return "badge bad";
  }
  if ((task.lock_state || {}).stale) {
    return "badge warn";
  }
  if (task.status === "accepted" || task.status === "synthesized") {
    return "badge good";
  }
  if (task.requires_human || task.status === "needs_human" || task.status === "paused") {
    return "badge warn";
  }
  return "badge neutral";
}

function renderTaskFilters(tasks, rows) {
  const filters = tasks.status_filter_options || ["all"];
  const counts = rows.reduce((acc, task) => {
    const status = task.status || "unknown";
    acc[status] = (acc[status] || 0) + 1;
    return acc;
  }, { all: rows.length });
  if (!filters.includes(state.taskFilter)) {
    state.taskFilter = "all";
  }
  const buttons = filters.map((filter) => {
    const button = document.createElement("button");
    button.className = filter === state.taskFilter ? "filter-chip active" : "filter-chip";
    button.type = "button";
    button.textContent = `${statusLabel(filter)} ${counts[filter] || 0}`;
    button.addEventListener("click", () => {
      state.taskFilter = filter;
      renderTasks(state.snapshot || {});
    });
    return button;
  });
  el("task-filters").replaceChildren(...buttons);
}

function filteredTasks(rows) {
  if (state.taskFilter === "all") {
    return rows;
  }
  return rows.filter((task) => task.status === state.taskFilter);
}

function taskBoardRow(task) {
  const row = document.createElement("button");
  row.className = task.task_id === state.selectedTaskId ? "task-row selected" : "task-row";
  row.type = "button";
  row.addEventListener("click", () => {
    state.selectedTaskId = task.task_id;
    renderTasks(state.snapshot || {});
  });

  const title = document.createElement("div");
  title.className = "task-row-title";
  title.textContent = `${valueOrUnavailable(task.task_id)} - ${valueOrUnavailable(task.title)}`;

  const meta = document.createElement("div");
  meta.className = "task-row-meta";
  meta.textContent = `${valueOrUnavailable(task.type)} / tier ${valueOrUnavailable(task.review_tier)} / rev ${valueOrUnavailable(task.revision_count)}`;

  const badge = document.createElement("span");
  badge.className = taskStatusClass(task);
  badge.textContent = statusLabel(task.status);

  row.append(title, badge, meta);
  return row;
}

function selectedTask(rows) {
  return rows.find((task) => task.task_id === state.selectedTaskId) || rows[0] || null;
}

function detailValue(value) {
  if (Array.isArray(value)) {
    return value.length > 0 ? value.join(", ") : valueOrUnavailable("");
  }
  return valueOrUnavailable(value);
}

function detailField(label, value) {
  const node = document.createElement("div");
  node.className = "detail-field";
  const heading = document.createElement("h3");
  heading.textContent = label;
  const body = document.createElement("div");
  body.className = "detail-value";
  body.textContent = detailValue(value);
  node.append(heading, body);
  return node;
}

function compactList(values, emptyText = "none recorded") {
  if (!Array.isArray(values) || values.length === 0) {
    return [emptyText];
  }
  return values.map((value) => {
    if (value && typeof value === "object") {
      return Object.entries(value)
        .filter(([, item]) => item !== null && item !== undefined && item !== "")
        .map(([key, item]) => `${key}: ${Array.isArray(item) ? item.join(", ") : item}`)
        .join(" / ");
    }
    return valueOrUnavailable(value);
  });
}

function detailListField(label, values, emptyText) {
  const node = document.createElement("div");
  node.className = "detail-field detail-list-field";
  const heading = document.createElement("h3");
  heading.textContent = label;
  const list = document.createElement("div");
  list.className = "insight-list";
  compactList(values, emptyText).forEach((value) => {
    const item = document.createElement("div");
    item.className = "insight-item";
    item.textContent = value;
    list.append(item);
  });
  node.append(heading, list);
  return node;
}

function taskInsightPanel(titleText, children) {
  const panel = document.createElement("section");
  panel.className = "task-insight-panel";
  const title = document.createElement("div");
  title.className = "task-insight-title";
  title.textContent = titleText;
  panel.append(title, ...children);
  return panel;
}

function confidenceText(summary) {
  if (!summary || !summary.count) {
    return "not recorded";
  }
  return `avg ${summary.average} / min ${summary.min} / ${summary.count} review${summary.count === 1 ? "" : "s"}`;
}

function sourceGateText(sourceGate) {
  if (!sourceGate) {
    return "not recorded";
  }
  const ids = compactList(sourceGate.source_ids, "no source ids").join(", ");
  return `${statusLabel(sourceGate.status)} / ${ids}`;
}

function scorecardText(scorecard) {
  if (!scorecard || Object.keys(scorecard).length === 0) {
    return ["none recorded"];
  }
  return Object.entries(scorecard).map(([key, value]) => `${key.replaceAll("_", " ")}: ${valueOrUnavailable(value)}`);
}

function reviewChainItems(chain) {
  if (!Array.isArray(chain) || chain.length === 0) {
    return ["no reviewer records"];
  }
  return chain.map((review) => {
    const confidence = review.confidence === null || review.confidence === undefined ? "confidence unavailable" : `confidence ${review.confidence}`;
    const gaps = compactList(review.evidence_gaps, "no gaps").join(", ");
    return `${valueOrUnavailable(review.role)}: ${valueOrUnavailable(review.decision)} / ${valueOrUnavailable(review.claim_strength)} / ${confidence} / ${gaps}`;
  });
}

function taskExplainabilityPanel(task) {
  const explanation = task.explainability || {};
  const fields = document.createElement("div");
  fields.className = "detail-grid";
  fields.replaceChildren(
    detailField("Why", explanation.rationale),
    detailField("Question", explanation.research_question),
    detailField("Trigger", explanation.trigger),
    detailField("Next", explanation.next_recommended_task),
    detailListField("Inputs", explanation.input_artifacts, "no inputs recorded"),
    detailListField("Outputs", explanation.output_artifacts, "no outputs recorded"),
    detailListField("Dependencies", explanation.dependencies, "no dependencies recorded"),
    detailListField("Unblocks", explanation.unblocks, "no downstream unblock recorded"),
    detailListField("Validation Commands", explanation.validation_commands, "no validation commands recorded")
  );
  const command = lifecycleCommandNode(explanation.next_command);
  return taskInsightPanel("Task Explanation", [fields, command]);
}

function taskQaPanel(task) {
  const qa = task.qa || {};
  const fields = document.createElement("div");
  fields.className = "detail-grid";
  fields.replaceChildren(
    detailField("Review Status", `${statusLabel(qa.review_status)} / ${valueOrUnavailable(qa.routing_reason)}`),
    detailField("Review Mode", compactList(qa.review_modes, "not recorded").join(", ")),
    detailField("Confidence", confidenceText(qa.reviewer_confidence)),
    detailField("Claim", `${valueOrUnavailable(qa.claim_strength)} / max ${valueOrUnavailable(qa.max_claim_strength)}`),
    detailField("Source Gate", sourceGateText(qa.source_gate)),
    detailField("Acceptance", `${valueOrUnavailable((qa.result_acceptance || {}).route)} / ${valueOrUnavailable((qa.result_acceptance || {}).recommended_decision)}`),
    detailListField("Caveats", qa.caveats, "no caveats recorded"),
    detailListField("Evidence Gaps", qa.evidence_gaps, "no evidence gaps recorded"),
    detailListField("Validation Checks", qa.validation_checks, "no validation checks recorded"),
    detailListField("Reproducibility", qa.reproducibility_checks, "no reproducibility checks recorded"),
    detailListField("Scorecard", scorecardText(qa.scorecard), "no scorecard recorded"),
    detailListField("Review Chain", reviewChainItems(qa.review_chain), "no reviewer records")
  );
  return taskInsightPanel("Review And QA", [fields]);
}

function artifactHref(file, mode = "view") {
  if (!file) {
    return "";
  }
  if (mode === "raw") {
    return String(file.raw_url || file.viewer_url || "").trim();
  }
  if (mode === "download") {
    return String(file.download_url || file.raw_url || file.viewer_url || "").trim();
  }
  return String(file.viewer_url || file.raw_url || "").trim();
}

function detailPathLink(file) {
  const path = file && file.path ? String(file.path) : "";
  const label = file && file.label ? file.label : "File";
  const displayPath = file && file.relative_path ? file.relative_path : valueOrUnavailable(path);
  const text = `${label}: ${displayPath}${file && file.exists ? "" : " (missing)"}`;
  const href = artifactHref(file);
  if (!path || !file || !file.exists || !href) {
    const node = document.createElement("span");
    node.className = "file-link missing";
    node.textContent = text;
    if (path) {
      node.title = path;
    }
    return node;
  }
  const wrap = document.createElement("span");
  wrap.className = "file-link-set";
  const link = document.createElement("a");
  link.className = "file-link";
  link.href = href;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.title = path;
  link.dataset.filePath = path;
  link.textContent = text;
  wrap.append(link);
  const rawHref = artifactHref(file, "raw");
  if (rawHref && rawHref !== href) {
    const raw = document.createElement("a");
    raw.className = "file-link-action";
    raw.href = rawHref;
    raw.target = "_blank";
    raw.rel = "noopener noreferrer";
    raw.textContent = "Raw";
    wrap.append(raw);
  }
  const downloadHref = artifactHref(file, "download");
  if (downloadHref) {
    const download = document.createElement("a");
    download.className = "file-link-action";
    download.href = downloadHref;
    download.setAttribute("download", "");
    download.textContent = "Download";
    wrap.append(download);
  }
  return wrap;
}

function projectStatusClass(project) {
  if (project.delivered_status === "accepted" || project.delivered_status === "synthesized") {
    return "badge good";
  }
  if (project.delivered_status === "paused") {
    return "badge warn";
  }
  if (project.delivered_status === "rejected") {
    return "badge bad";
  }
  return "badge neutral";
}

function taskActionButton(action, task) {
  const button = document.createElement("button");
  button.className = "button";
  button.type = "button";
  button.textContent = state.runningAction === action.id ? "Running" : action.label;
  button.disabled = Boolean(state.runningAction);
  button.addEventListener("click", () => runTaskAction(action, task));
  return button;
}

function decisionActions() {
  return ((state.actions || {}).decision_actions || []);
}

function taskAllowedDecisions(task) {
  const gate = (task && task.human_gate) || {};
  const decisions = Array.isArray(gate.available_decisions)
    ? gate.available_decisions
    : ["resume", "pause", "reject"];
  return new Set(decisions.map((decision) => String(decision).trim()).filter(Boolean));
}

function isDecisionActionAvailable(action, task) {
  if (action.append_only) {
    return true;
  }
  return taskAllowedDecisions(task).has(action.decision);
}

function decisionActionButton(action, task) {
  const button = document.createElement("button");
  button.className = action.id === "decision_reject" ? "button danger" : "button secondary";
  button.type = "button";
  button.textContent = state.runningAction === action.id ? "Running" : action.label;
  button.disabled = Boolean(state.runningAction);
  button.addEventListener("click", () => openDecisionModal(action, task));
  return button;
}

function taskFilesByLabel(task) {
  return (task.files || []).reduce((acc, file) => {
    if (file && file.label) {
      acc[file.label] = file;
    }
    return acc;
  }, {});
}

function decisionEvidenceLinks(task) {
  const byLabel = taskFilesByLabel(task);
  const preferred = [
    "Worker output",
    "Review aggregate",
    "Result acceptance",
    "Status JSON",
    "Task brief",
  ];
  const links = preferred
    .map((label) => byLabel[label])
    .filter((file) => file && file.exists && artifactHref(file));
  if (!links.length) {
    const missing = document.createElement("div");
    missing.className = "decision-evidence missing";
    missing.textContent = "Evidence artifacts unavailable";
    return missing;
  }
  const list = document.createElement("div");
  list.className = "decision-evidence";
  list.replaceChildren(...links.map(detailPathLink));
  return list;
}

function decisionConsequence(action, task) {
  if (action.append_only) {
    return `records ${action.decision}; task remains ${statusLabel(task.status)}`;
  }
  const target = action.target_status ? statusLabel(action.target_status) : "unchanged";
  if (action.decision === "reject") {
    return `sets task to ${target}; stops this result path`;
  }
  if (action.decision === "pause") {
    return `sets task to ${target}; waits for more human input`;
  }
  return `sets task to ${target}; allows the workflow to continue`;
}

function decisionOptionList(task) {
  const actions = decisionActions().filter((action) => isDecisionActionAvailable(action, task));
  const list = document.createElement("div");
  list.className = "decision-options";
  if (!actions.length) {
    list.append(empty("No available decision actions."));
    return list;
  }
  for (const action of actions) {
    const row = document.createElement("div");
    row.className = "decision-option";
    const title = document.createElement("div");
    title.className = "decision-option-title";
    title.textContent = `${action.label} -> ${action.target_status ? statusLabel(action.target_status) : "log only"}`;
    const consequence = document.createElement("div");
    consequence.className = "record-meta";
    consequence.textContent = decisionConsequence(action, task);
    const command = document.createElement("code");
    command.className = "action-command decision-command-inline";
    command.textContent = decisionCommandPreview(action, task);
    row.append(title, consequence, command);
    list.append(row);
  }
  return list;
}

function sourceBlockerGuidance(task) {
  const gate = task.human_gate || {};
  const text = [
    gate.trigger,
    gate.reason,
    gate.required_human_decision,
    task.human_gate_reason,
    task.last_transition_reason,
  ].map((value) => String(value || "").toLowerCase()).join(" ");
  if (!/(source|data|library|evidence|governance)/.test(text)) {
    return null;
  }
  const sources = ((state.snapshot || {}).sources || {});
  const blocked = Array.isArray(sources.blocked_sources) ? sources.blocked_sources.slice(0, 4) : [];
  const panel = document.createElement("div");
  panel.className = "source-blocker-guidance";
  const title = document.createElement("div");
  title.className = "decision-option-title";
  title.textContent = "Source blocker guidance";
  const rows = document.createElement("div");
  rows.className = "record-meta";
  rows.textContent = blocked.length
    ? blocked.map((source) => `${valueOrUnavailable(source.source_id)}: ${valueOrUnavailable(source.reason || source.status || source.approval_status)}`).join(" / ")
    : valueOrUnavailable(gate.required_human_decision || gate.reason || task.human_gate_reason);
  const actions = document.createElement("div");
  actions.className = "record-meta";
  const dynamicActions = blocked.flatMap((source) => Array.isArray(source.available_actions) ? source.available_actions : [])
    .map(actionLabel)
    .filter(Boolean)
    .slice(0, 5);
  actions.textContent = dynamicActions.length > 0
    ? `Available routes: ${dynamicActions.join(", ")}.`
    : "Available routes: approve source, accept for planning only, continue with caveats, revise source audit, pause, or reject.";
  panel.append(title, rows, actions);
  return panel;
}

function decisionTaskCard(task) {
  const card = document.createElement("article");
  card.className = "decision-card";
  const title = document.createElement("div");
  title.className = "record-title";
  title.textContent = `${valueOrUnavailable(task.task_id)} - ${valueOrUnavailable(task.title)}`;
  const reason = document.createElement("div");
  reason.className = "record-meta";
  reason.textContent = valueOrUnavailable(task.human_gate_reason || task.last_transition_reason);
  const gate = task.human_gate || {};
  const options = document.createElement("div");
  options.className = "record-meta";
  options.textContent = Array.isArray(gate.available_decisions) && gate.available_decisions.length
    ? `options: ${gate.available_decisions.join(", ")}`
    : `status: ${statusLabel(task.status)}`;
  const controls = document.createElement("div");
  controls.className = "decision-actions";
  controls.replaceChildren(
    ...decisionActions()
      .filter((action) => isDecisionActionAvailable(action, task))
      .map((action) => decisionActionButton(action, task))
  );
  const guidance = sourceBlockerGuidance(task);
  const children = [title, reason, decisionEvidenceLinks(task), options, decisionOptionList(task)];
  if (guidance) {
    children.push(guidance);
  }
  children.push(controls);
  card.append(...children);
  return card;
}

function renderTaskDetail(rows) {
  const panel = el("task-detail");
  const task = selectedTask(rows);
  if (!task) {
    panel.replaceChildren(empty("No task selected."));
    return;
  }
  const title = document.createElement("div");
  title.className = "detail-title";
  title.textContent = `${valueOrUnavailable(task.task_id)} - ${valueOrUnavailable(task.title)}`;

  const fields = document.createElement("div");
  fields.className = "detail-grid";
  fields.replaceChildren(
    detailField("Status", statusLabel(task.status)),
    detailField("Type", task.type),
    detailField("Review Tier", task.review_tier),
    detailField("Revision", `${valueOrUnavailable(task.revision_count)} of ${valueOrUnavailable(task.max_revisions)}`),
    detailField("Lock", (task.lock_state || {}).locked ? ((task.lock_state || {}).stale ? "stale" : "locked") : "unlocked"),
    detailField("Transition", (task.transition_validation || {}).valid ? "valid" : valueOrUnavailable((task.transition_validation || {}).reason)),
    detailField("Human Gate", task.human_gate_reason),
    detailField("Last Transition", task.last_transition_reason),
    detailField("Allowed Paths", task.allowed_paths || []),
    detailField("Allowed Next", task.allowed_next_statuses || [])
  );

  const files = document.createElement("div");
  files.className = "file-list";
  for (const file of task.files || []) {
    files.append(detailPathLink(file));
  }

  const actionRow = document.createElement("div");
  actionRow.className = "detail-actions";
  const taskActions = ((state.actions || {}).task_actions || []);
  actionRow.replaceChildren(...taskActions.map((action) => taskActionButton(action, task)));

  panel.replaceChildren(title, fields, taskExplainabilityPanel(task), taskQaPanel(task), files, actionRow);
}

function renderTasks(snapshot) {
  const tasks = snapshot.tasks || {};
  const rows = tasks.all || [];
  el("task-total").textContent = asNumber(tasks.board_total || rows.length);
  renderTaskFilters(tasks, rows);
  if (rows.length > 0 && !rows.some((task) => task.task_id === state.selectedTaskId)) {
    state.selectedTaskId = rows[0].task_id;
  }
  const visible = filteredTasks(rows);
  if (visible.length > 0 && !visible.some((task) => task.task_id === state.selectedTaskId)) {
    state.selectedTaskId = visible[0].task_id;
  }
  el("task-board").replaceChildren(
    ...(visible.length ? visible.map(taskBoardRow) : [empty("No tasks match this filter.")])
  );
  renderTaskDetail(visible);
}

function renderDecisions(snapshot) {
  const decisions = snapshot.human_decisions || {};
  const rows = decisions.blocked_task_refs || [];
  el("decision-total").textContent = asNumber(decisions.open_count);
  const inbox = el("human-decisions");
  inbox.replaceChildren(
    ...(rows.length ? rows.map(decisionTaskCard) : [empty("No open human decisions.")])
  );
  renderList("decision-log", decisions.recent_decision_rows, "No recent decision rows.", (row) =>
    record(
      `${valueOrUnavailable(row.item_id)} - ${valueOrUnavailable(row.decision)}`,
      `${valueOrUnavailable(row.reason)} / ${valueOrUnavailable(row.approver)}`,
      valueOrUnavailable(row.related_artifacts)
    )
  );
}

function renderOutcomes(snapshot) {
  const delivered = snapshot.delivered_projects || {};
  const rejected = snapshot.rejected_results || {};
  const rows = delivered.rows || [];
  const summary = delivered.summary || {};
  el("outcome-total").textContent = asNumber(delivered.count || rows.length);
  el("outcome-summary").replaceChildren(
    metric("Accepted", asNumber(summary.accepted_count), `rate ${valueOrUnavailable(summary.acceptance_rate)}`),
    metric("Synthesized", asNumber(summary.synthesized_count), `${asNumber(summary.rejected_count)} rejected`),
    metric("Avg Iterations", valueOrUnavailable(summary.average_iterations), `${valueOrUnavailable(summary.total_actual_cost_usd)} actual cost`),
    metric("Revalidation", revalidationSummary(summary.revalidation_counts), "current / due / stale")
  );
  renderOutcomeFilters(delivered, rows);
  if (rows.length > 0 && !rows.some((project) => project.project_id === state.selectedProjectId)) {
    state.selectedProjectId = rows[0].project_id;
  }
  const visible = filteredProjects(rows);
  if (visible.length > 0 && !visible.some((project) => project.project_id === state.selectedProjectId)) {
    state.selectedProjectId = visible[0].project_id;
  }
  renderProjectTable(visible);
  renderProjectDetail(visible);
  renderRejectedLedger(rejected);
}

function revalidationSummary(counts) {
  const data = counts || {};
  return `${asNumber(data.current)} / ${asNumber(data.due)} / ${asNumber(data.stale)}`;
}

function renderOutcomeFilters(delivered, rows) {
  const filters = delivered.status_filter_options || ["all"];
  const counts = rows.reduce((acc, project) => {
    const status = project.delivered_status || "unknown";
    acc[status] = (acc[status] || 0) + 1;
    return acc;
  }, { all: rows.length });
  if (!filters.includes(state.outcomeFilter)) {
    state.outcomeFilter = "all";
  }
  const buttons = filters.map((filter) => {
    const button = document.createElement("button");
    button.className = filter === state.outcomeFilter ? "filter-chip active" : "filter-chip";
    button.type = "button";
    button.textContent = `${statusLabel(filter)} ${counts[filter] || 0}`;
    button.addEventListener("click", () => {
      state.outcomeFilter = filter;
      renderOutcomes(state.snapshot || {});
    });
    return button;
  });
  el("outcome-filters").replaceChildren(...buttons);
}

function filteredProjects(rows) {
  if (state.outcomeFilter === "all") {
    return rows;
  }
  return rows.filter((project) => project.delivered_status === state.outcomeFilter);
}

function renderProjectTable(rows) {
  const target = el("delivered-projects");
  if (!rows.length) {
    target.replaceChildren(empty("No delivered projects match this filter."));
    return;
  }
  const table = document.createElement("table");
  table.className = "outcome-table";
  const thead = document.createElement("thead");
  const header = document.createElement("tr");
  for (const label of ["Project", "Status", "Accepted", "Claim", "Review", "Cost"]) {
    const cell = document.createElement("th");
    cell.textContent = label;
    header.append(cell);
  }
  thead.append(header);
  const tbody = document.createElement("tbody");
  for (const project of rows) {
    tbody.append(projectTableRow(project));
  }
  table.append(thead, tbody);
  target.replaceChildren(table);
}

function projectTableRow(project) {
  const row = document.createElement("tr");
  row.className = project.project_id === state.selectedProjectId ? "selected" : "";
  row.tabIndex = 0;
  row.addEventListener("click", () => {
    state.selectedProjectId = project.project_id;
    renderOutcomes(state.snapshot || {});
  });
  row.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      state.selectedProjectId = project.project_id;
      renderOutcomes(state.snapshot || {});
    }
  });
  const projectCell = document.createElement("td");
  projectCell.textContent = `${valueOrUnavailable(project.task_id)} - ${valueOrUnavailable(project.title)}`;
  const statusCell = document.createElement("td");
  const badge = document.createElement("span");
  badge.className = projectStatusClass(project);
  badge.textContent = statusLabel(project.delivered_status);
  statusCell.append(badge);
  const acceptedCell = document.createElement("td");
  acceptedCell.textContent = valueOrUnavailable(project.accepted_date);
  const claimCell = document.createElement("td");
  claimCell.textContent = `${valueOrUnavailable(project.claim_strength)} / ${valueOrUnavailable(project.revalidation_status)}`;
  const reviewCell = document.createElement("td");
  reviewCell.textContent = `${valueOrUnavailable(project.aggregate_review_decision)} / ${valueOrUnavailable(project.reviewer_count)} reviewers`;
  const costCell = document.createElement("td");
  costCell.textContent = valueOrUnavailable(project.actual_cost_usd);
  row.append(projectCell, statusCell, acceptedCell, claimCell, reviewCell, costCell);
  return row;
}

function selectedProject(rows) {
  return rows.find((project) => project.project_id === state.selectedProjectId) || rows[0] || null;
}

function renderProjectDetail(rows) {
  const panel = el("outcome-detail");
  const project = selectedProject(rows);
  if (!project) {
    panel.replaceChildren(empty("No delivered project selected."));
    return;
  }
  const title = document.createElement("div");
  title.className = "detail-title";
  title.textContent = `${valueOrUnavailable(project.task_id)} - ${valueOrUnavailable(project.title)}`;
  const fields = document.createElement("div");
  fields.className = "detail-grid";
  fields.replaceChildren(
    detailField("Status", statusLabel(project.delivered_status)),
    detailField("Type", project.project_type),
    detailField("Accepted", project.accepted_date),
    detailField("Idea Score", `${valueOrUnavailable(project.origin_idea_id)} / ${valueOrUnavailable(project.idea_score)}`),
    detailField("Review", `${valueOrUnavailable(project.aggregate_review_decision)} / tier ${valueOrUnavailable(project.review_tier)}`),
    detailField("Reviewers", `${valueOrUnavailable(project.reviewer_count)} / disagreement ${project.reviewer_disagreement ? "yes" : "no"}`),
    detailField("Iterations", `${valueOrUnavailable(project.iteration_count)} / revisions ${valueOrUnavailable(project.revision_count)}`),
    detailField("Cost", `actual ${valueOrUnavailable(project.actual_cost_usd)} / estimate ${valueOrUnavailable(project.estimated_cost_usd)}`),
    detailField("Claim", `${valueOrUnavailable(project.claim_strength)} / ${valueOrUnavailable(project.claim_type)}`),
    detailField("Revalidation", `${valueOrUnavailable(project.revalidation_status)} / ${valueOrUnavailable(project.next_recheck_date)}`),
    detailField("Source IDs", project.source_ids || []),
    detailField("Caveats", project.caveats),
    detailField("Blocker", project.main_blocker),
    detailField("Key Finding", project.key_finding)
  );
  const files = document.createElement("div");
  files.className = "file-list";
  for (const file of project.links || []) {
    files.append(detailPathLink(file));
  }
  panel.replaceChildren(title, fields, files);
}

function renderRejectedLedger(rejected) {
  const rows = rejected.recent_rows || [];
  el("rejected-ledger-total").textContent = asNumber(rejected.count);
  renderList("rejected-ledger", rows, "No rejected ledger rows.", (row) =>
    record(
      `${valueOrUnavailable(row.task_id)} - ${valueOrUnavailable(row.route)}`,
      `${valueOrUnavailable(row.reason)} / ${valueOrUnavailable(row.claim_strength)}`,
      valueOrUnavailable(row.evidence_link || row.claim)
    )
  );
}

function promptRows(snapshot) {
  return ((snapshot.prompts || {}).prompts || []);
}

function selectedPrompt(rows) {
  return rows.find((prompt) => prompt.prompt_id === state.selectedPromptId) || rows[0] || null;
}

function promptStatusClass(prompt) {
  if (!prompt.active_exists || !prompt.draft_exists) {
    return "badge neutral";
  }
  if ((prompt.draft_validation || {}).ok === false) {
    return "badge bad";
  }
  if (prompt.has_draft_changes) {
    return "badge warn";
  }
  return "badge good";
}

function promptRow(prompt) {
  const row = document.createElement("button");
  row.className = prompt.prompt_id === state.selectedPromptId ? "task-row selected" : "task-row";
  row.type = "button";
  row.addEventListener("click", () => {
    state.selectedPromptId = prompt.prompt_id;
    renderPrompts(state.snapshot || {});
  });
  const title = document.createElement("div");
  title.className = "task-row-title";
  title.textContent = valueOrUnavailable(prompt.prompt_id);
  const meta = document.createElement("div");
  meta.className = "task-row-meta";
  meta.textContent = `${valueOrUnavailable(prompt.role)} / ${valueOrUnavailable(prompt.active_version)}`;
  const badge = document.createElement("span");
  badge.className = promptStatusClass(prompt);
  badge.textContent = (prompt.draft_validation || {}).ok === false
    ? "invalid draft"
    : (prompt.has_draft_changes ? "draft" : "current");
  row.append(title, badge, meta);
  return row;
}

function validationSummary(validation) {
  if (!validation) {
    return "unavailable";
  }
  const errors = validation.errors || [];
  const warnings = validation.warnings || [];
  return validation.ok ? `valid / ${warnings.length} warnings` : `${errors.length} errors / ${warnings.length} warnings`;
}

function validationIssueText(issue) {
  if (!issue) {
    return "unknown validation issue";
  }
  if (typeof issue === "string") {
    return issue;
  }
  const field = issue.field || issue.section || issue.path || issue.key || "validation";
  const reason = issue.reason || issue.message || issue.error || issue.code || "";
  return reason ? `${field}: ${reason}` : String(field);
}

function validationIssueList(validation) {
  if (!validation) {
    return null;
  }
  const issues = [
    ...((validation.errors || []).map((issue) => ({ kind: "error", text: validationIssueText(issue) }))),
    ...((validation.warnings || []).map((issue) => ({ kind: "warning", text: validationIssueText(issue) }))),
  ];
  if (!issues.length) {
    return null;
  }
  const container = document.createElement("div");
  container.className = "validation-details";
  const title = document.createElement("div");
  title.className = "validation-details-title";
  title.textContent = "Validation Details";
  const list = document.createElement("ul");
  list.className = "validation-list";
  issues.forEach((issue) => {
    const item = document.createElement("li");
    item.className = `validation-${issue.kind}`;
    item.textContent = issue.text;
    list.append(item);
  });
  container.append(title, list);
  return container;
}

function promptBindingsText(prompt) {
  const bindings = prompt.schedule_bindings || [];
  if (!bindings.length) {
    return "none";
  }
  return bindings.map((binding) =>
    `${valueOrUnavailable(binding.job_id)} (${valueOrUnavailable(binding.status)} / ${valueOrUnavailable(binding.prompt_version)})`
  ).join(", ");
}

function renderPromptDetail(rows) {
  const panel = el("prompt-detail");
  const prompt = selectedPrompt(rows);
  if (!prompt) {
    panel.replaceChildren(empty("Prompt library is not initialized."));
    return;
  }
  state.selectedPromptId = prompt.prompt_id;
  const title = document.createElement("div");
  title.className = "detail-title";
  title.textContent = `${valueOrUnavailable(prompt.prompt_id)} - ${valueOrUnavailable(prompt.role)}`;

  const fields = document.createElement("div");
  fields.className = "detail-grid";
  fields.replaceChildren(
    detailField("Active Version", prompt.active_version),
    detailField("Draft Version", prompt.draft_version),
    detailField("Draft Validation", validationSummary(prompt.draft_validation)),
    detailField("Schedule Bindings", promptBindingsText(prompt))
  );

  const author = document.createElement("input");
  author.id = "prompt-author";
  author.className = "text-input";
  author.type = "text";
  author.value = window.localStorage.getItem("asyncResearchPromptAuthor") || "human";

  const reason = document.createElement("input");
  reason.id = "prompt-reason";
  reason.className = "text-input";
  reason.type = "text";
  reason.value = "";

  const editor = document.createElement("textarea");
  editor.id = "prompt-editor";
  editor.className = "text-area prompt-editor";
  editor.rows = 18;
  editor.value = prompt.draft_text || prompt.active_text || "";

  const allowInvalid = document.createElement("label");
  allowInvalid.className = "checkbox-label";
  const checkbox = document.createElement("input");
  checkbox.id = "prompt-allow-invalid";
  checkbox.type = "checkbox";
  allowInvalid.append(checkbox, document.createTextNode("Allow invalid activation"));

  const controls = document.createElement("div");
  controls.className = "detail-actions";
  const save = document.createElement("button");
  save.className = "button secondary";
  save.type = "button";
  save.textContent = state.runningAction === "prompt_save_draft" ? "Saving" : "Save Draft";
  save.disabled = Boolean(state.runningAction);
  save.addEventListener("click", () => runPromptDraft(prompt));
  const activate = document.createElement("button");
  activate.className = "button";
  activate.type = "button";
  activate.textContent = state.runningAction === "prompt_activate" ? "Activating" : "Activate";
  activate.disabled = Boolean(state.runningAction);
  activate.addEventListener("click", () => runPromptActivate(prompt));
  controls.append(save, activate);

  const diff = document.createElement("pre");
  diff.className = "result-output prompt-diff";
  diff.textContent = prompt.diff || "No active-vs-draft changes.";
  const validationIssues = validationIssueList(prompt.draft_validation);

  const form = document.createElement("div");
  form.className = "prompt-form";
  form.append(
    detailField("Author", ""),
    author,
    detailField("Reason", ""),
    reason,
    editor,
    allowInvalid,
    controls
  );

  const children = [title, fields];
  if (validationIssues) {
    children.push(validationIssues);
  }
  children.push(form, diff);
  panel.replaceChildren(...children);
}

function renderPrompts(snapshot) {
  const prompts = snapshot.prompts || {};
  const rows = promptRows(snapshot);
  el("prompt-total").textContent = prompts.available ? rows.length : 0;
  el("prompt-init").disabled = Boolean(state.runningAction);
  const listChildren = prompts.available && rows.length ? rows.map(promptRow) : [empty("Prompt library is not initialized.")];
  el("prompt-list").replaceChildren(...listChildren);
  renderPromptDetail(prompts.available ? rows : []);
}

function scheduleRows(snapshot) {
  return ((snapshot.schedules || {}).jobs || []);
}

function selectedSchedule(rows) {
  return rows.find((job) => job.job_id === state.selectedScheduleId) || rows[0] || null;
}

function scheduleStatusClass(job, schedules) {
  if (!schedules || schedules.available === false) {
    return "badge neutral";
  }
  if ((schedules.validation || {}).ok === false) {
    return "badge bad";
  }
  if (job.status === "enabled") {
    return "badge good";
  }
  return "badge neutral";
}

function schedulePromptText(job) {
  const binding = job.prompt_binding || {};
  return `${valueOrUnavailable(binding.prompt_id)} / ${valueOrUnavailable(binding.prompt_version)}`;
}

function scheduleRow(job, schedules) {
  const row = document.createElement("button");
  row.className = job.job_id === state.selectedScheduleId ? "task-row selected" : "task-row";
  row.type = "button";
  row.addEventListener("click", () => {
    state.selectedScheduleId = job.job_id;
    renderSchedules(state.snapshot || {});
  });
  const title = document.createElement("div");
  title.className = "task-row-title";
  title.textContent = valueOrUnavailable(job.job_id);
  const badge = document.createElement("span");
  badge.className = scheduleStatusClass(job, schedules);
  badge.textContent = statusLabel(job.status);
  const meta = document.createElement("div");
  meta.className = "task-row-meta";
  meta.textContent = `${valueOrUnavailable(job.cadence)} / ${schedulePromptText(job)}`;
  row.append(title, badge, meta);
  return row;
}

function promptSelectOptions(snapshot, currentPromptId) {
  const rows = promptRows(snapshot);
  const ids = rows.map((prompt) => prompt.prompt_id).filter(Boolean);
  if (currentPromptId && !ids.includes(currentPromptId)) {
    ids.push(currentPromptId);
  }
  return ids.map((promptId) => {
    const prompt = rows.find((row) => row.prompt_id === promptId) || {};
    const option = document.createElement("option");
    option.value = promptId;
    option.textContent = prompt.active_version ? `${promptId} / ${prompt.active_version}` : promptId;
    return option;
  });
}

function textInput(id, value, type = "text") {
  const input = document.createElement("input");
  input.id = id;
  input.className = "text-input";
  input.type = type;
  input.value = value || "";
  return input;
}

function renderScheduleDetail(rows, snapshot) {
  const panel = el("schedule-detail");
  const schedules = snapshot.schedules || {};
  const job = selectedSchedule(rows);
  if (!job) {
    panel.replaceChildren(empty("Schedule manifest is not initialized."));
    return;
  }
  state.selectedScheduleId = job.job_id;
  const binding = job.prompt_binding || {};
  const title = document.createElement("div");
  title.className = "detail-title";
  title.textContent = `${valueOrUnavailable(job.job_id)} - ${statusLabel(job.status)}`;

  const fields = document.createElement("div");
  fields.className = "detail-grid";
  fields.replaceChildren(
    detailField("Cadence", job.cadence),
    detailField("Prompt Binding", schedulePromptText(job)),
    detailField("Max Runtime", `${valueOrUnavailable(job.max_runtime_minutes)} minutes`),
    detailField("Concurrency", `${valueOrUnavailable(job.concurrency_key)} / ${valueOrUnavailable(job.concurrency_limit)}`)
  );

  const status = document.createElement("select");
  status.id = "schedule-status";
  status.className = "select";
  ["enabled", "disabled"].forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = statusLabel(value);
    status.append(option);
  });
  status.value = job.status === "enabled" ? "enabled" : "disabled";

  const prompt = document.createElement("select");
  prompt.id = "schedule-prompt-id";
  prompt.className = "select";
  const options = promptSelectOptions(snapshot, binding.prompt_id);
  if (options.length) {
    prompt.append(...options);
  } else {
    const option = document.createElement("option");
    option.value = binding.prompt_id || "";
    option.textContent = binding.prompt_id || "unavailable";
    prompt.append(option);
  }
  prompt.value = binding.prompt_id || "";

  const maxRuntime = textInput("schedule-max-runtime", job.max_runtime_minutes || 30, "number");
  maxRuntime.min = "1";
  maxRuntime.max = "1440";
  const concurrencyLimit = textInput("schedule-concurrency-limit", job.concurrency_limit || 1, "number");
  concurrencyLimit.min = "1";
  concurrencyLimit.max = "20";
  const promptVersion = textInput("schedule-prompt-version", binding.prompt_version);
  prompt.addEventListener("change", () => {
    const selected = promptRows(snapshot).find((row) => row.prompt_id === prompt.value);
    if (selected && selected.active_version) {
      promptVersion.value = selected.active_version;
    }
  });

  const form = document.createElement("div");
  form.className = "prompt-form";
  const controls = document.createElement("div");
  controls.className = "detail-actions";
  const save = document.createElement("button");
  save.className = "button secondary";
  save.type = "button";
  save.textContent = state.runningAction === "schedule_save" ? "Saving" : "Save";
  save.disabled = Boolean(state.runningAction);
  save.addEventListener("click", () => runScheduleSave(job));
  const enable = document.createElement("button");
  enable.className = "button";
  enable.type = "button";
  enable.textContent = state.runningAction === "schedule_enable" ? "Enabling" : "Enable Intent";
  enable.disabled = Boolean(state.runningAction);
  enable.addEventListener("click", () => runScheduleStatus("schedule_enable", job));
  const trigger = document.createElement("button");
  trigger.className = "button secondary";
  trigger.type = "button";
  trigger.textContent = state.runningAction === "schedule_trigger_dry_run" ? "Previewing" : "Preview Trigger";
  trigger.disabled = Boolean(state.runningAction);
  trigger.addEventListener("click", () => runScheduleTriggerDryRun(job));
  const runNow = document.createElement("button");
  runNow.className = "button";
  runNow.type = "button";
  runNow.textContent = state.runningAction === "schedule_trigger_now" ? "Running" : "Run Now";
  runNow.disabled = Boolean(state.runningAction);
  runNow.addEventListener("click", () => runScheduleTriggerNow(job));
  const disable = document.createElement("button");
  disable.className = "button secondary";
  disable.type = "button";
  disable.textContent = state.runningAction === "schedule_disable" ? "Disabling" : "Disable Intent";
  disable.disabled = Boolean(state.runningAction);
  disable.addEventListener("click", () => runScheduleStatus("schedule_disable", job));
  controls.append(save, trigger, runNow, enable, disable);

  form.append(
    detailField("Job ID", ""),
    textInput("schedule-job-id", job.job_id),
    detailField("Description", ""),
    textInput("schedule-description", job.description),
    detailField("Status", ""),
    status,
    detailField("Cadence", ""),
    textInput("schedule-cadence", job.cadence),
    detailField("Prompt", ""),
    prompt,
    detailField("Prompt Version", ""),
    promptVersion,
    detailField("Max Runtime Minutes", ""),
    maxRuntime,
    detailField("Concurrency Key", ""),
    textInput("schedule-concurrency-key", job.concurrency_key),
    detailField("Concurrency Limit", ""),
    concurrencyLimit,
    detailField("Disabled Reason", ""),
    textInput("schedule-disabled-reason", job.disabled_reason),
    detailField("Author", ""),
    textInput("schedule-author", window.localStorage.getItem("asyncResearchScheduleAuthor") || "human"),
    detailField("Reason", ""),
    textInput("schedule-reason", ""),
    controls
  );

  const validationIssues = validationIssueList(schedules.validation);
  const children = [title, fields];
  if (validationIssues) {
    children.push(validationIssues);
  }
  children.push(form);
  panel.replaceChildren(...children);
}

function renderSchedules(snapshot) {
  const schedules = snapshot.schedules || {};
  const rows = scheduleRows(snapshot);
  el("schedule-total").textContent = schedules.available ? rows.length : 0;
  el("schedule-init").disabled = Boolean(state.runningAction);
  const listChildren = schedules.available && rows.length ? rows.map((job) => scheduleRow(job, schedules)) : [empty("Schedule manifest is not initialized.")];
  el("schedule-list").replaceChildren(...listChildren);
  renderScheduleDetail(schedules.available ? rows : [], snapshot);
}

function decisionCommandPreview(action, task) {
  return String(action.command_template || "")
    .replace("<task_id>", valueOrUnavailable(task.task_id))
    .replace("<task_dir>", valueOrUnavailable(task.task_dir))
    .replace("<status_path>", valueOrUnavailable(task.status_path));
}

function openDecisionModal(action, task) {
  state.pendingDecision = { action, task };
  el("decision-modal-title").textContent = action.label;
  el("decision-modal-task").textContent = `${valueOrUnavailable(task.task_id)} - ${valueOrUnavailable(task.title)}`;
  el("decision-command-preview").textContent = decisionCommandPreview(action, task);
  el("decision-form-error").textContent = "";
  el("decision-reason").value = "";
  el("decision-approver").value = window.localStorage.getItem("asyncResearchDecisionApprover") || "";
  const modal = el("decision-modal");
  modal.classList.add("open");
  modal.setAttribute("aria-hidden", "false");
  el("decision-reason").focus();
}

function closeDecisionModal() {
  state.pendingDecision = null;
  const modal = el("decision-modal");
  modal.classList.remove("open");
  modal.setAttribute("aria-hidden", "true");
}

function lifecycleStatusClass(station) {
  if (!station) {
    return "badge neutral";
  }
  if (station.status === "complete") {
    return "badge good";
  }
  if (station.status === "blocked") {
    return "badge bad";
  }
  if (station.status === "active" || station.status === "queued") {
    return "badge warn";
  }
  return "badge neutral";
}

function lifecycleCommandNode(command) {
  const node = document.createElement("code");
  node.className = "action-command lifecycle-command";
  node.textContent = valueOrUnavailable((command || {}).command);
  return node;
}

function lifecycleAcceptedOutputs(outputs) {
  const list = document.createElement("div");
  list.className = "lifecycle-output-list";
  if (!outputs || outputs.length === 0) {
    list.append(empty("No accepted outputs linked to this station."));
    return list;
  }
  for (const output of outputs) {
    const row = document.createElement("div");
    row.className = "record-row";
    const title = document.createElement("div");
    title.className = "record-title";
    title.textContent = `${valueOrUnavailable(output.task_id)} - ${valueOrUnavailable(output.title)}`;
    const meta = document.createElement("div");
    meta.className = "record-meta";
    meta.textContent = `${statusLabel(output.status)} / ${valueOrUnavailable(output.claim_strength)} / ${valueOrUnavailable(output.accepted_date)}`;
    row.append(title, meta);
    const links = (output.links || []).filter((file) => file && file.exists && artifactHref(file));
    if (links.length) {
      const files = document.createElement("div");
      files.className = "file-list";
      links.slice(0, 3).forEach((file) => files.append(detailPathLink(file)));
      row.append(files);
    }
    list.append(row);
  }
  return list;
}

function lifecycleBlockers(blockers) {
  const list = document.createElement("div");
  list.className = "lifecycle-blockers";
  if (!blockers || blockers.length === 0) {
    return list;
  }
  for (const blocker of blockers) {
    list.append(record(
      `${valueOrUnavailable(blocker.task_id || blocker.source_id || blocker.status)} - ${valueOrUnavailable(blocker.reason)}`,
      valueOrUnavailable(blocker.task_dir || blocker.path)
    ));
  }
  return list;
}

function lifecycleStationCard(station, index) {
  const card = document.createElement("article");
  card.className = `lifecycle-station lifecycle-${station.status || "unknown"}`;
  const marker = document.createElement("div");
  marker.className = "lifecycle-marker";
  marker.textContent = String(index + 1);

  const body = document.createElement("div");
  body.className = "lifecycle-body";
  const heading = document.createElement("div");
  heading.className = "lifecycle-heading";
  const title = document.createElement("div");
  title.className = "record-title";
  title.textContent = valueOrUnavailable(station.label);
  const badge = document.createElement("span");
  badge.className = lifecycleStatusClass(station);
  badge.textContent = statusLabel(station.status);
  heading.append(title, badge);

  const objective = document.createElement("div");
  objective.className = "record-meta";
  objective.textContent = valueOrUnavailable(station.objective);

  const fields = document.createElement("div");
  fields.className = "lifecycle-fields";
  fields.replaceChildren(
    detailField("Owner / Runner", station.owner_runner),
    detailField("Current Task", station.active_task ? `${valueOrUnavailable(station.active_task.task_id)} / ${statusLabel(station.active_task.status)}` : "none"),
    detailField("Next", station.next_recommended_task),
    detailField("Summary", station.summary)
  );

  const files = document.createElement("div");
  files.className = "file-list";
  for (const file of ((station.active_task || {}).files || [])) {
    files.append(detailPathLink(file));
  }
  for (const file of station.artifact_links || []) {
    files.append(detailPathLink(file));
  }

  body.append(heading, objective, fields, lifecycleCommandNode(station.next_command), lifecycleBlockers(station.blockers), files, lifecycleAcceptedOutputs(station.accepted_outputs));
  card.append(marker, body);
  return card;
}

function renderLifecycle(snapshot) {
  const lifecycle = snapshot.lifecycle || {};
  const stations = lifecycle.stations || [];
  el("lifecycle-current").textContent = lifecycle.current_station_label
    ? `Current: ${lifecycle.current_station_label}`
    : "Unavailable";
  el("lifecycle-summary").replaceChildren(
    metric("Stations", asNumber(lifecycle.station_count), `${asNumber(lifecycle.completed_count)} complete`),
    metric("Active / Blocked", asNumber(lifecycle.active_count), `missing ${asNumber(lifecycle.missing_count)}`),
    metric("Accepted Outputs", asNumber(lifecycle.accepted_output_count), "linked into lifecycle stations"),
    metric("Next Action", valueOrUnavailable(lifecycle.current_station_label), valueOrUnavailable(lifecycle.next_action))
  );
  el("lifecycle-map").replaceChildren(
    ...(stations.length ? stations.map(lifecycleStationCard) : [empty("Lifecycle is unavailable until the workspace is initialized.")])
  );
}

function deliverableReadinessClass(row) {
  if (!row) {
    return "badge neutral";
  }
  if (row.target_ready) {
    return "badge good";
  }
  if ((row.blockers || []).length > 0) {
    return "badge bad";
  }
  if ((row.warnings || []).length > 0) {
    return "badge warn";
  }
  return "badge neutral";
}

function deliverableMaturityText(row) {
  const maturity = row.maturity || {};
  return `current ${statusLabel(maturity.current)} / target ${statusLabel(maturity.target)} / ceiling ${statusLabel(maturity.verified_ceiling)}`;
}

function deliverableQaText(row) {
  const qa = row.editorial_qa || {};
  const acceptance = row.task_acceptance || {};
  return [
    `checklist ${asNumber(qa.satisfied_gate_count)}/${asNumber(qa.required_gate_count)}`,
    `critic ${statusLabel(qa.critic_status)}`,
    `response ${statusLabel(qa.response_matrix_status)}`,
    `accepted source tasks ${asNumber(acceptance.accepted_source_task_count)}/${asNumber(acceptance.source_task_count)} evidence only`,
  ].join(" / ");
}

function deliverableRecord(row) {
  const wrapper = document.createElement("div");
  wrapper.className = "record-row";
  const heading = document.createElement("div");
  heading.className = "lifecycle-heading";
  const title = document.createElement("div");
  title.className = "record-title";
  title.textContent = `${valueOrUnavailable(row.deliverable_id)} - ${valueOrUnavailable(row.title)}`;
  const badge = document.createElement("span");
  badge.className = deliverableReadinessClass(row);
  badge.textContent = valueOrUnavailable(row.readiness_label);
  heading.append(title, badge);
  const meta = document.createElement("div");
  meta.className = "record-meta";
  meta.textContent = deliverableMaturityText(row);
  const qa = document.createElement("div");
  qa.className = "record-meta";
  qa.textContent = deliverableQaText(row);
  const audience = document.createElement("div");
  audience.className = "record-meta";
  audience.textContent = `audience ${valueOrUnavailable(row.target_audience)} / venue ${valueOrUnavailable(row.target_venue)} / independence ${statusLabel((row.review_independence || {}).achieved)}`;
  wrapper.append(heading, meta, qa, audience);
  return wrapper;
}

function deliverableAttentionRecord(row) {
  const blockers = (row.blockers || []).slice(0, 3).map((item) => `${valueOrUnavailable(item.reason)}: ${valueOrUnavailable(item.message)}`);
  const warnings = (row.warnings || []).slice(0, 2).map((item) => `${valueOrUnavailable(item.reason)}: ${valueOrUnavailable(item.message)}`);
  const details = [...blockers, ...warnings];
  return record(
    `${valueOrUnavailable(row.deliverable_id)} - ${valueOrUnavailable(row.readiness_label)}`,
    `${asNumber((row.blockers || []).length)} blocker(s) / ${asNumber((row.warnings || []).length)} warning(s)`,
    details.length ? details.join(" / ") : deliverableQaText(row)
  );
}

function renderDeliverables(snapshot) {
  const deliverables = snapshot.deliverables || {};
  const summary = deliverables.summary || {};
  const rows = deliverables.rows || [];
  const attention = deliverables.attention_rows || [];
  el("deliverable-total").textContent = asNumber(deliverables.count || rows.length);
  el("deliverable-summary").replaceChildren(
    metric("Ready", asNumber(summary.target_ready_count), `${asNumber(summary.deliverable_count)} tracked`),
    metric("Blocked", asNumber(summary.blocked_count), `${asNumber(summary.warning_count)} warning signals`),
    metric("Open Gaps", asNumber(summary.open_gap_count), `${asNumber(summary.open_critical_major_response_count)} critical or major responses`),
    metric("Same-Agent Reviews", asNumber(summary.same_agent_review_count), "visible below independence requirement")
  );
  renderList("deliverable-list", rows, "No deliverables declared yet.", deliverableRecord);
  renderFoundationLinks("deliverable-links", deliverables.links);
  renderList("deliverable-attention", attention, "No deliverable maturity attention needed.", deliverableAttentionRecord);
}

function foundationCard(name, group, countKeys) {
  const card = document.createElement("article");
  card.className = "foundation-card";
  const summary = group && group.summary ? group.summary : {};
  const lines = countKeys.map((key) => `${key.replaceAll("_", " ")}: ${valueOrUnavailable(summary[key])}`);
  if (group && group.available === false) {
    lines.unshift(valueOrUnavailable(group.reason));
  }
  card.innerHTML = `
    <div class="metric-label"></div>
    <div class="metric-value"></div>
    <div class="metric-note"></div>
  `;
  card.querySelector(".metric-label").textContent = name;
  card.querySelector(".metric-value").textContent = group && group.available === false ? "unavailable" : "available";
  card.querySelector(".metric-note").textContent = lines.join(" / ");
  return card;
}

function compactTextList(values, emptyText = "none") {
  if (!Array.isArray(values) || values.length === 0) {
    return emptyText;
  }
  return values.map(valueOrUnavailable).join(", ");
}

function findingText(finding) {
  return `${valueOrUnavailable(finding.reason || finding.check || finding.severity)} / ${valueOrUnavailable(finding.message || finding.path)}`;
}

function renderFoundationLinks(target, links) {
  const rows = Array.isArray(links) ? links.filter((file) => file && file.path) : [];
  const list = el(target);
  if (!rows.length) {
    list.replaceChildren(empty("No foundation artifact links."));
    return;
  }
  list.replaceChildren(...rows.map(detailPathLink));
}

function ideaDrilldownRows(ideas) {
  const sections = (ideas && ideas.sections) || {};
  const rows = [];
  (sections.candidate_ideas || []).slice(0, 4).forEach((idea) => {
    rows.push(record(
      `Candidate ${valueOrUnavailable(idea.idea_id)} - ${valueOrUnavailable(idea.title)}`,
      `score ${valueOrUnavailable(idea.weighted_score)} / priority ${valueOrUnavailable(idea.human_priority)} / next ${valueOrUnavailable(idea.recommended_next_task)}`,
      `status ${statusLabel(idea.status)} / blockers ${compactTextList(idea.hard_gate_blockers, "none")} / issues ${asNumber(idea.issue_count)}`
    ));
  });
  (sections.promoted_ideas || []).slice(0, 3).forEach((idea) => {
    rows.push(record(
      `Promoted ${valueOrUnavailable(idea.idea_id)} - ${valueOrUnavailable(idea.title)}`,
      `task ${valueOrUnavailable(idea.promoted_task_id)} / status ${statusLabel(idea.status)}`,
      `updated ${valueOrUnavailable(idea.updated_at)}`
    ));
  });
  (sections.idea_to_task_links || []).slice(0, 3).forEach((link) => {
    rows.push(record(
      `Task Link ${valueOrUnavailable(link.idea_id)} -> ${valueOrUnavailable(link.promoted_task_id)}`,
      statusLabel(link.link_status),
      valueOrUnavailable(link.title)
    ));
  });
  (sections.next_recommended_tasks || []).slice(0, 3).forEach((task) => {
    rows.push(record(
      `Next Task ${valueOrUnavailable(task.recommended_next_task)}`,
      `${asNumber(task.idea_count)} idea${asNumber(task.idea_count) === 1 ? "" : "s"}`,
      compactTextList((task.ideas || []).map((idea) => idea.idea_id), "no ideas")
    ));
  });
  (sections.top_blockers || []).slice(0, 3).forEach((finding) => {
    rows.push(record(
      `Blocker ${valueOrUnavailable(finding.candidate_id || finding.idea_id)}`,
      valueOrUnavailable(finding.reason),
      findingText(finding)
    ));
  });
  return rows;
}

function libraryDrilldownRows(library) {
  const sections = (library && library.sections) || {};
  const rows = [];
  (sections.coverage_by_topic || []).slice(0, 3).forEach((topic) => {
    rows.push(record(
      `Topic ${valueOrUnavailable(topic.topic)}`,
      `confidence ${valueOrUnavailable(topic.confidence)} / sources ${asNumber(topic.source_count)}`,
      valueOrUnavailable(topic.summary || topic.caveats)
    ));
  });
  (sections.claims || []).slice(0, 3).forEach((claim) => {
    rows.push(record(
      `Claim ${valueOrUnavailable(claim.claim)}`,
      `${valueOrUnavailable(claim.claim_strength)} / ${statusLabel(claim.disputed_status)}`,
      `sources ${compactTextList(claim.source_refs, "none")} / caveats ${valueOrUnavailable(claim.caveats)}`
    ));
  });
  (sections.methods || []).slice(0, 3).forEach((method) => {
    rows.push(record(
      `Method ${valueOrUnavailable(method.method)}`,
      valueOrUnavailable(method.use_case),
      `sources ${compactTextList(method.source_refs, "none")} / risks ${valueOrUnavailable(method.risks)}`
    ));
  });
  (sections.open_questions || []).slice(0, 3).forEach((question) => {
    rows.push(record(
      `Open Question ${valueOrUnavailable(question.question_id)}`,
      valueOrUnavailable(question.question),
      `next ${valueOrUnavailable(question.next_task)} / status ${statusLabel(question.status)}`
    ));
  });
  (sections.risky_sources || []).slice(0, 3).forEach((source) => {
    rows.push(record(
      `Risky Source ${valueOrUnavailable(source.source_id)}`,
      `${statusLabel(source.status)} / ${valueOrUnavailable(source.trust_tier)}`,
      valueOrUnavailable(source.notes || source.title)
    ));
  });
  (sections.risky_claims || []).slice(0, 3).forEach((claim) => {
    rows.push(record(
      `Risky Claim ${valueOrUnavailable(claim.claim)}`,
      `${valueOrUnavailable(claim.claim_strength)} / ${statusLabel(claim.disputed_status)}`,
      `risky refs ${valueOrUnavailable(JSON.stringify(claim.risky_source_refs || {}))}`
    ));
  });
  (sections.validator_findings || []).slice(0, 3).forEach((finding) => {
    rows.push(record(
      `Validator ${valueOrUnavailable(finding.reason)}`,
      valueOrUnavailable(finding.severity),
      findingText(finding)
    ));
  });
  return rows;
}

function renderFoundations(snapshot) {
  el("foundation-cards").replaceChildren(
    foundationCard("Ideas", snapshot.ideas, ["candidate_count", "failure_count", "warning_count"]),
    foundationCard("Data", snapshot.data, ["source_count", "data_gap_count", "validator_warning_count"]),
    foundationCard("Library", snapshot.library, ["source_count", "claim_count", "validator_warning_count"]),
    foundationCard("Analysis", snapshot.analysis, ["active_run_analysis_count", "preflight_blocked_count", "revalidation_needed_count"])
  );
  const ideaRows = ideaDrilldownRows(snapshot.ideas || {});
  el("idea-drilldown").replaceChildren(...(ideaRows.length ? ideaRows : [empty("No idea catalog records.")]));
  renderFoundationLinks("idea-foundation-links", (snapshot.ideas || {}).links);
  const libraryRows = libraryDrilldownRows(snapshot.library || {});
  el("library-drilldown").replaceChildren(...(libraryRows.length ? libraryRows : [empty("No library records.")]));
  renderFoundationLinks("library-foundation-links", (snapshot.library || {}).links);
}

function commandRow(command) {
  return record(valueOrUnavailable(command.label), valueOrUnavailable(command.command));
}

function sourceTitle(source) {
  return `${valueOrUnavailable(source.source_id)} - ${valueOrUnavailable(source.source_name)}`;
}

function detailSummary(value) {
  if (!value) {
    return "";
  }
  if (Array.isArray(value)) {
    return `${value.length} detail item${value.length === 1 ? "" : "s"}`;
  }
  if (typeof value === "object") {
    if (Array.isArray(value.sources)) {
      return `${value.sources.length} source${value.sources.length === 1 ? "" : "s"}`;
    }
    const counts = ["error_count", "warning_count", "source_count", "row_count"]
      .filter((key) => value[key] !== undefined && value[key] !== null)
      .map((key) => `${key.replaceAll("_", " ")} ${value[key]}`);
    return counts.length ? counts.join(" / ") : `${Object.keys(value).length} detail fields`;
  }
  return String(value);
}

function renderOperations(snapshot) {
  const cost = snapshot.cost || {};
  const sources = snapshot.sources || {};
  const health = snapshot.health || {};
  const accepted = snapshot.accepted_outputs || {};
  const healthSummary = health.summary || {};
  const sourceSummary = sources.summary || {};
  const costSummary = cost.summary || {};
  const staleRows = accepted.stale_rows || [];
  const dueRows = accepted.due_rows || [];
  const healthAlerts = health.alerts || [];
  const sourceAttention = sources.attention_sources || [];
  const taskCosts = Array.isArray(cost.task_costs) ? cost.task_costs : [];
  const roleCosts = Array.isArray(cost.role_costs) ? cost.role_costs : [];
  const modelCosts = Array.isArray(cost.model_provider_costs) ? cost.model_provider_costs : [];
  const costRows = Array.isArray(cost.top_spend_rows) && cost.top_spend_rows.length > 0
    ? cost.top_spend_rows
    : cost.recent_rows || [];

  el("operation-total").textContent = asNumber(healthSummary.alert_count) + asNumber(sourceSummary.blocked_source_count) + asNumber((accepted.memory_decay || {}).stale_count);
  el("operation-summary").replaceChildren(
    metric("Monthly Budget", statusLabel(cost.monthly_budget_state), `${money(cost.month_spend_usd)} / ${money(cost.monthly_budget_usd)} (${percent(cost.monthly_usage_ratio)})`),
    metric("Weekly Budget", statusLabel(cost.weekly_budget_state), `${money(cost.week_spend_usd)} / ${money(cost.weekly_budget_usd)} (${percent(cost.weekly_usage_ratio)})`),
    metric("Sources Needing Review", sourceAttention.length, `${asNumber(sourceSummary.usable_today_count)} usable today`),
    metric("Task Economics", asNumber(costSummary.task_cost_count), `${asNumber(costSummary.approval_required_count)} approvals / ${asNumber(costSummary.network_use_count)} network rows`)
  );
  renderList("cost-task-drilldown", taskCosts, "No task economics rows.", (row) =>
    record(
      `${valueOrUnavailable(row.item_id)} - ${money(row.amount_usd)}`,
      `${valueOrUnavailable(row.task_type)} / ${statusLabel(row.task_status)} / budget ${money(row.planned_total_usd)} (${percent(row.budget_ratio)})`,
      `actual ${money(row.actual_spend_usd)} / estimate ${money(row.estimated_spend_usd)} / API ${money(row.api_usd)} / compute ${money(row.compute_usd)} / data ${money(row.data_usd)} / ${row.network_use ? "network" : "no network signal"} / approval ${statusLabel(row.approval_status)}`
    )
  );
  renderList("cost-role-drilldown", roleCosts, "No role cost rows.", (row) =>
    record(
      `Role ${valueOrUnavailable(row.label)} - ${money(row.amount_usd)}`,
      `${asNumber(row.row_count)} rows / actual ${money(row.actual_spend_usd)} / estimate ${money(row.estimated_spend_usd)}`,
      `${valueOrUnavailable(row.total_tokens)} tokens / API ${money(row.api_usd)} / compute ${money(row.compute_usd)}`
    )
  );
  renderList("cost-model-drilldown", modelCosts, "No model or provider cost rows.", (row) =>
    record(
      `Model ${valueOrUnavailable(row.label)} - ${money(row.amount_usd)}`,
      `${asNumber(row.row_count)} rows / actual ${money(row.actual_spend_usd)} / estimate ${money(row.estimated_spend_usd)}`,
      `${valueOrUnavailable(row.total_tokens)} tokens / API ${money(row.api_usd)} / data ${money(row.data_usd)}`
    )
  );
  renderList("cost-ledger", costRows, "No cost ledger rows.", (row) =>
    record(
      `${valueOrUnavailable(row.item_id)} - ${money(row.amount_usd)}`,
      `${valueOrUnavailable(row.date)} / ${valueOrUnavailable(row.role)} / ${valueOrUnavailable(row.provider || row.model_or_tool)}`,
      `${valueOrUnavailable(row.total_tokens)} tokens / API ${money(row.api_usd)} / compute ${money(row.compute_usd)} / ${valueOrUnavailable(row.notes || row.usage_source)}`
    )
  );
  renderList("cost-recovery-commands", cost.recovery_commands, "No cost commands.", commandRow);
  renderList("source-attention", sourceAttention, "No source governance attention needed.", (source) =>
    record(
      sourceTitle(source),
      `${statusLabel(source.approval_status)} / ${valueOrUnavailable(source.source_tier)} / ${valueOrUnavailable((source.attention_reasons || []).join(", "))}`,
      [valueOrUnavailable(source.last_reviewed), valueOrUnavailable(source.known_limitations || source.usability_reason || source.review_notes), sourceActionSummary(source)]
        .filter(Boolean)
        .join(" / ")
    )
  );
  renderList("source-recovery-commands", sources.recovery_commands, "No source commands.", commandRow);
  renderList("health-alerts", healthAlerts, "No health alerts.", (alert) =>
    record(
      `${valueOrUnavailable(alert.severity)} - ${valueOrUnavailable(alert.check)}`,
      valueOrUnavailable(alert.message),
      detailSummary(alert.details)
    )
  );
  renderList("accepted-evidence", [...staleRows, ...dueRows], "No stale or due accepted evidence.", (row) =>
    record(
      `${valueOrUnavailable(row.task_id)} - ${valueOrUnavailable(row.title)}`,
      `${statusLabel(row.revalidation_status)} / ${valueOrUnavailable(row.next_recheck_date)} / ${valueOrUnavailable(row.claim_type)}`,
      valueOrUnavailable(row.source_ids || row.evidence_link)
    )
  );
  renderList("health-recovery-commands", health.recovery_commands, "No health commands.", commandRow);
}

function renderRuns(snapshot) {
  const runs = snapshot.runs || {};
  el("run-total").textContent = runs.count || 0;
  renderList("recent-runs", runs.recent_runs, "No run artifacts.", (run) =>
    record(
      `${valueOrUnavailable(run.run_id)} - ${valueOrUnavailable(run.status)}`,
      `${valueOrUnavailable(run.job_id)} / exit ${run.exit_code === null || run.exit_code === undefined ? "unavailable" : run.exit_code}`,
      valueOrUnavailable(run.final_message_preview || `${valueOrUnavailable(run.started_at)} -> ${valueOrUnavailable(run.finished_at)}`)
    )
  );
}

function renderWarnings(snapshot) {
  const warnings = snapshot.warnings || [];
  el("warning-total").textContent = warnings.length;
  renderList("warnings-list", warnings, "No snapshot warnings.", (warning) =>
    record(
      `${valueOrUnavailable(warning.severity)} - ${valueOrUnavailable(warning.reason || warning.check)}`,
      valueOrUnavailable(warning.message),
      valueOrUnavailable(warning.path)
    )
  );
}

function setupRow(title, status, detail) {
  const row = document.createElement("div");
  row.className = "record-row";
  const titleNode = document.createElement("div");
  titleNode.className = "record-title";
  titleNode.textContent = title;
  const statusNode = document.createElement("div");
  statusNode.className = "record-meta";
  statusNode.textContent = status;
  const detailNode = document.createElement("div");
  detailNode.className = "record-meta";
  detailNode.textContent = detail;
  row.append(titleNode, statusNode, detailNode);
  return row;
}

function resultSummary(action) {
  const result = state.results[action.id];
  if (!result) {
    return "not run in this browser session";
  }
  return `${result.status} / exit ${result.exit_code} / ${valueOrUnavailable(result.finished_at)}`;
}

function actionBadge(action) {
  const badge = document.createElement("span");
  badge.className = action.mutates ? "badge warn" : "badge neutral";
  badge.textContent = action.mutates ? "mutates files" : "read-only";
  return badge;
}

function actionButton(action) {
  const button = document.createElement("button");
  button.className = "button";
  button.type = "button";
  button.dataset.action = action.id;
  button.textContent = state.runningAction === action.id ? "Running" : "Run";
  button.disabled = Boolean(state.runningAction);
  button.addEventListener("click", () => runAction(action));
  return button;
}

function actionCard(action) {
  const card = document.createElement("article");
  card.className = "action-card";
  const header = document.createElement("div");
  header.className = "action-card-header";
  const title = document.createElement("div");
  title.className = "action-title";
  title.textContent = action.label;
  header.append(title, actionBadge(action));

  const description = document.createElement("div");
  description.className = "record-meta";
  description.textContent = action.description;

  const command = document.createElement("code");
  command.className = "action-command";
  command.textContent = action.command;

  const summary = document.createElement("div");
  summary.className = "record-meta";
  summary.textContent = resultSummary(action);

  const controls = document.createElement("div");
  controls.className = "action-controls";
  if (action.id === "init") {
    const select = document.createElement("select");
    select.className = "select";
    select.ariaLabel = "Starter template";
    for (const template of action.templates || ["generic"]) {
      const option = document.createElement("option");
      option.value = template;
      option.textContent = template;
      select.append(option);
    }
    select.addEventListener("change", () => {
      command.textContent = (action.template_commands || {})[select.value] || action.command;
    });
    controls.append(select);
  }
  controls.append(actionButton(action));
  card.append(header, description, command, summary, controls);
  return card;
}

function renderSetup(snapshot, catalog) {
  const workspace = snapshot.workspace || {};
  const starter = workspace.starter_files || {};
  const actions = catalog && catalog.actions ? catalog.actions : [];
  el("setup-total").textContent = actions.length;
  el("setup-checklist").replaceChildren(
    setupRow("Workspace", workspace.exists ? "exists" : "missing", valueOrUnavailable(workspace.ops_dir)),
    setupRow(
      "Starter files",
      `${asNumber(starter.available_count)} of ${asNumber(starter.required_count)} available`,
      `${asNumber(starter.missing_count)} missing`
    ),
    ...actions
      .filter((action) => action.id !== "init")
      .map((action) => setupRow(action.label, resultSummary(action), action.command))
  );
  el("setup-actions").replaceChildren(...actions.map(actionCard));
}

function render(snapshot, actionsCatalog) {
  state.snapshot = snapshot;
  state.actions = actionsCatalog;
  el("workspace-path").textContent = snapshot.ops_dir || "research_ops";
  setBadge(snapshot.readiness);
  renderMetrics(snapshot);
  renderLifecycle(snapshot);
  renderDeliverables(snapshot);
  renderSetup(snapshot, actionsCatalog);
  renderTasks(snapshot);
  renderDecisions(snapshot);
  renderOutcomes(snapshot);
  renderPrompts(snapshot);
  renderSchedules(snapshot);
  renderFoundations(snapshot);
  renderOperations(snapshot);
  renderRuns(snapshot);
  renderWarnings(snapshot);
}

function renderError(error) {
  setBadge({ status: "unavailable" });
  const grid = el("dashboard");
  const card = metric("Snapshot", "unavailable", error.message || String(error));
  card.classList.add("error-state");
  grid.replaceChildren(card);
}

function showResult(result) {
  el("result-title").textContent = result.label || "Command Result";
  el("result-command").textContent = result.command || "unavailable";
  const exit = el("result-exit");
  exit.className = resultBadgeClass(result);
  exit.textContent = result.exit_code === undefined ? "unavailable" : `exit ${result.exit_code}`;
  el("result-next").textContent = result.next_step || result.message || "Review the command result.";
  el("result-stdout").textContent = result.stdout || "";
  el("result-stderr").textContent = result.stderr || "";
  const drawer = el("result-drawer");
  drawer.classList.add("open");
  drawer.setAttribute("aria-hidden", "false");
}

function closeResult() {
  const drawer = el("result-drawer");
  drawer.classList.remove("open");
  drawer.setAttribute("aria-hidden", "true");
}

async function postAction(payload) {
  const response = await fetch("/api/actions/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  return { response, result };
}

async function runAction(action) {
  if (state.runningAction) {
    return;
  }
  state.runningAction = action.id;
  renderSetup(state.snapshot || {}, state.actions || {});
  try {
    const payload = { action: action.id };
    if (action.id === "init") {
      const select = document.querySelector(".action-card select");
      payload.template = select && select.value ? select.value : "generic";
    }
    let { response, result } = await postAction(payload);
    if (response.status === 409 && result.reason === "confirmation_required") {
      const confirmed = window.confirm(`${result.command}\n\n${result.message}`);
      if (!confirmed) {
        showResult({
          label: action.label,
          command: result.command,
          exit_code: "cancelled",
          status: "failed",
          stdout: "",
          stderr: "",
          next_step: "Action cancelled before any command ran.",
        });
        return;
      }
      payload.confirm = result.confirmation_token;
      ({ response, result } = await postAction(payload));
    }
    state.results[action.id] = result;
    showResult(result);
    if (result.changed || action.id !== "init") {
      await refresh();
    }
  } catch (error) {
    showResult({
      label: action.label,
      command: action.command,
      exit_code: "unavailable",
      status: "failed",
      stdout: "",
      stderr: error.message || String(error),
      next_step: "Check that the local console server is still running.",
    });
  } finally {
    state.runningAction = null;
    renderSetup(state.snapshot || {}, state.actions || {});
  }
}

async function runTaskAction(action, task) {
  if (state.runningAction) {
    return;
  }
  state.runningAction = action.id;
  renderTasks(state.snapshot || {});
  try {
    const { result } = await postAction({ action: action.id, task_dir: task.task_dir });
    state.results[`${action.id}:${task.task_id}`] = result;
    showResult(result);
    await refresh();
  } catch (error) {
    showResult({
      label: action.label,
      command: action.command_template,
      exit_code: "unavailable",
      status: "failed",
      stdout: "",
      stderr: error.message || String(error),
      next_step: "Check that the local console server is still running.",
    });
  } finally {
    state.runningAction = null;
    renderTasks(state.snapshot || {});
  }
}

async function runDecisionAction(action, task, reason, approver) {
  if (state.runningAction) {
    return;
  }
  state.runningAction = action.id;
  renderDecisions(state.snapshot || {});
  try {
    const payload = {
      action: action.id,
      task_dir: task.task_dir,
      reason,
      approver,
      confirm: action.confirmation_token,
    };
    const { result } = await postAction(payload);
    state.results[`${action.id}:${task.task_id}`] = result;
    if (result.ok && approver) {
      window.localStorage.setItem("asyncResearchDecisionApprover", approver);
    }
    closeDecisionModal();
    showResult(result);
    await refresh();
  } catch (error) {
    showResult({
      label: action.label,
      command: action.command_template,
      exit_code: "unavailable",
      status: "failed",
      stdout: "",
      stderr: error.message || String(error),
      next_step: "Check that the local console server is still running.",
    });
  } finally {
    state.runningAction = null;
    renderDecisions(state.snapshot || {});
  }
}

function promptAction(id) {
  return (((state.actions || {}).prompt_actions || []).find((action) => action.id === id)) || { id, label: id };
}

function promptFormValues() {
  return {
    author: (el("prompt-author") || {}).value ? el("prompt-author").value.trim() : "human",
    reason: (el("prompt-reason") || {}).value ? el("prompt-reason").value.trim() : "",
    content: (el("prompt-editor") || {}).value || "",
    allowInvalid: Boolean((el("prompt-allow-invalid") || {}).checked),
  };
}

async function runPromptInit() {
  if (state.runningAction) {
    return;
  }
  const action = promptAction("prompts_init");
  state.runningAction = action.id;
  renderPrompts(state.snapshot || {});
  try {
    const { result } = await postAction({ action: action.id });
    state.results[action.id] = result;
    showResult(result);
    await refresh();
  } catch (error) {
    showResult({
      label: action.label,
      command: action.command_template,
      exit_code: "unavailable",
      status: "failed",
      stdout: "",
      stderr: error.message || String(error),
      next_step: "Check that the local console server is still running.",
    });
  } finally {
    state.runningAction = null;
    renderPrompts(state.snapshot || {});
  }
}

async function runPromptDraft(prompt) {
  if (state.runningAction) {
    return;
  }
  const values = promptFormValues();
  if (!values.reason || !values.content.trim()) {
    showResult({
      label: "Save Draft",
      command: "async-research prompts draft",
      exit_code: "unavailable",
      status: "failed",
      stdout: "",
      stderr: "",
      next_step: "Prompt draft content and reason are required.",
    });
    return;
  }
  const action = promptAction("prompt_save_draft");
  state.runningAction = action.id;
  renderPrompts(state.snapshot || {});
  try {
    const { result } = await postAction({
      action: action.id,
      prompt_id: prompt.prompt_id,
      content: values.content,
      reason: values.reason,
      author: values.author,
    });
    state.results[`${action.id}:${prompt.prompt_id}`] = result;
    if (result.ok && values.author) {
      window.localStorage.setItem("asyncResearchPromptAuthor", values.author);
    }
    showResult(result);
    await refresh();
  } catch (error) {
    showResult({
      label: action.label,
      command: action.command_template,
      exit_code: "unavailable",
      status: "failed",
      stdout: "",
      stderr: error.message || String(error),
      next_step: "Check that the local console server is still running.",
    });
  } finally {
    state.runningAction = null;
    renderPrompts(state.snapshot || {});
  }
}

async function runPromptActivate(prompt) {
  if (state.runningAction) {
    return;
  }
  const values = promptFormValues();
  if (!values.reason) {
    showResult({
      label: "Activate Draft",
      command: "async-research prompts activate",
      exit_code: "unavailable",
      status: "failed",
      stdout: "",
      stderr: "",
      next_step: "Activation reason is required.",
    });
    return;
  }
  const action = promptAction("prompt_activate");
  state.runningAction = action.id;
  renderPrompts(state.snapshot || {});
  try {
    const payload = {
      action: action.id,
      prompt_id: prompt.prompt_id,
      reason: values.reason,
      author: values.author,
      allow_invalid: values.allowInvalid,
    };
    let { response, result } = await postAction(payload);
    if (response.status === 409 && result.reason === "confirmation_required") {
      const confirmed = window.confirm(`${result.command}\n\n${result.message}`);
      if (!confirmed) {
        showResult({
          label: action.label,
          command: result.command,
          exit_code: "cancelled",
          status: "failed",
          stdout: "",
          stderr: "",
          next_step: "Prompt activation cancelled before files changed.",
        });
        return;
      }
      payload.confirm = result.confirmation_token;
      ({ result } = await postAction(payload));
    }
    state.results[`${action.id}:${prompt.prompt_id}`] = result;
    if (result.ok && values.author) {
      window.localStorage.setItem("asyncResearchPromptAuthor", values.author);
    }
    showResult(result);
    await refresh();
  } catch (error) {
    showResult({
      label: action.label,
      command: action.command_template,
      exit_code: "unavailable",
      status: "failed",
      stdout: "",
      stderr: error.message || String(error),
      next_step: "Check that the local console server is still running.",
    });
  } finally {
    state.runningAction = null;
    renderPrompts(state.snapshot || {});
  }
}

function scheduleAction(id) {
  return (((state.actions || {}).schedule_actions || []).find((action) => action.id === id)) || { id, label: id };
}

function scheduleFormValues() {
  return {
    jobId: (el("schedule-job-id") || {}).value ? el("schedule-job-id").value.trim() : "",
    description: (el("schedule-description") || {}).value ? el("schedule-description").value.trim() : "",
    status: (el("schedule-status") || {}).value || "disabled",
    cadence: (el("schedule-cadence") || {}).value ? el("schedule-cadence").value.trim() : "",
    promptId: (el("schedule-prompt-id") || {}).value ? el("schedule-prompt-id").value.trim() : "",
    promptVersion: (el("schedule-prompt-version") || {}).value ? el("schedule-prompt-version").value.trim() : "",
    maxRuntimeMinutes: Number((el("schedule-max-runtime") || {}).value || 0),
    concurrencyKey: (el("schedule-concurrency-key") || {}).value ? el("schedule-concurrency-key").value.trim() : "",
    concurrencyLimit: Number((el("schedule-concurrency-limit") || {}).value || 1),
    disabledReason: (el("schedule-disabled-reason") || {}).value ? el("schedule-disabled-reason").value.trim() : "",
    author: (el("schedule-author") || {}).value ? el("schedule-author").value.trim() : "human",
    reason: (el("schedule-reason") || {}).value ? el("schedule-reason").value.trim() : "",
  };
}

async function runScheduleInit() {
  if (state.runningAction) {
    return;
  }
  const action = scheduleAction("schedules_init");
  state.runningAction = action.id;
  renderSchedules(state.snapshot || {});
  try {
    const { result } = await postAction({ action: action.id });
    state.results[action.id] = result;
    showResult(result);
    await refresh();
  } catch (error) {
    showResult({
      label: action.label,
      command: action.command_template,
      exit_code: "unavailable",
      status: "failed",
      stdout: "",
      stderr: error.message || String(error),
      next_step: "Check that the local console server is still running.",
    });
  } finally {
    state.runningAction = null;
    renderSchedules(state.snapshot || {});
  }
}

async function runScheduleSave(job) {
  if (state.runningAction) {
    return;
  }
  const values = scheduleFormValues();
  if (!values.jobId || !values.reason || !values.description || !values.cadence || !values.promptId || !values.concurrencyKey) {
    showResult({
      label: "Save Schedule",
      command: "async-research schedules upsert",
      exit_code: "unavailable",
      status: "failed",
      stdout: "",
      stderr: "",
      next_step: "Job id, description, cadence, prompt, concurrency key, and reason are required.",
    });
    return;
  }
  const action = scheduleAction("schedule_save");
  state.runningAction = action.id;
  renderSchedules(state.snapshot || {});
  try {
    const { result } = await postAction({
      action: action.id,
      job_id: values.jobId,
      description: values.description,
      status: values.status,
      cadence: values.cadence,
      prompt_id: values.promptId,
      prompt_version: values.promptVersion,
      max_runtime_minutes: values.maxRuntimeMinutes,
      concurrency_key: values.concurrencyKey,
      concurrency_limit: values.concurrencyLimit,
      disabled_reason: values.disabledReason,
      reason: values.reason,
      author: values.author,
    });
    state.results[`${action.id}:${job.job_id}`] = result;
    if (result.ok && values.author) {
      window.localStorage.setItem("asyncResearchScheduleAuthor", values.author);
    }
    showResult(result);
    await refresh();
  } catch (error) {
    showResult({
      label: action.label,
      command: action.command_template,
      exit_code: "unavailable",
      status: "failed",
      stdout: "",
      stderr: error.message || String(error),
      next_step: "Check that the local console server is still running.",
    });
  } finally {
    state.runningAction = null;
    renderSchedules(state.snapshot || {});
  }
}

async function runScheduleTriggerDryRun(job) {
  if (state.runningAction) {
    return;
  }
  const values = scheduleFormValues();
  if (!values.jobId) {
    showResult({
      label: "Preview Trigger",
      command: "async-research schedules trigger-dry-run",
      exit_code: "unavailable",
      status: "failed",
      stdout: "",
      stderr: "",
      next_step: "Job id is required.",
    });
    return;
  }
  const action = scheduleAction("schedule_trigger_dry_run");
  state.runningAction = action.id;
  renderSchedules(state.snapshot || {});
  try {
    const { result } = await postAction({
      action: action.id,
      job_id: values.jobId,
    });
    state.results[`${action.id}:${job.job_id}`] = result;
    showResult(result);
  } catch (error) {
    showResult({
      label: action.label,
      command: action.command_template,
      exit_code: "unavailable",
      status: "failed",
      stdout: "",
      stderr: error.message || String(error),
      next_step: "Check that the local console server is still running.",
    });
  } finally {
    state.runningAction = null;
    renderSchedules(state.snapshot || {});
  }
}

async function runScheduleTriggerNow(job) {
  if (state.runningAction) {
    return;
  }
  const values = scheduleFormValues();
  if (!values.jobId) {
    showResult({
      label: "Run Now",
      command: "async-research schedules trigger-now",
      exit_code: "unavailable",
      status: "failed",
      stdout: "",
      stderr: "",
      next_step: "Job id is required.",
    });
    return;
  }
  const action = scheduleAction("schedule_trigger_now");
  state.runningAction = action.id;
  renderSchedules(state.snapshot || {});
  try {
    const payload = {
      action: action.id,
      job_id: values.jobId,
    };
    let { response, result } = await postAction(payload);
    if (response.status === 409 && result.reason === "confirmation_required") {
      const confirmed = window.confirm(`${result.command}\n\n${result.message}`);
      if (!confirmed) {
        showResult({
          label: action.label,
          command: result.command,
          exit_code: "cancelled",
          status: "failed",
          stdout: "",
          stderr: "",
          next_step: "Run cancelled before any process launched.",
        });
        return;
      }
      payload.confirm = result.confirmation_token;
      ({ result } = await postAction(payload));
    }
    state.results[`${action.id}:${job.job_id}`] = result;
    showResult(result);
    await refresh();
  } catch (error) {
    showResult({
      label: action.label,
      command: action.command_template,
      exit_code: "unavailable",
      status: "failed",
      stdout: "",
      stderr: error.message || String(error),
      next_step: "Check that the local console server is still running.",
    });
  } finally {
    state.runningAction = null;
    renderSchedules(state.snapshot || {});
  }
}

async function runScheduleStatus(actionId, job) {
  if (state.runningAction) {
    return;
  }
  const values = scheduleFormValues();
  if (!values.jobId || !values.reason) {
    showResult({
      label: actionId === "schedule_enable" ? "Enable Intent" : "Disable Intent",
      command: "async-research schedules set-status",
      exit_code: "unavailable",
      status: "failed",
      stdout: "",
      stderr: "",
      next_step: "Job id and reason are required.",
    });
    return;
  }
  const action = scheduleAction(actionId);
  state.runningAction = action.id;
  renderSchedules(state.snapshot || {});
  try {
    const { result } = await postAction({
      action: action.id,
      job_id: values.jobId,
      reason: values.reason,
      author: values.author,
      disabled_reason: values.disabledReason,
    });
    state.results[`${action.id}:${job.job_id}`] = result;
    if (result.ok && values.author) {
      window.localStorage.setItem("asyncResearchScheduleAuthor", values.author);
    }
    showResult(result);
    await refresh();
  } catch (error) {
    showResult({
      label: action.label,
      command: action.command_template,
      exit_code: "unavailable",
      status: "failed",
      stdout: "",
      stderr: error.message || String(error),
      next_step: "Check that the local console server is still running.",
    });
  } finally {
    state.runningAction = null;
    renderSchedules(state.snapshot || {});
  }
}

function submitDecisionForm(event) {
  event.preventDefault();
  const pending = state.pendingDecision;
  if (!pending) {
    return;
  }
  const reason = el("decision-reason").value.trim();
  const approver = el("decision-approver").value.trim();
  if (!reason || !approver) {
    el("decision-form-error").textContent = "Reason and approver are required.";
    return;
  }
  runDecisionAction(pending.action, pending.task, reason, approver);
}

async function refresh(options = {}) {
  if (state.loading) {
    return;
  }
  state.loading = true;
  const button = el("refresh-button");
  button.disabled = true;
  if (options.source === "auto") {
    setRefreshStatus("Refreshing");
  }
  try {
    const [snapshotResponse, actionsResponse] = await Promise.all([
      fetch("/api/snapshot", { cache: "no-store" }),
      fetch("/api/actions", { cache: "no-store" }),
    ]);
    if (!snapshotResponse.ok) {
      throw new Error(`snapshot request failed with ${snapshotResponse.status}`);
    }
    if (!actionsResponse.ok) {
      throw new Error(`actions request failed with ${actionsResponse.status}`);
    }
    render(await snapshotResponse.json(), await actionsResponse.json());
    setRefreshStatus(`Updated ${refreshTimeLabel(new Date())}`);
  } catch (error) {
    renderError(error);
    setRefreshStatus("Refresh failed");
  } finally {
    state.loading = false;
    button.disabled = false;
    updateAutoRefreshControls();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  el("refresh-button").addEventListener("click", refresh);
  el("auto-refresh-toggle").addEventListener("change", (event) => setAutoRefreshEnabled(event.target.checked));
  el("auto-refresh-interval").addEventListener("change", (event) => setAutoRefreshInterval(event.target.value));
  el("prompt-init").addEventListener("click", runPromptInit);
  el("schedule-init").addEventListener("click", runScheduleInit);
  el("result-close").addEventListener("click", closeResult);
  el("decision-cancel").addEventListener("click", closeDecisionModal);
  el("decision-form").addEventListener("submit", submitDecisionForm);
  updateAutoRefreshControls();
  scheduleAutoRefresh();
  refresh();
});
