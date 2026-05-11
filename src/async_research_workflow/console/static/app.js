const state = {
  snapshot: null,
  actions: null,
  results: {},
  loading: false,
  runningAction: null,
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
    metric("Accepted outputs", asNumber(accepted.count), "delivered memory rows"),
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

function renderTasks(snapshot) {
  const tasks = snapshot.tasks || {};
  el("task-total").textContent = asNumber(tasks.total);
  renderList("active-tasks", tasks.active, "No active tasks.", (task) =>
    record(
      `${valueOrUnavailable(task.task_id)} - ${valueOrUnavailable(task.title)}`,
      `${valueOrUnavailable(task.status)} / ${valueOrUnavailable(task.type)}`,
      `updated: ${valueOrUnavailable(task.last_transition_reason)}`
    )
  );
  renderList("blocked-tasks", tasks.blocked, "No blocked tasks.", (task) =>
    record(
      `${valueOrUnavailable(task.task_id)} - ${valueOrUnavailable(task.title)}`,
      `${valueOrUnavailable(task.status)} / ${valueOrUnavailable(task.type)}`,
      valueOrUnavailable(task.human_gate_reason || task.last_transition_reason)
    )
  );
}

function renderDecisions(snapshot) {
  const decisions = snapshot.human_decisions || {};
  el("decision-total").textContent = asNumber(decisions.open_count);
  renderList("human-decisions", decisions.blocked_task_refs, "No open human decisions.", (task) =>
    record(
      `${valueOrUnavailable(task.task_id)} - ${valueOrUnavailable(task.title)}`,
      valueOrUnavailable(task.human_gate_reason),
      valueOrUnavailable(task.status_path)
    )
  );
}

function renderOutcomes(snapshot) {
  const accepted = (snapshot.accepted_outputs || {}).recent_rows || [];
  const rejected = (snapshot.rejected_results || {}).recent_rows || [];
  renderList("accepted-outputs", accepted, "No accepted outputs.", (row) =>
    record(
      `${valueOrUnavailable(row.task_id)} - ${valueOrUnavailable(row.title)}`,
      valueOrUnavailable(row.key_finding || row.claim_type),
      valueOrUnavailable(row.evidence_link)
    )
  );
  renderList("rejected-results", rejected, "No rejected results.", (row) =>
    record(
      `${valueOrUnavailable(row.task_id)} - ${valueOrUnavailable(row.route)}`,
      valueOrUnavailable(row.reason),
      valueOrUnavailable(row.evidence_link)
    )
  );
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
  el("result-close").addEventListener("click", closeResult);
  refresh();
});
