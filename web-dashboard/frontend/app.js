const state = {
  summary: null,
  todayRecords: [],
  attendanceRecords: [],
  employees: [],
  logs: [],
  rules: null,
  latestDetection: null,
};

const refreshLabel = document.getElementById("last-refresh");
const pageTitle = document.getElementById("page-title");
const modal = document.getElementById("employee-modal");
const modalTitle = document.getElementById("modal-title");
const modalContent = document.getElementById("modal-content");

document.querySelectorAll(".nav-link").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.view));
});

document.getElementById("attendance-filters").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  state.attendanceRecords = (await api(`/api/attendance/history?${new URLSearchParams(form)}`)).records;
  renderAttendanceTable();
});

document.getElementById("employee-filters").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  state.employees = (await api(`/api/employees?${new URLSearchParams(form)}`)).employees;
  renderEmployees();
});

document.getElementById("log-filters").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  state.logs = (await api(`/api/logs?${new URLSearchParams(form)}`)).logs;
  renderLogs();
});

document.getElementById("modal-close").addEventListener("click", () => modal.close());
modal.addEventListener("click", (event) => {
  if (event.target === modal) {
    modal.close();
  }
});

async function boot() {
  await refreshAll();
  setInterval(refreshAll, 5000);
}

async function refreshAll() {
  const [summaryResponse, todayResponse, attendanceResponse, employeesResponse, logsResponse, latestResponse, rulesResponse] = await Promise.all([
    api("/api/dashboard/summary"),
    api("/api/attendance/today"),
    api("/api/attendance/history"),
    api("/api/employees"),
    api("/api/logs"),
    api("/api/latest-detection"),
    api("/api/status-rules"),
  ]);

  state.summary = summaryResponse.summary;
  state.todayRecords = todayResponse.records;
  state.attendanceRecords = attendanceResponse.records;
  state.employees = employeesResponse.employees;
  state.logs = logsResponse.logs;
  state.latestDetection = latestResponse.latest_detection;
  state.rules = rulesResponse;

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

async function api(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Request failed: ${path}`);
  }
  return response.json();
}

function setView(viewName) {
  document.querySelectorAll(".nav-link").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === viewName);
  });
  document.querySelectorAll(".view").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.viewPanel === viewName);
  });
  pageTitle.textContent = document.querySelector(`.nav-link[data-view="${viewName}"] span:last-child`).textContent;
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
      <p class="label">${label}</p>
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
    <p class="identity">${latest.employee_name}</p>
    <div class="metric-grid">
      <div class="metric">
        <div class="label">Timestamp</div>
        <div class="value">${formatDateTime(latest.timestamp)}</div>
      </div>
      <div class="metric">
        <div class="label">Event Type</div>
        <div class="value">${latest.event_type}</div>
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
        <strong class="stack-item-title">${event.employee_name}</strong>
        ${badge(event.status, event.status_group)}
      </div>
      <p class="stack-item-meta">${formatDateTime(event.timestamp)} &middot; ${event.event_type}</p>
    </article>
  `).join("") : `<div class="empty-state">No recent detections available.</div>`;
}

function renderTodayAttendance() {
  renderAttendanceRows(document.getElementById("today-attendance-body"), state.todayRecords);
}

function renderAttendanceTable() {
  renderAttendanceRows(document.getElementById("attendance-body"), state.attendanceRecords);
}

function renderAttendanceRows(tbody, records) {
  tbody.innerHTML = records.length ? records.map((record) => `
    <tr>
      <td class="cell-compact">${record.employee_id ?? "&mdash;"}</td>
      <td class="record-name-cell">
        <span class="record-name">${record.employee_name}</span>
        <span class="subtle">${record.event_type}</span>
      </td>
      <td class="cell-compact">${record.date}</td>
      <td class="cell-compact">${record.entry_time ?? "&mdash;"}</td>
      <td class="cell-compact">${record.exit_time ?? "&mdash;"}</td>
      <td>${badge(record.current_status, statusGroupFromText(record.current_status))}</td>
      <td class="cell-compact">${record.event_type}</td>
      <td>${record.notes.length ? record.notes.join(", ") : "&mdash;"}</td>
    </tr>
  `).join("") : `
    <tr>
      <td colspan="8"><div class="empty-state">No attendance records matched the current filters.</div></td>
    </tr>
  `;
}

function renderEmployees() {
  const tbody = document.getElementById("employees-body");
  tbody.innerHTML = state.employees.length ? state.employees.map((employee) => `
    <tr>
      <td class="cell-compact">${employee.id}</td>
      <td class="record-name-cell">
        <span class="employee-name">${employee.name}</span>
        <span class="subtle">Registered identity profile</span>
      </td>
      <td class="cell-compact">${employee.face_registered ? "Yes" : "No"}</td>
      <td class="record-meta">${employee.last_seen ? formatDateTime(employee.last_seen) : "Never logged"}</td>
      <td>${badge(employee.current_status, statusGroupFromText(employee.current_status))}</td>
      <td><button class="details-button" data-employee-id="${employee.id}">Open</button></td>
    </tr>
  `).join("") : `
    <tr>
      <td colspan="6"><div class="empty-state">No registered employees matched the current filters.</div></td>
    </tr>
  `;

  tbody.querySelectorAll(".details-button").forEach((button) => {
    button.addEventListener("click", async () => openEmployeeModal(button.dataset.employeeId));
  });
}

async function openEmployeeModal(employeeId) {
  const response = await api(`/api/employees/${employeeId}`);
  const employee = response.employee;
  modalTitle.textContent = employee.name;

  const history = employee.history || [];
  modalContent.innerHTML = `
    <div class="detail-grid">
      <div class="detail-card">
        <div class="detail-label">Latest Attendance State</div>
        <div class="detail-value">${employee.latest_attendance_state}</div>
      </div>
      <div class="detail-card">
        <div class="detail-label">Latest Event</div>
        <div class="detail-value">${employee.latest_event ? employee.latest_event.status : "No events yet"}</div>
      </div>
      <div class="detail-card">
        <div class="detail-label">Late History</div>
        <div class="detail-value">${employee.late_history_count}</div>
      </div>
      <div class="detail-card">
        <div class="detail-label">Overtime History</div>
        <div class="detail-value">${employee.overtime_history_count}</div>
      </div>
    </div>
    <section class="panel">
      <div class="panel-header">
        <div>
          <p class="eyebrow">Attendance History</p>
          <h3>${employee.name}</h3>
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
                <td>${record.date}</td>
                <td>${record.entry_time ?? "&mdash;"}</td>
                <td>${record.exit_time ?? "&mdash;"}</td>
                <td>${badge(record.current_status, statusGroupFromText(record.current_status))}</td>
                <td>${record.notes.length ? record.notes.join(", ") : "&mdash;"}</td>
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

function renderLogs() {
  const container = document.getElementById("log-list");
  container.innerHTML = state.logs.length ? state.logs.map((log, index) => `
    <article class="log-item${index === 0 ? " recent" : ""}">
      <div class="log-item-header">
        <strong class="employee-name">${log.employee_name ?? "Unknown line"}</strong>
        ${badge(log.status, log.status_group)}
      </div>
      <p class="timestamp">${log.timestamp ? formatDateTime(log.timestamp) : "No timestamp"} &middot; ${log.event_type}</p>
      <p class="log-item-body">${log.raw}</p>
      ${index === 0 ? '<span class="log-recent-label">Most Recent Activity</span>' : ""}
    </article>
  `).join("") : `<div class="empty-state">No log entries matched the current filters.</div>`;
}

function renderRules() {
  const container = document.getElementById("rules-panel");
  if (!state.rules) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML = state.rules.rules.map((rule) => `
    <article class="rule-card">
      <p class="eyebrow">${rule.name}</p>
      <p class="rule-time">${rule.time}</p>
      <p>${rule.description}</p>
    </article>
  `).join("") + `
    <article class="rule-card">
      <p class="eyebrow">Source Paths</p>
      <p class="rule-time">Live Local Files</p>
      <p class="muted">Database: ${state.rules.database_path}</p>
      <p class="muted">Logs: ${state.rules.log_path}</p>
      <p class="muted">Rules source: ${state.rules.source}</p>
    </article>
  `;
}

function badge(label, group) {
  return `<span class="badge ${group || "neutral"}">${label}</span>`;
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

boot().catch((error) => {
  refreshLabel.textContent = "Dashboard failed to load";
  console.error(error);
});
