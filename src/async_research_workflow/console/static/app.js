const state = {
  snapshot: null,
  actions: null,
  results: {},
  loading: false,
  runningAction: null,
  taskFilter: "all",
  selectedTaskId: null,
  outcomeFilter: "all",
  selectedProjectId: null,
  selectedPromptId: null,
  selectedScheduleId: null,
  pendingDecision: null,
};

const el = (id) => document.getElementById(id);

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
  const rejected = snapshot.rejected_results || {};
  const cost = snapshot.cost || {};
  const readiness = snapshot.readiness || {};
  const health = snapshot.health || {};
  const warnings = snapshot.warnings || [];
  const grid = el("dashboard");
  grid.replaceChildren(
    metric("Readiness", statusLabel(readiness.verdict || readiness.status), readiness.next_step),
    metric("Health", statusLabel(health.verdict || health.status), health.next_step),
    metric("Active tasks", (tasks.active || []).length, `${asNumber(tasks.total)} total tasks`),
    metric("Blocked tasks", (tasks.blocked || []).length, `${asNumber(decisions.open_count)} human decisions`),
    metric("Delivered projects", asNumber((delivered.summary || {}).project_count || accepted.count), `${asNumber((delivered.summary || {}).accepted_count)} accepted outputs`),
    metric("Rejected results", asNumber(rejected.count), "recent rejected ledger rows"),
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

function detailPathLink(file) {
  const link = document.createElement("a");
  link.className = file.exists ? "file-link" : "file-link missing";
  link.href = `file://${file.path}`;
  link.target = "_blank";
  link.rel = "noreferrer";
  link.textContent = `${file.label}: ${file.path}${file.exists ? "" : " (missing)"}`;
  return link;
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
  card.append(title, reason, options, controls);
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

  panel.replaceChildren(title, fields, files, actionRow);
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
  const disable = document.createElement("button");
  disable.className = "button secondary";
  disable.type = "button";
  disable.textContent = state.runningAction === "schedule_disable" ? "Disabling" : "Disable Intent";
  disable.disabled = Boolean(state.runningAction);
  disable.addEventListener("click", () => runScheduleStatus("schedule_disable", job));
  controls.append(save, enable, disable);

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

function renderFoundations(snapshot) {
  el("foundation-cards").replaceChildren(
    foundationCard("Ideas", snapshot.ideas, ["candidate_count", "failure_count", "warning_count"]),
    foundationCard("Data", snapshot.data, ["source_count", "data_gap_count", "validator_warning_count"]),
    foundationCard("Library", snapshot.library, ["source_count", "claim_count", "validator_warning_count"]),
    foundationCard("Analysis", snapshot.analysis, ["active_run_analysis_count", "preflight_blocked_count", "revalidation_needed_count"])
  );
}

function renderRuns(snapshot) {
  const runs = snapshot.runs || {};
  el("run-total").textContent = runs.count || 0;
  renderList("recent-runs", runs.recent_runs, "No run artifacts.", (run) =>
    record(
      `${valueOrUnavailable(run.run_id)} - ${valueOrUnavailable(run.status)}`,
      `${valueOrUnavailable(run.task_id)} / ${valueOrUnavailable(run.job_id)}`,
      `${valueOrUnavailable(run.started_at)} -> ${valueOrUnavailable(run.finished_at)}`
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
  renderSetup(snapshot, actionsCatalog);
  renderTasks(snapshot);
  renderDecisions(snapshot);
  renderOutcomes(snapshot);
  renderPrompts(snapshot);
  renderSchedules(snapshot);
  renderFoundations(snapshot);
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

async function refresh() {
  if (state.loading) {
    return;
  }
  state.loading = true;
  const button = el("refresh-button");
  button.disabled = true;
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
  } catch (error) {
    renderError(error);
  } finally {
    state.loading = false;
    button.disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  el("refresh-button").addEventListener("click", refresh);
  el("prompt-init").addEventListener("click", runPromptInit);
  el("schedule-init").addEventListener("click", runScheduleInit);
  el("result-close").addEventListener("click", closeResult);
  el("decision-cancel").addEventListener("click", closeDecisionModal);
  el("decision-form").addEventListener("submit", submitDecisionForm);
  refresh();
});
