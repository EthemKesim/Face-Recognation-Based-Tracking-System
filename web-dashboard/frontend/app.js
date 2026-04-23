const state = {
  summary: null,
  todayRecords: [],
  attendanceRecords: [],
  employees: [],
  logs: [],
  rules: null,
  latestDetection: null,
  session: null,
  deletingEmployeeId: null,
  activeView: "dashboard",
  filters: {
    attendance: "",
    employees: "",
    logs: "",
  },
};

const VIEW_META = {
  dashboard: "Professional admin view for your live face recognition attendance data.",
  attendance: "Search and review structured attendance history without affecting live monitoring data.",
  employees: "Inspect registered identities, current attendance state, and available employee actions.",
  logs: "Review the latest parsed recognition events with focused search and event filters.",
  rules: "Reference the attendance timing rules currently mirrored from the local Python system.",
};

const refreshLabel = document.getElementById("last-refresh");
const pageTitle = document.getElementById("page-title");
const topbarSubtitle = document.getElementById("topbar-subtitle");
const modal = document.getElementById("employee-modal");
const modalTitle = document.getElementById("modal-title");
const modalContent = document.getElementById("modal-content");
const feedbackBanner = document.getElementById("feedback-banner");
const logoutButton = document.getElementById("logout-button");
const sessionUser = document.getElementById("session-user");
const confirmDialog = document.getElementById("confirm-dialog");
const confirmTitle = document.getElementById("confirm-title");
const confirmMessage = document.getElementById("confirm-message");
const confirmCancel = document.getElementById("confirm-cancel");
const confirmAccept = document.getElementById("confirm-accept");
const attendanceFiltersForm = document.getElementById("attendance-filters");
const employeeFiltersForm = document.getElementById("employee-filters");
const logFiltersForm = document.getElementById("log-filters");
let confirmResolver = null;

document.querySelectorAll(".nav-link").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.view));
});

attendanceFiltersForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  state.filters.attendance = buildQueryString(new FormData(event.currentTarget));
  await loadAttendanceRecords();
});

employeeFiltersForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  state.filters.employees = buildQueryString(new FormData(event.currentTarget));
  await loadEmployees();
});

logFiltersForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  state.filters.logs = buildQueryString(new FormData(event.currentTarget));
  await loadLogs();
});

document.getElementById("modal-close").addEventListener("click", () => modal.close());
modal.addEventListener("click", (event) => {
  if (event.target === modal) {
    modal.close();
  }
});

confirmCancel.addEventListener("click", () => confirmDialog.close("cancel"));
confirmAccept.addEventListener("click", () => confirmDialog.close("confirm"));
confirmDialog.addEventListener("click", (event) => {
  if (event.target === confirmDialog) {
    confirmDialog.close("cancel");
  }
});
confirmDialog.addEventListener("close", () => {
  if (confirmResolver) {
    confirmResolver(confirmDialog.returnValue === "confirm");
    confirmResolver = null;
  }
});

logoutButton.addEventListener("click", async () => {
  logoutButton.disabled = true;
  try {
    await api("/api/auth/logout", { method: "POST", skipRedirectOnUnauthorized: true });
  } finally {
    window.location.href = "/login";
  }
});

async function boot() {
  await loadSession();
  setView(state.activeView);
  await refreshAll();
  setInterval(() => {
    refreshAll().catch((error) => {
      refreshLabel.textContent = "Refresh failed";
      setFeedback("error", error.message);
    });
  }, 5000);
}

async function loadSession() {
  const session = await api("/api/auth/session", { skipRedirectOnUnauthorized: true });
  if (!session.authenticated) {
    window.location.href = "/login";
    throw new Error("Authentication required.");
  }

  state.session = session;
  renderSession();
}

async function refreshAll() {
  const [summaryResponse, todayResponse, latestResponse, rulesResponse] = await Promise.all([
    api("/api/dashboard/summary"),
    api("/api/attendance/today"),
    api("/api/latest-detection"),
    api("/api/status-rules"),
  ]);

  state.summary = summaryResponse.summary;
  state.todayRecords = todayResponse.records;
  state.latestDetection = latestResponse.latest_detection;
  state.rules = rulesResponse;

  await Promise.all([loadAttendanceRecords(), loadEmployees(), loadLogs()]);

  renderSummary();
  renderLatestDetection();
  renderRecentDetections();
  renderTodayAttendance();
  renderAttendanceTable();
  renderEmployees();
  renderLogs();
  renderRules();
  refreshLabel.textContent = `Last updated ${new Date().toLocaleString()}`;
}

async function loadAttendanceRecords() {
  const response = await api(withQuery("/api/attendance/history", state.filters.attendance));
  state.attendanceRecords = response.records;
  renderAttendanceTable();
}

async function loadEmployees() {
  const response = await api(withQuery("/api/employees", state.filters.employees));
  state.employees = response.employees;
  renderEmployees();
}

async function loadLogs() {
  const response = await api(withQuery("/api/logs", state.filters.logs));
  state.logs = response.logs;
  renderLogs();
}

async function api(path, options = {}) {
  const { skipRedirectOnUnauthorized = false, headers = {}, ...fetchOptions } = options;
  const response = await fetch(path, {
    cache: "no-store",
    ...fetchOptions,
    headers: {
      ...headers,
    },
  });

  let payload = {};
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    payload = await response.json();
  }

  if (response.status === 401 && !skipRedirectOnUnauthorized) {
    window.location.href = "/login";
    throw new Error(payload.error || "Authentication required.");
  }

  if (response.status === 401 && skipRedirectOnUnauthorized) {
    return payload;
  }

  if (!response.ok) {
    throw new Error(payload.error || `Request failed: ${path}`);
  }

  return payload;
}

function renderSession() {
  sessionUser.textContent = state.session?.username
    ? `Logged in as ${state.session.username}`
    : "Not signed in";
}

function setView(viewName) {
  state.activeView = viewName;

  document.querySelectorAll(".nav-link").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === viewName);
  });
  document.querySelectorAll(".view").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.viewPanel === viewName);
  });

  pageTitle.textContent = document.querySelector(`.nav-link[data-view="${viewName}"] span:last-child`).textContent;
  topbarSubtitle.textContent = VIEW_META[viewName] || VIEW_META.dashboard;
}

function renderSummary() {
  const container = document.getElementById("summary-cards");
  if (!state.summary) {
    container.innerHTML = "";
    return;
  }

  const cards = [
    ["Total Registered Employees", state.summary.total_registered_employees],
    ["Present Today", state.summary.present_today],
    ["Late Today", state.summary.late_today],
    ["Checked Out Today", state.summary.checked_out_today],
    ["Overtime Employees", state.summary.overtime_employees],
  ];

  container.innerHTML = cards.map(([label, value]) => `
    <article class="summary-card">
      <p class="label">${escapeHtml(label)}</p>
      <p class="value">${value}</p>
      <p class="meta">Live data mirrored from the local attendance source.</p>
    </article>
  `).join("");
}

function renderLatestDetection() {
  const container = document.getElementById("latest-detection");
  const latest = state.latestDetection;

  if (!latest) {
    container.innerHTML = `
      <div class="empty-state">
        No recognition events have been logged yet. Start your existing Python recognition script and this panel will update automatically.
      </div>
    `;
    return;
  }

  container.innerHTML = `
    <p class="eyebrow">Latest Detected Employee</p>
    <p class="identity">${escapeHtml(latest.employee_name)}</p>
    <div class="metric-grid">
      <div class="metric">
        <div class="label">Timestamp</div>
        <div class="value">${formatDateTime(latest.timestamp)}</div>
      </div>
      <div class="metric">
        <div class="label">Event Type</div>
        <div class="value">${escapeHtml(latest.event_type)}</div>
      </div>
      <div class="metric">
        <div class="label">Status</div>
        <div class="value">${badge(latest.status, latest.status_group)}</div>
      </div>
      <div class="metric">
        <div class="label">Camera Integration</div>
        <div class="value muted">Live event mirror from Python logs</div>
      </div>
    </div>
  `;
}

function renderRecentDetections() {
  const container = document.getElementById("recent-detections");
  const detections = state.summary?.recent_detections || [];
  container.innerHTML = detections.length ? detections.map((event) => `
    <article class="stack-item">
      <div class="stack-item-header">
        <strong class="stack-item-title">${escapeHtml(event.employee_name)}</strong>
        ${badge(event.status, event.status_group)}
      </div>
      <p class="stack-item-meta">${formatDateTime(event.timestamp)} &middot; ${escapeHtml(event.event_type)}</p>
    </article>
  `).join("") : `<div class="empty-state">No recent detections available.</div>`;
}

function renderTodayAttendance() {
  renderAttendanceRows(
    document.getElementById("today-attendance-body"),
    state.todayRecords,
    "No attendance records have been logged for today yet. This snapshot only shows records dated today, while the live panels can still show the latest historical detection."
  );
}

function renderAttendanceTable() {
  renderAttendanceRows(
    document.getElementById("attendance-body"),
    state.attendanceRecords,
    "No attendance records matched the current filters."
  );
}

function renderAttendanceRows(tbody, records, emptyMessage) {
  tbody.innerHTML = records.length ? records.map((record) => `
    <tr>
      <td class="cell-compact">${record.employee_id ?? "&mdash;"}</td>
      <td class="record-name-cell">
        <span class="record-name">${escapeHtml(record.employee_name)}</span>
        <span class="subtle">${escapeHtml(record.event_type)}</span>
      </td>
      <td class="cell-compact">${escapeHtml(record.date)}</td>
      <td class="cell-compact">${record.entry_time ?? "&mdash;"}</td>
      <td class="cell-compact">${record.exit_time ?? "&mdash;"}</td>
      <td>${badge(record.current_status, statusGroupFromText(record.current_status))}</td>
      <td class="cell-compact">${escapeHtml(record.event_type)}</td>
      <td>${record.notes.length ? record.notes.map(escapeHtml).join(", ") : "&mdash;"}</td>
    </tr>
  `).join("") : `
    <tr>
      <td colspan="8"><div class="empty-state">${escapeHtml(emptyMessage)}</div></td>
    </tr>
  `;
}

function renderEmployees() {
  const tbody = document.getElementById("employees-body");
  tbody.innerHTML = state.employees.length ? state.employees.map((employee) => {
    const isDeleting = state.deletingEmployeeId === employee.id;
    return `
      <tr>
        <td class="cell-compact">${employee.id}</td>
        <td class="record-name-cell">
          <span class="employee-name">${escapeHtml(employee.name)}</span>
          <span class="subtle">Registered identity profile</span>
        </td>
        <td class="cell-compact">${employee.face_registered ? "Yes" : "No"}</td>
        <td class="record-meta">${employee.last_seen ? formatDateTime(employee.last_seen) : "Never logged"}</td>
        <td>${badge(employee.current_status, statusGroupFromText(employee.current_status))}</td>
        <td>
          <div class="action-group">
            <button class="details-button" data-employee-id="${employee.id}" ${isDeleting ? "disabled" : ""}>Open</button>
            <button
              class="danger-button delete-button"
              data-employee-id="${employee.id}"
              data-employee-name="${escapeHtml(employee.name)}"
              ${isDeleting ? "disabled" : ""}
            >
              ${isDeleting ? "Deleting..." : "Delete"}
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join("") : `
    <tr>
      <td colspan="6"><div class="empty-state">No registered employees matched the current filters.</div></td>
    </tr>
  `;

  tbody.querySelectorAll(".details-button").forEach((button) => {
    button.addEventListener("click", async () => openEmployeeModal(button.dataset.employeeId));
  });

  tbody.querySelectorAll(".delete-button").forEach((button) => {
    button.addEventListener("click", async () => {
      await handleDeleteEmployee(button.dataset.employeeId, button.dataset.employeeName);
    });
  });
}

async function openEmployeeModal(employeeId) {
  const response = await api(`/api/employees/${employeeId}`);
  const employee = response.employee;
  modal.dataset.employeeId = String(employee.id);
  modalTitle.textContent = employee.name;

  const history = employee.history || [];
  modalContent.innerHTML = `
    <div class="detail-grid detail-metrics-grid">
      <div class="detail-card">
        <div class="detail-label">Latest Attendance State</div>
        <div class="detail-value">${escapeHtml(employee.latest_attendance_state)}</div>
        <p class="detail-note">Most recent structured status for this employee.</p>
      </div>
      <div class="detail-card">
        <div class="detail-label">Latest Event</div>
        <div class="detail-value">${employee.latest_event ? escapeHtml(employee.latest_event.status) : "No events yet"}</div>
        <p class="detail-note">Latest parsed recognition event from the activity log.</p>
      </div>
      <div class="detail-card">
        <div class="detail-label">Late History</div>
        <div class="detail-value">${employee.late_history_count}</div>
        <p class="detail-note">Attendance events flagged as late.</p>
      </div>
      <div class="detail-card">
        <div class="detail-label">Overtime History</div>
        <div class="detail-value">${employee.overtime_history_count}</div>
        <p class="detail-note">Recorded overtime check-out events.</p>
      </div>
    </div>
    <section class="panel">
      <div class="panel-header">
        <div>
          <p class="eyebrow">Recorded Events</p>
          <h3>Attendance History</h3>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Entry Time</th>
              <th>Exit Time</th>
              <th>Current Status</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            ${history.length ? history.map((record) => `
              <tr>
                <td>${escapeHtml(record.date)}</td>
                <td>${record.entry_time ?? "&mdash;"}</td>
                <td>${record.exit_time ?? "&mdash;"}</td>
                <td>${badge(record.current_status, statusGroupFromText(record.current_status))}</td>
                <td>${record.notes.length ? record.notes.map(escapeHtml).join(", ") : "&mdash;"}</td>
              </tr>
            `).join("") : `
              <tr><td colspan="5"><div class="empty-state">No attendance history available.</div></td></tr>
            `}
          </tbody>
        </table>
      </div>
    </section>
  `;

  modal.showModal();
}

async function handleDeleteEmployee(employeeId, employeeName) {
  const normalizedId = Number(employeeId);
  if (!Number.isInteger(normalizedId)) {
    setFeedback("error", "Employee id is invalid.");
    return;
  }

  const confirmed = await confirmAction({
    title: "Are you sure you want to delete this employee?",
    message: `${employeeName} will be removed from the employee list, face encoding records, and stored attendance history.`,
    confirmLabel: "Delete Employee",
  });
  if (!confirmed) {
    return;
  }

  state.deletingEmployeeId = normalizedId;
  renderEmployees();

  try {
    const response = await api(`/api/employees/${normalizedId}`, { method: "DELETE" });
    if (modal.open && modal.dataset.employeeId === String(normalizedId)) {
      modal.close();
    }
    await refreshAll();
    const feedbackMessage = response.warning
      ? `${response.message} ${response.warning}`
      : response.message;
    setFeedback(response.warning ? "info" : "success", feedbackMessage);
  } catch (error) {
    setFeedback("error", error.message);
  } finally {
    state.deletingEmployeeId = null;
    renderEmployees();
  }
}

function renderLogs() {
  const container = document.getElementById("log-list");
  container.innerHTML = state.logs.length ? state.logs.map((log, index) => {
    const hasParsedData = Boolean(log.employee_name && log.timestamp);
    const supportingText = log.notes?.length
      ? escapeHtml(log.notes.join(" • "))
      : hasParsedData
      ? escapeHtml(log.status)
      : escapeHtml(log.raw || "No log data available.");

    return `
      <article class="log-item${index === 0 ? " recent" : ""}">
        <div class="log-item-header">
          <strong class="employee-name">${escapeHtml(log.employee_name ?? "Unknown line")}</strong>
          ${badge(log.status, log.status_group)}
        </div>
        <p class="timestamp">${log.timestamp ? formatDateTime(log.timestamp) : "No timestamp"} &middot; ${escapeHtml(log.event_type)}</p>
        <p class="log-item-body">${supportingText}</p>
        ${index === 0 ? '<span class="log-recent-label">Most Recent Activity</span>' : ""}
      </article>
    `;
  }).join("") : `<div class="empty-state">No log entries matched the current filters.</div>`;
}

function renderRules() {
  const container = document.getElementById("rules-panel");
  if (!state.rules) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML = state.rules.rules.map((rule) => `
    <article class="rule-card">
      <p class="eyebrow">${escapeHtml(rule.name)}</p>
      <p class="rule-time">${escapeHtml(rule.time)}</p>
      <p>${escapeHtml(rule.description)}</p>
    </article>
  `).join("") + `
    <article class="rule-card source-paths-card">
      <p class="eyebrow">Source Paths</p>
      <p class="rule-time">Live Local Files</p>
      <p class="muted">${escapeHtml(state.rules.database_path)}</p>
      <p class="muted">${escapeHtml(state.rules.log_path)}</p>
      <p class="muted">${escapeHtml(state.rules.source)}</p>
    </article>
  `;
}

function setFeedback(type, message) {
  if (!message) {
    feedbackBanner.className = "feedback-banner";
    feedbackBanner.textContent = "";
    return;
  }

  feedbackBanner.className = `feedback-banner ${type} show`;
  feedbackBanner.textContent = message;
}

function confirmAction({ title, message, confirmLabel }) {
  confirmTitle.textContent = title;
  confirmMessage.textContent = message;
  confirmAccept.textContent = confirmLabel;
  confirmDialog.returnValue = "";

  if (confirmDialog.open) {
    confirmDialog.close("cancel");
  }

  confirmDialog.showModal();
  return new Promise((resolve) => {
    confirmResolver = resolve;
  });
}

function badge(label, group) {
  return `<span class="badge ${group || "neutral"}">${escapeHtml(label)}</span>`;
}

function statusGroupFromText(text) {
  const value = (text || "").toLowerCase();
  if (value.includes("late") || value.includes("warning") || value.includes("violation")) return "late";
  if (value.includes("lunch")) return "lunch";
  if (value.includes("overtime")) return "overtime";
  if (value.includes("checked out") || value.includes("check-out")) return "checkout";
  if (value.includes("still inside") || value.includes("check-in") || value.includes("present")) return "checkin";
  return "neutral";
}

function formatDateTime(value) {
  if (!value) return "&mdash;";
  const date = new Date(value);
  return date.toLocaleString();
}

function buildQueryString(formData) {
  const params = new URLSearchParams();
  for (const [key, value] of formData.entries()) {
    const normalizedValue = String(value).trim();
    if (normalizedValue) {
      params.set(key, normalizedValue);
    }
  }
  return params.toString();
}

function withQuery(path, queryString) {
  return queryString ? `${path}?${queryString}` : path;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("\"", "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

boot().catch((error) => {
  refreshLabel.textContent = "Dashboard failed to load";
  setFeedback("error", error.message);
  console.error(error);
});
