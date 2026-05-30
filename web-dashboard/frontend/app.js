const state = {
  summary: null,
  todayRecords: [],
  attendanceRecords: [],
  employees: [],
  logs: [],
  latestDetection: null,
  station: null,
  testTime: null,
  session: null,
  deletingEmployeeId: null,
  editingEmployeeId: null,
  unknownFaces: [],
  admins: [],
  adminLogs: [],
  attendanceRules: null,
  activeView: "dashboard",
  filters: {
    attendance: "",
    employees: "",
    logs: "",
  },
};

const VIEW_META = {
  dashboard: "",
  attendance: "",
  employees: "",
  logs: "",
  reports: "",
  "unknown-faces": "",
  "admin-logs": "",
  settings: "",
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
const adminCreateForm = document.getElementById("admin-create-form");
const adminCreateFeedback = document.getElementById("admin-create-feedback");
const stationStartButton = document.getElementById("station-start-btn");
const stationStopButton = document.getElementById("station-stop-btn");
const clearTestTimeButton = document.getElementById("clear-test-time-btn");
const globalSearchInput = document.getElementById("global-search");
const sidebarStartRecognitionButton = document.getElementById("sidebar-start-recognition");
const editEmployeeModal = document.getElementById("edit-employee-modal");
const editModalTitle = document.getElementById("edit-modal-title");
const editModalClose = document.getElementById("edit-modal-close");
const editNameInput = document.getElementById("edit-name");
const editDepartmentInput = document.getElementById("edit-department");
const editStatusSelect = document.getElementById("edit-status");
const editSubmitBtn = document.getElementById("edit-submit-btn");
const editFeedback = document.getElementById("edit-feedback");
let confirmResolver = null;
let cameraStream = null;
let capturedImageDataUrl = null;
let lastUnknownRedirectAt = 0;

document.querySelectorAll(".nav-link").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.view));
});

attendanceFiltersForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  state.filters.attendance = buildQueryString(new FormData(event.currentTarget));
  await loadAttendanceRecords();
});

const exportAttendanceButton = document.getElementById("export-attendance-button");
if (exportAttendanceButton) {
  exportAttendanceButton.addEventListener("click", async () => {
    const formData = new FormData(attendanceFiltersForm);
    const queryString = buildQueryString(formData);
    const url = withQuery("/api/attendance/export", queryString);

    exportAttendanceButton.disabled = true;
    const originalLabel = exportAttendanceButton.textContent;
    exportAttendanceButton.textContent = "Exporting...";

    try {
      const response = await fetch(url, { cache: "no-store" });

      if (response.status === 401) {
        window.location.href = "/login";
        return;
      }

      if (!response.ok) {
        throw new Error(`Export failed: ${response.status}`);
      }

      const blob = await response.blob();
      const downloadUrl = URL.createObjectURL(blob);
      const filename = extractFilename(response.headers.get("Content-Disposition")) || "attendance_export.csv";

      const tempAnchor = document.createElement("a");
      tempAnchor.href = downloadUrl;
      tempAnchor.download = filename;
      document.body.appendChild(tempAnchor);
      tempAnchor.click();
      document.body.removeChild(tempAnchor);
      URL.revokeObjectURL(downloadUrl);

      setFeedback("success", `Attendance records exported as ${filename}.`);
    } catch (error) {
      setFeedback("error", error.message || "Could not export attendance records.");
      console.error(error);
    } finally {
      exportAttendanceButton.disabled = false;
      exportAttendanceButton.textContent = originalLabel;
    }
  });
}

const exportXlsxButton = document.getElementById("export-xlsx-button");
if (exportXlsxButton) {
  exportXlsxButton.addEventListener("click", async () => {
    const formData = new FormData(attendanceFiltersForm);
    const queryString = buildQueryString(formData);
    const url = withQuery("/api/attendance/export", queryString ? `${queryString}&format=xlsx` : "format=xlsx");
    await downloadFile(exportXlsxButton, url, "attendance_export.xlsx", "Exporting...");
  });
}

document.addEventListener("click", async (event) => {
  const btn = event.target.closest(".report-xlsx-btn");
  if (!btn) return;
  const reportType = btn.dataset.reportType;
  if (!reportType) return;
  const url = `/api/reports/export?type=${encodeURIComponent(reportType)}&format=xlsx`;
  await downloadFile(btn, url, `report_${reportType}.xlsx`, "Exporting...");
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

if (adminCreateForm) {
  adminCreateForm.addEventListener("submit", handleAdminCreate);
}

document.getElementById("modal-close").addEventListener("click", () => modal.close());
modal.addEventListener("click", (event) => {
  if (event.target === modal) {
    modal.close();
  }
});

editModalClose.addEventListener("click", () => editEmployeeModal.close());
editEmployeeModal.addEventListener("click", (event) => {
  if (event.target === editEmployeeModal) editEmployeeModal.close();
});
editSubmitBtn.addEventListener("click", () => submitEmployeeEdit());

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

stationStartButton.addEventListener("click", () => setStationRunning(true));
stationStopButton.addEventListener("click", () => setStationRunning(false));
clearTestTimeButton.addEventListener("click", clearTestTimeOverride);
globalSearchInput.addEventListener("input", applyGlobalSearch);
sidebarStartRecognitionButton.addEventListener("click", async () => {
  setView("settings");
  await setStationRunning(true);
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
  const [summaryResponse, todayResponse, latestResponse, stationResponse, testTimeResponse] = await Promise.all([
    api("/api/dashboard/summary"),
    api("/api/attendance/today"),
    api("/api/latest-detection"),
    api("/api/camera-station/status"),
    api("/api/test-time"),
  ]);

  state.summary = summaryResponse.summary;
  state.todayRecords = todayResponse.records;
  state.latestDetection = latestResponse.latest_detection;
  state.station = stationResponse.station || stationResponse;
  state.testTime = testTimeResponse.test_time;

  await Promise.all([loadAttendanceRecords(), loadEmployees(), loadLogs(), loadUnknownFaces(), loadAdmins(), loadAdminLogs(), loadAttendanceRules()]);

  renderSummary();
  renderAnalytics();
  renderReports();
  renderAbsentToday();
  renderAdminAlerts();
  renderLatestDetection();
  renderStation();
  renderTestTime();
  renderRecentDetections();
  renderTodayAttendance();
  renderAttendanceTable();
  renderEmployees();
  renderLogs();
  renderUnknownFaces();
  renderAdmins();
  renderAdminLogs();
  renderAttendanceRules();
  refreshLabel.textContent = `Last updated ${new Date().toLocaleString()}`;
}

async function setStationRunning(shouldRun) {
  const button = shouldRun ? stationStartButton : stationStopButton;
  button.disabled = true;
  try {
    const response = await api(shouldRun ? "/api/camera-station/start" : "/api/camera-station/stop", { method: "POST" });
    state.station = response.station;
    renderStation();
    setFeedback("success", shouldRun ? "Camera station started." : "Camera station stopped.");
  } catch (error) {
    setFeedback("error", error.message);
  } finally {
    button.disabled = false;
  }
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

async function loadUnknownFaces() {
  try {
    const response = await api("/api/unknown-faces");
    state.unknownFaces = response.unknown_faces || [];
    renderUnknownFaces();
  } catch (_) {}
}

async function loadAdminLogs() {
  try {
    const response = await api("/api/admin-logs");
    state.adminLogs = response.logs || [];
    renderAdminLogs();
  } catch (_) {}
}

async function loadAdmins() {
  try {
    const response = await api("/api/admins");
    state.admins = response.admins || [];
    renderAdmins();
  } catch (_) {}
}

async function loadAttendanceRules() {
  try {
    const response = await api("/api/attendance-rules");
    state.attendanceRules = response.rules || null;
    renderAttendanceRules();
  } catch (_) {}
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
    ? `${state.session.username} is logged in`
    : "Not signed in";
  const avatar = document.getElementById("admin-avatar");
  if (avatar) {
    avatar.textContent = state.session?.username ? state.session.username.charAt(0).toUpperCase() : "A";
  }
}

function setView(viewName) {
  if (state.activeView === "settings" && viewName !== "settings") {
    stopCameraStream();
  }
  state.activeView = viewName;

  document.querySelectorAll(".nav-link").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === viewName);
  });
  document.querySelectorAll(".view").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.viewPanel === viewName);
  });

  const activeNav = document.querySelector(`.nav-link[data-view="${viewName}"] span:last-child`);
  pageTitle.textContent = activeNav ? activeNav.textContent : "Overview";
  topbarSubtitle.textContent = VIEW_META[viewName] || VIEW_META.dashboard;
}

function renderSummary() {
  const container = document.getElementById("summary-cards");
  if (!state.summary) {
    container.innerHTML = "";
    return;
  }

  const unknownDetections = state.logs.filter((log) => log.status_group === "unknown" || statusGroupFromText(log.status) === "unknown").length;
  const cards = [
    ["Total Registered Employees", state.summary.total_registered_employees, "&#128101;"],
    ["Present Today", state.summary.present_today, "&#9989;"],
    ["Late Today", state.summary.late_today, "&#9200;"],
    ["Unknown Detections", unknownDetections, "&#10067;"],
  ];

  container.innerHTML = cards.map(([label, value, icon]) => `
    <article class="summary-card">
      <div class="summary-card-head">
        <p class="label">${escapeHtml(label)}</p>
        <span class="summary-icon summary-emoji">${icon}</span>
      </div>
      <p class="value">${value}</p>
    </article>
  `).join("");
}

function renderAnalytics() {
  renderAttentionSummary();
  renderLateWeek();
  renderCheckFlow();
}

function renderAttentionSummary() {
  const container = document.getElementById("attendance-trend-chart");
  if (!container) return;
  const lateCount = Number(state.summary?.late_today || 0);
  const unknownCount = state.logs.filter((log) => log.status_group === "unknown" || statusGroupFromText(log.status) === "unknown").length;
  const overtimeCount = Number(state.summary?.overtime_employees || 0);
  const noCheckoutCount = state.todayRecords.filter((record) => record.entry_time && !record.exit_time).length;
  const issues = [
    { label: "Late", value: lateCount, group: lateCount ? "late" : "neutral" },
    { label: "Unknown", value: unknownCount, group: unknownCount ? "unknown" : "neutral" },
    { label: "No Check-Out", value: noCheckoutCount, group: noCheckoutCount ? "checkout" : "neutral" },
    { label: "Overtime", value: overtimeCount, group: overtimeCount ? "overtime" : "neutral" },
  ];
  const needsAttention = issues.some((item) => item.value > 0);

  container.innerHTML = `
    <div class="attention-head">
      <div>
        <span>Attention</span>
        <strong>${needsAttention ? "Review needed" : "All clear"}</strong>
      </div>
      <span class="attention-state ${needsAttention ? "warning" : "checkin"}">${needsAttention ? "!" : "OK"}</span>
    </div>
    <div class="attention-grid">
      ${issues.map((item) => `
        <div class="attention-item ${item.group}">
          <span>${escapeHtml(item.label)}</span>
          <strong>${item.value}</strong>
        </div>
      `).join("")}
    </div>
  `;
}

function renderAttendanceTrend() {
  const container = document.getElementById("attendance-trend-chart");
  const counts = new Map();
  state.attendanceRecords.forEach((record) => {
    counts.set(record.date, (counts.get(record.date) || 0) + (record.entry_time ? 1 : 0));
  });
  const points = [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0])).slice(-7);
  renderBars(container, points, "No attendance trend data yet.");
}

function renderLateWeek() {
  const container = document.getElementById("late-week-chart");
  const counts = new Map();
  state.logs
    .filter((log) => ["late", "warning", "violation"].includes(statusGroupFromText(log.status)))
    .forEach((log) => counts.set(log.date || "Unknown", (counts.get(log.date || "Unknown") || 0) + 1));
  const points = [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0])).slice(-7);
  renderBars(container, points, "No late arrivals found in current log data.");
}

function renderBars(container, points, emptyMessage) {
  if (!container) return;
  if (!points.length) {
    container.innerHTML = `<div class="empty-state chart-empty">${escapeHtml(emptyMessage)}</div>`;
    return;
  }
  const maxValue = Math.max(...points.map(([, value]) => value), 1);
  container.innerHTML = points.map(([label, value]) => `
    <div class="chart-row">
      <span>${escapeHtml(shortDateLabel(label))}</span>
      <div class="chart-track"><div class="chart-fill" style="width:${Math.max(8, (value / maxValue) * 100)}%"></div></div>
      <strong>${value}</strong>
    </div>
  `).join("");
}

function renderCheckFlow() {
  const container = document.getElementById("check-flow-chart");
  if (!container) return;
  const checkIns = state.todayRecords.filter((record) => record.entry_time).length;
  const checkOuts = state.todayRecords.filter((record) => record.exit_time).length;
  const stillInside = Math.max(checkIns - checkOuts, 0);
  const totalRegistered = Number(state.summary?.total_registered_employees || 0);
  const presentRate = totalRegistered ? Math.round((checkIns / totalRegistered) * 100) : 0;
  container.innerHTML = `
    <div class="today-overview-card">
      <div>
        <span>Present Rate</span>
        <strong>${presentRate}%</strong>
      </div>
      <div class="today-progress"><span style="width:${Math.max(3, Math.min(presentRate, 100))}%"></span></div>
    </div>
    <div class="flow-stats-row">
      <div class="flow-stat checkin"><span>Check-In</span><strong>${checkIns}</strong></div>
      <div class="flow-stat checkout"><span>Check-Out</span><strong>${checkOuts}</strong></div>
      <div class="flow-stat neutral"><span>Still Inside</span><strong>${stillInside}</strong></div>
    </div>
  `;
}

function renderReports() {
  const container = document.getElementById("reports-panel");
  if (!container) return;
  const lateCount = state.logs.filter((log) => ["late", "warning", "violation"].includes(statusGroupFromText(log.status))).length;
  const overtimeCount = state.logs.filter((log) => statusGroupFromText(log.status) === "overtime").length;
  const presentRate = state.summary?.total_registered_employees
    ? Math.round(((state.summary.present_today || 0) / state.summary.total_registered_employees) * 100)
    : 0;
  const punctualCount = state.todayRecords.filter((record) => statusGroupFromText(record.current_status) === "checkin").length;

  container.innerHTML = `
    <article class="report-card hero-report">
      <p class="eyebrow">Attendance Summary</p>
      <h3>Today ${presentRate}% present</h3>
    </article>
    <article class="report-card">${reportMetric("Late Count", lateCount)}</article>
    <article class="report-card">${reportMetric("Overtime Count", overtimeCount)}</article>
    <article class="report-card">${reportMetric("Punctuality Overview", punctualCount)}</article>
    <article class="report-card export-card">
      <p class="eyebrow">Export</p>
      <h3>Reports Ready</h3>
    </article>
  `;
}

function reportMetric(label, value) {
  return `
    <p class="eyebrow">${escapeHtml(label)}</p>
    <h3>${value}</h3>
  `;
}

function renderLatestDetection() {
  const container = document.getElementById("latest-detection");
  if (!container) return;
  const latest = state.latestDetection;
  const station = state.station || {};
  const cameraLabel = station.online ? "Live" : station.worker_running ? "Starting" : "Offline";

  const group = latest ? latest.status_group || statusGroupFromText(latest.status || latest.event_type) : "neutral";
  container.innerHTML = `
    <div class="camera-preview-card">
      <div class="camera-preview-frame">
        <img src="/api/camera-station/feed" alt="Live attendance camera preview">
        <div class="camera-preview-shade"></div>
        <div class="camera-live-pill ${station.online ? "online" : "offline"}">
          <span></span>${escapeHtml(cameraLabel)}
        </div>
        <div class="camera-latest-card">
          ${latest ? `
            <div class="live-avatar">${escapeHtml(getInitials(latest.employee_name))}</div>
            <div class="live-person-copy">
              <p class="eyebrow">Latest Recognized</p>
              <p class="identity" title="${escapeHtml(latest.employee_name)}">${escapeHtml(latest.employee_name)}</p>
              <div class="live-status-line">
                ${badge(latest.status, group)}
                <span>${formatTimePart(latest.timestamp)}</span>
              </div>
            </div>
          ` : `
            <div class="live-avatar">?</div>
            <div class="live-person-copy">
              <p class="eyebrow">Latest Recognized</p>
              <p class="identity">Waiting</p>
              <div class="live-status-line"><span>No recognition events yet</span></div>
            </div>
          `}
        </div>
      </div>
    </div>
  `;
}

function renderStation() {
  const station = state.station || {};
  const stateBadge = document.getElementById("station-state");
  const statusGrid = document.getElementById("station-status");
  const latest = document.getElementById("station-latest");
  const statusLabel = station.online ? "Running" : station.worker_running ? "Starting" : "Stopped";
  const lastFrame = station.last_frame_at ? formatDateTime(station.last_frame_at) : "No frames yet";
  const logic = station.logic || {};

  stateBadge.classList.toggle("offline", !station.online);
  stateBadge.querySelector("span").textContent = statusLabel;
  stationStartButton.disabled = Boolean(station.worker_running);
  stationStopButton.disabled = !station.worker_running;

  statusGrid.innerHTML = `
    <div class="metric">
      <div class="label">Camera Status</div>
      <div class="value">${escapeHtml(statusLabel)}</div>
    </div>
    <div class="metric">
      <div class="label">Recognition Status</div>
      <div class="value">${escapeHtml(station.latest_recognition?.recognition_status || "Waiting")}</div>
    </div>
    <div class="metric">
      <div class="label">Camera</div>
      <div class="value">Index ${station.camera_index ?? 0}</div>
    </div>
    <div class="metric">
      <div class="label">Registered Faces</div>
      <div class="value">${station.known_faces ?? 0}</div>
    </div>
    <div class="metric">
      <div class="label">Latest Frame</div>
      <div class="value">${escapeHtml(lastFrame)}</div>
    </div>
    <div class="metric">
      <div class="label">Check-out Window</div>
      <div class="value">${formatSeconds(logic.check_out_after_seconds)}</div>
    </div>
    <div class="metric">
      <div class="label">Re-entry Cooldown</div>
      <div class="value">${formatSeconds(logic.reentry_after_seconds)}</div>
    </div>
    <div class="metric">
      <div class="label">Check-in Liveness</div>
      <div class="value">${escapeHtml(logic.checkin_liveness || "Unavailable")}</div>
    </div>
  `;

  if (station.last_error) {
    latest.innerHTML = `<div class="empty-state station-error">${escapeHtml(station.last_error)}</div>`;
    return;
  }

  if (!station.latest_recognition) {
    latest.innerHTML = `<div class="empty-state">Waiting for a recognized attendance event.</div>`;
    return;
  }

  if (station.latest_recognition.recognition_status === "Unknown") {
    latest.innerHTML = `
      <article class="station-event station-unknown">
        <p class="eyebrow">Registration Suggested</p>
        <strong>Unknown Face</strong>
        <div class="station-event-meta">
          ${badge("Unknown", "unknown")}
          <span>${formatDateTime(station.latest_recognition.timestamp)}</span>
        </div>
        <button class="secondary-button" type="button" id="open-register-from-unknown">Open Register</button>
      </article>
    `;
    document.getElementById("open-register-from-unknown").addEventListener("click", () => setView("settings"));
    autoOpenRegisterForUnknown();
    return;
  }

  latest.innerHTML = `
    <article class="station-event">
      <p class="eyebrow">Latest Station Event</p>
      <strong>${escapeHtml(station.latest_recognition.employee_name)}</strong>
      <div class="station-event-meta">
        ${badge(station.latest_recognition.status, statusGroupFromText(station.latest_recognition.status))}
        <span>${formatDateTime(station.latest_recognition.timestamp)}</span>
      </div>
    </article>
  `;
}

function autoOpenRegisterForUnknown() {
  const now = Date.now();
  if (state.activeView === "settings" || now - lastUnknownRedirectAt < 15000) {
    return;
  }
  lastUnknownRedirectAt = now;
  setFeedback("info", "Unknown face detected. Settings opened so you can register the employee.");
  setView("settings");
}

function renderTestTime() {
  const panel = document.getElementById("test-time-panel");
  const status = document.getElementById("test-time-status");
  const current = document.getElementById("test-time-current");
  const testTime = state.testTime || {};
  const scenarios = testTime.scenarios || [];

  status.classList.toggle("offline", !testTime.active);
  status.querySelector("span").textContent = testTime.active ? testTime.label : "Real System Time";
  current.textContent = formatDateTime(testTime.current_datetime);
  clearTestTimeButton.disabled = !testTime.active;

  panel.innerHTML = scenarios.map((scenario) => `
    <button class="scenario-button ${testTime.scenario_key === scenario.key ? "active" : ""}" data-scenario-key="${escapeHtml(scenario.key)}" type="button">
      <span>${escapeHtml(scenario.label)}</span>
      <strong>${escapeHtml(scenario.time.slice(0, 5))}</strong>
    </button>
  `).join("");

  panel.querySelectorAll("[data-scenario-key]").forEach((button) => {
    button.addEventListener("click", () => applyTestTimeOverride(button.dataset.scenarioKey));
  });
}

async function applyTestTimeOverride(scenarioKey) {
  try {
    const response = await api("/api/test-time", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario_key: scenarioKey }),
    });
    state.testTime = response.test_time;
    renderTestTime();
    setFeedback("success", `Attendance clock set to ${response.test_time.label}.`);
  } catch (error) {
    setFeedback("error", error.message);
  }
}

async function clearTestTimeOverride() {
  try {
    const response = await api("/api/test-time/clear", { method: "POST" });
    state.testTime = response.test_time;
    renderTestTime();
    setFeedback("success", "Attendance clock returned to real system time.");
  } catch (error) {
    setFeedback("error", error.message);
  }
}

function renderRecentDetections() {
  const container = document.getElementById("recent-detections");
  const detections = state.summary?.recent_detections || [];
  container.innerHTML = detections.length ? detections.map((event) => {
    const group = event.status_group || statusGroupFromText(event.status || event.event_type);
    return `
    <article class="stack-item event-card ${group}">
      <span class="event-dot ${group}"></span>
      <div class="event-row-main">
        <div class="event-row-copy">
          <strong class="stack-item-title">${escapeHtml(event.employee_name)}</strong>
          <p class="stack-item-meta">${formatTimePart(event.timestamp)} &middot; ${escapeHtml(event.event_type)}</p>
        </div>
        ${badge(event.status, group)}
      </div>
    </article>
  `;
  }).join("") : `<div class="empty-state live-empty"><span class="empty-state-icon">?</span><strong>No recent detections available.</strong><span>New camera events will appear here.</span></div>`;
}

function renderAdminAlerts() {
  const container = document.getElementById("admin-alerts");
  if (!container) return;
  const alerts = state.summary?.admin_alerts || [];

  if (!alerts.length) {
    container.innerHTML = `
      <div class="empty-state admin-alert-clear">
        <span class="empty-state-icon">OK</span>
        <strong>No repeated late arrivals.</strong>
        <span>Employees are below the alert threshold.</span>
      </div>
    `;
    return;
  }

  container.innerHTML = alerts.map((alert) => `
    <article class="admin-alert-item ${escapeHtml(alert.severity || "warning")}">
      <div class="admin-alert-main">
        ${avatarHtml(alert.employee_image_url, alert.employee_name, 38)}
        <div>
          <strong>${escapeHtml(alert.employee_name)}</strong>
          <span>${escapeHtml(alert.count)} late arrivals in ${escapeHtml(alert.window_days)} days</span>
        </div>
      </div>
      <div class="admin-alert-meta">
        <span>Threshold ${escapeHtml(alert.threshold)}</span>
        <span>${alert.latest_timestamp ? formatDatePart(alert.latest_timestamp) : "Recent"}</span>
      </div>
    </article>
  `).join("");
}

function renderTodayAttendance() {
  const tbody = document.getElementById("today-attendance-body");
  if (!tbody) return;
  renderAttendanceRows(
    tbody,
    state.todayRecords,
    "No attendance records for today."
  );
}

function renderAttendanceTable() {
  const tbody = document.getElementById("attendance-body");
  if (!tbody) return;
  renderAttendanceRows(
    tbody,
    state.attendanceRecords,
    "No attendance records found."
  );
}

function renderAttendanceRows(tbody, records, emptyMessage) {
  tbody.innerHTML = records.length ? records.map((record) => `
    <tr>
      <td class="cell-compact">${record.employee_id ?? "&mdash;"}</td>
      <td class="record-name-cell">
        <div class="name-with-avatar">
          ${avatarHtml(record.employee_image_url, record.employee_name)}
          <div>
            <span class="record-name">${escapeHtml(record.employee_name)}</span>
            <span class="subtle">${escapeHtml(record.event_type)}</span>
          </div>
        </div>
      </td>
      <td class="cell-compact">${escapeHtml(record.date)}</td>
      <td class="cell-compact">${record.entry_time ?? "&mdash;"}</td>
      <td class="cell-compact">${record.exit_time ?? "&mdash;"}</td>
      <td class="cell-compact">${formatDuration(record.entry_time, record.exit_time)}</td>
      <td>${badge(record.current_status, statusGroupFromText(record.current_status))}</td>
      <td class="cell-compact">${escapeHtml(record.event_type)}</td>
      <td>${record.notes.length ? record.notes.map(escapeHtml).join(", ") : "&mdash;"}</td>
    </tr>
  `).join("") : `
    <tr>
      <td colspan="9"><div class="empty-state">${escapeHtml(emptyMessage)}</div></td>
    </tr>
  `;
}

function renderEmployees() {
  const tbody = document.getElementById("employees-body");
  tbody.innerHTML = state.employees.length ? state.employees.map((employee) => {
    const isDeleting = state.deletingEmployeeId === employee.id;
    return `
      <tr${employee.status === "inactive" ? ' style="opacity:0.6"' : ""}>
        <td class="cell-compact">${employee.id}</td>
        <td class="record-name-cell">
          <div class="name-with-avatar">
            ${avatarHtml(employee.image_url, employee.name)}
            <div>
              <span class="employee-name">${escapeHtml(employee.name)}</span>
              <span class="subtle">${escapeHtml(employee.department_role || "Registered identity profile")}${employee.status === "inactive" ? " &middot; Inactive" : ""}</span>
            </div>
          </div>
        </td>
        <td class="cell-compact">${employee.face_registered ? "Yes" : "No"}</td>
        <td class="record-meta">${employee.last_seen ? formatDateTime(employee.last_seen) : "Never logged"}</td>
        <td>${badge(employee.current_status, statusGroupFromText(employee.current_status))}</td>
        <td>
          <div class="action-group">
            <button class="details-button" data-employee-id="${employee.id}" ${isDeleting ? "disabled" : ""}>Open</button>
            <button
              class="secondary-button edit-button"
              data-employee-id="${employee.id}"
              data-employee-name="${escapeHtml(employee.name)}"
              data-employee-department="${escapeHtml(employee.department_role || "")}"
              data-employee-status="${escapeHtml(employee.status || "active")}"
              ${isDeleting ? "disabled" : ""}
            >Edit</button>
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

  tbody.querySelectorAll(".edit-button").forEach((button) => {
    button.addEventListener("click", () => openEditEmployeeModal(button.dataset));
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
  document.getElementById("modal-avatar").innerHTML = avatarHtml(employee.image_url, employee.name, 64);

  const history = employee.history || [];
  modalContent.innerHTML = `
    <div class="manual-event-row">
      <button class="secondary-button checkin-button" data-event-type="CHECK-IN">Check In</button>
      <button class="secondary-button checkout-button" data-event-type="CHECK-OUT">Check Out</button>
    </div>
    <div class="detail-grid detail-metrics-grid">
      <div class="detail-card">
        <div class="detail-label">Latest Attendance State</div>
        <div class="detail-value">${escapeHtml(employee.latest_attendance_state)}</div>
      </div>
      <div class="detail-card">
        <div class="detail-label">Latest Event</div>
        <div class="detail-value">${employee.latest_event ? escapeHtml(employee.latest_event.status) : "No events yet"}</div>
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
    ${employee.department_role ? `<p class="detail-note">Department / Role: ${escapeHtml(employee.department_role)}</p>` : ""}
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

  modalContent.querySelectorAll("[data-event-type]").forEach((button) => {
    button.addEventListener("click", () => handleManualEvent(employee.id, button.dataset.eventType));
  });

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
    message: "",
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
      ? escapeHtml(log.notes.join(" - "))
      : hasParsedData
      ? escapeHtml(log.status)
      : escapeHtml(log.raw || "No log data available.");

    return `
      <article class="log-item${index === 0 ? " recent" : ""}">
        <div class="log-item-header">
          <div class="name-with-avatar">
            ${avatarHtml(log.employee_image_url, log.employee_name ?? "?")}
            <strong class="employee-name">${escapeHtml(log.employee_name ?? "Unknown line")}</strong>
          </div>
          ${badge(log.status, log.status_group)}
        </div>
        <p class="timestamp">${log.timestamp ? formatDateTime(log.timestamp) : "No timestamp"} &middot; ${escapeHtml(log.event_type)}</p>
        <p class="log-item-body">${supportingText}</p>
        ${index === 0 ? '<span class="log-recent-label">Most Recent Activity</span>' : ""}
      </article>
    `;
  }).join("") : `<div class="empty-state">No log entries matched the current filters.</div>`;
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

function eventSymbol(group) {
  const symbols = {
    checkin: "+",
    checkout: "-",
    lunch: "~",
    overtime: "^",
    late: "!",
    warning: "!",
    violation: "!",
    unknown: "?",
  };
  return symbols[group] || "i";
}

function statusGroupFromText(text) {
  const value = (text || "").toLowerCase();
  if (value.includes("unknown")) return "unknown";
  if (value.includes("violation")) return "violation";
  if (value.includes("warning")) return "warning";
  if (value.includes("late")) return "late";
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

function formatDatePart(value) {
  if (!value) return "&mdash;";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return escapeHtml(value);
  return date.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

function formatTimePart(value) {
  if (!value) return "&mdash;";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
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
function extractFilename(contentDisposition) {
  if (!contentDisposition) {
    return null;
  }
  const match = /filename="?([^"]+)"?/i.exec(contentDisposition);
  return match ? match[1] : null;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("\"", "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function shortDateLabel(value) {
  if (!value || value === "Unknown") return "Unknown";
  const parts = value.split("-");
  return parts.length === 3 ? `${parts[1]}/${parts[2]}` : value;
}

function applyGlobalSearch() {
  const value = globalSearchInput.value.trim();
  const formMap = {
    attendance: attendanceFiltersForm,
    employees: employeeFiltersForm,
    logs: logFiltersForm,
  };
  const form = formMap[state.activeView];
  if (!form) return;
  const input = form.querySelector('input[name="search"]');
  if (!input) return;
  input.value = value;
  form.dispatchEvent(new Event("submit", { cancelable: true }));
}

function formatSeconds(value) {
  if (!Number.isFinite(value)) {
    return "Unavailable";
  }
  if (value >= 60 && value % 60 === 0) {
    return `${value / 60} min`;
  }
  return `${value} sec`;
}

function stopCameraStream() {
  if (cameraStream) {
    cameraStream.getTracks().forEach((track) => track.stop());
    cameraStream = null;
  }
  const video = document.getElementById("register-video");
  if (video) {
    video.srcObject = null;
    video.style.display = "none";
  }
  const placeholder = document.getElementById("camera-placeholder");
  if (placeholder) placeholder.style.display = "";
  const startBtn = document.getElementById("start-camera-btn");
  if (startBtn) startBtn.style.display = "";
  const capBtn = document.getElementById("capture-btn");
  if (capBtn) capBtn.disabled = true;
  const retakeBtn = document.getElementById("retake-btn");
  if (retakeBtn) retakeBtn.style.display = "none";
  const preview = document.getElementById("captured-preview");
  if (preview) preview.style.display = "none";
  capturedImageDataUrl = null;
}

function setRegisterFeedback(type, message) {
  const el = document.getElementById("register-feedback");
  if (!message) {
    el.className = "feedback-banner";
    el.textContent = "";
    return;
  }
  el.className = `feedback-banner ${type} show`;
  el.textContent = message;
}

(function initRegisterView() {
  const startCameraBtn = document.getElementById("start-camera-btn");
  const captureBtn = document.getElementById("capture-btn");
  const retakeBtn = document.getElementById("retake-btn");
  const registerVideo = document.getElementById("register-video");
  const registerCanvas = document.getElementById("register-canvas");
  const capturedPreview = document.getElementById("captured-preview");
  const cameraPlaceholder = document.getElementById("camera-placeholder");
  const cameraSource = document.getElementById("camera-source");
  const uploadSource = document.getElementById("upload-source");
  const uploadArea = document.getElementById("upload-area");
  const uploadPreview = document.getElementById("upload-preview");
  const clearUploadBtn = document.getElementById("clear-upload-btn");
  const photoUpload = document.getElementById("photo-upload");
  const registerName = document.getElementById("register-name");
  const registerDepartment = document.getElementById("register-department");
  const registerSubmitBtn = document.getElementById("register-submit-btn");

  // Source tab switching
  document.querySelectorAll(".source-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      const source = tab.dataset.source;
      document.querySelectorAll(".source-tab").forEach((t) =>
        t.classList.toggle("active", t.dataset.source === source)
      );
      setRegisterFeedback("", "");
      capturedImageDataUrl = null;
      registerSubmitBtn.disabled = true;

      if (source === "camera") {
        uploadSource.style.display = "none";
        uploadPreview.style.display = "none";
        uploadArea.style.display = "";
        clearUploadBtn.style.display = "none";
        photoUpload.value = "";
        cameraSource.style.display = "";
      } else {
        if (cameraStream) {
          cameraStream.getTracks().forEach((t) => t.stop());
          cameraStream = null;
          registerVideo.srcObject = null;
          registerVideo.style.display = "none";
          cameraPlaceholder.style.display = "";
          startCameraBtn.style.display = "";
          captureBtn.disabled = true;
          retakeBtn.style.display = "none";
          capturedPreview.style.display = "none";
        }
        cameraSource.style.display = "none";
        uploadSource.style.display = "";
      }
    });
  });

  // File upload helpers
  function applyUploadedFile(file) {
    if (!file.type.startsWith("image/")) {
      setRegisterFeedback("error", "Please select a valid image file (JPG, PNG, WEBP).");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setRegisterFeedback("error", "File is too large. Maximum size is 10 MB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      capturedImageDataUrl = e.target.result;
      uploadPreview.src = capturedImageDataUrl;
      uploadPreview.style.display = "block";
      uploadArea.style.display = "none";
      clearUploadBtn.style.display = "";
      registerSubmitBtn.disabled = !registerName.value.trim();
    };
    reader.readAsDataURL(file);
  }

  photoUpload.addEventListener("change", () => {
    if (photoUpload.files[0]) applyUploadedFile(photoUpload.files[0]);
  });

  clearUploadBtn.addEventListener("click", () => {
    capturedImageDataUrl = null;
    photoUpload.value = "";
    uploadPreview.style.display = "none";
    uploadArea.style.display = "";
    clearUploadBtn.style.display = "none";
    registerSubmitBtn.disabled = true;
    setRegisterFeedback("", "");
  });

  uploadArea.addEventListener("dragover", (e) => {
    e.preventDefault();
    uploadArea.classList.add("drag-over");
  });

  uploadArea.addEventListener("dragleave", (e) => {
    if (!uploadArea.contains(e.relatedTarget)) uploadArea.classList.remove("drag-over");
  });

  uploadArea.addEventListener("drop", (e) => {
    e.preventDefault();
    uploadArea.classList.remove("drag-over");
    const file = e.dataTransfer.files[0];
    if (file) applyUploadedFile(file);
  });

  startCameraBtn.addEventListener("click", async () => {
    setRegisterFeedback("", "");
    try {
      cameraStream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
      registerVideo.srcObject = cameraStream;
      registerVideo.style.display = "block";
      cameraPlaceholder.style.display = "none";
      capturedPreview.style.display = "none";
      startCameraBtn.style.display = "none";
      captureBtn.disabled = false;
      retakeBtn.style.display = "none";
      capturedImageDataUrl = null;
      registerSubmitBtn.disabled = true;
    } catch (err) {
      setRegisterFeedback("error", `Camera access denied: ${err.message}`);
    }
  });

  captureBtn.addEventListener("click", () => {
    registerCanvas.width = registerVideo.videoWidth;
    registerCanvas.height = registerVideo.videoHeight;
    registerCanvas.getContext("2d").drawImage(registerVideo, 0, 0);
    capturedImageDataUrl = registerCanvas.toDataURL("image/jpeg", 0.92);
    capturedPreview.src = capturedImageDataUrl;
    capturedPreview.style.display = "block";
    registerVideo.style.display = "none";
    captureBtn.disabled = true;
    retakeBtn.style.display = "";
    registerSubmitBtn.disabled = !registerName.value.trim();
  });

  retakeBtn.addEventListener("click", () => {
    capturedImageDataUrl = null;
    capturedPreview.style.display = "none";
    registerVideo.style.display = "block";
    captureBtn.disabled = false;
    retakeBtn.style.display = "none";
    registerSubmitBtn.disabled = true;
    setRegisterFeedback("", "");
  });

  registerName.addEventListener("input", () => {
    registerSubmitBtn.disabled = !registerName.value.trim() || !capturedImageDataUrl;
  });

  registerSubmitBtn.addEventListener("click", async () => {
    const name = registerName.value.trim();
    const departmentRole = registerDepartment.value.trim();
    if (!name || !capturedImageDataUrl) return;

    registerSubmitBtn.disabled = true;
    registerSubmitBtn.textContent = "Registering...";
    setRegisterFeedback("", "");

    try {
      const response = await api("/api/employees/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, department_role: departmentRole, image: capturedImageDataUrl }),
      });

      setRegisterFeedback("success", `${response.name} registered successfully (ID: ${response.user_id}).`);
      registerName.value = "";
      registerDepartment.value = "";
      stopCameraStream();
      await loadEmployees();
    } catch (err) {
      setRegisterFeedback("error", err.message);
    } finally {
      registerSubmitBtn.disabled = false;
      registerSubmitBtn.textContent = "Register Employee";
    }
  });
}());

function formatDuration(entryTime, exitTime) {
  if (!entryTime || !exitTime) return "&mdash;";
  const toSeconds = (t) => {
    const [h, m, s = 0] = t.split(":").map(Number);
    return h * 3600 + m * 60 + s;
  };
  const diff = toSeconds(exitTime) - toSeconds(entryTime);
  if (diff <= 0) return "&mdash;";
  const hours = Math.floor(diff / 3600);
  const minutes = Math.floor((diff % 3600) / 60);
  return hours === 0 ? `${minutes}m` : `${hours}h ${minutes}m`;
}

function renderAbsentToday() {
  const container = document.getElementById("absent-list");
  if (!container) return;
  const absent = state.summary?.absent_employees || [];
  if (!absent.length) {
    container.innerHTML = `
      <div class="empty-state absent-clear-state">
        <span class="empty-state-icon">OK</span>
        <strong>All registered employees have checked in.</strong>
        <span>No missing check-ins today.</span>
      </div>
    `;
    return;
  }
  container.innerHTML = `<div class="absent-grid">${absent.map((emp) => `
    <div class="absent-item">
      ${avatarHtml(emp.image_url, emp.name, 32)}
      <span class="absent-name">${escapeHtml(emp.name)}</span>
    </div>
  `).join("")}</div>`;
}

async function handleManualEvent(employeeId, eventType) {
  const endpoint = eventType === "CHECK-IN" ? "checkin" : "checkout";
  try {
    const response = await api(`/api/employees/${employeeId}/${endpoint}`, { method: "POST" });
    setFeedback("success", `${response.employee_name} manually ${eventType === "CHECK-IN" ? "checked in" : "checked out"} at ${new Date(response.timestamp).toLocaleTimeString()}.`);
    if (modal.open) modal.close();
    await refreshAll();
  } catch (error) {
    setFeedback("error", error.message);
  }
}

// ---------------------------------------------------------------------------
// Employee edit
// ---------------------------------------------------------------------------

function openEditEmployeeModal(dataset) {
  state.editingEmployeeId = Number(dataset.employeeId);
  editModalTitle.textContent = dataset.employeeName || "Employee";
  editNameInput.value = dataset.employeeName || "";
  editDepartmentInput.value = dataset.employeeDepartment || "";
  editStatusSelect.value = dataset.employeeStatus || "active";
  editFeedback.className = "feedback-banner";
  editFeedback.textContent = "";
  editEmployeeModal.showModal();
}

async function submitEmployeeEdit() {
  const id = state.editingEmployeeId;
  if (!id) return;

  const fullName = editNameInput.value.trim();
  const departmentRole = editDepartmentInput.value.trim();
  const status = editStatusSelect.value;

  if (!fullName) {
    editFeedback.className = "feedback-banner error show";
    editFeedback.textContent = "Employee name cannot be empty.";
    return;
  }

  editSubmitBtn.disabled = true;
  editSubmitBtn.textContent = "Saving...";

  try {
    await api(`/api/employees/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ full_name: fullName, department_role: departmentRole, status }),
    });
    editFeedback.className = "feedback-banner success show";
    editFeedback.textContent = "Employee updated successfully.";
    setFeedback("success", `${fullName} updated.`);
    await refreshAll();
    setTimeout(() => editEmployeeModal.close(), 800);
  } catch (err) {
    editFeedback.className = "feedback-banner error show";
    editFeedback.textContent = err.message || "Could not save changes.";
  } finally {
    editSubmitBtn.disabled = false;
    editSubmitBtn.textContent = "Save Changes";
  }
}

// ---------------------------------------------------------------------------
// Unknown faces
// ---------------------------------------------------------------------------

function renderUnknownFaces() {
  const container = document.getElementById("unknown-faces-list");
  if (!container) return;
  const faces = state.unknownFaces || [];

  if (!faces.length) {
    container.innerHTML = `<div class="empty-state"><span class="empty-state-icon">?</span><strong>No unknown face detections recorded yet.</strong></div>`;
    return;
  }

  container.innerHTML = faces.map((face, index) => `
    <article class="log-item${index === 0 ? " recent" : ""}">
      <div class="log-item-header">
        <div class="name-with-avatar">
          ${face.image_url
            ? `<div class="avatar-wrap"><img src="${escapeHtml(face.image_url)}" class="avatar" style="width:40px;height:40px" alt="Unknown face" onerror="this.classList.add('avatar-error')"><span class="avatar avatar-fallback" style="width:40px;height:40px;font-size:12px">?</span></div>`
            : `<span class="avatar avatar-fallback" style="width:40px;height:40px;font-size:12px">?</span>`
          }
          <strong>Unknown Face #${face.id}</strong>
        </div>
        <span class="badge unknown">Unknown</span>
      </div>
      <p class="timestamp">First seen: ${formatDateTime(face.first_seen)} &middot; Last seen: ${formatDateTime(face.last_seen)}</p>
      <p class="log-item-body">Detected ${face.detection_count} time${face.detection_count !== 1 ? "s" : ""}</p>
      <div style="margin-top:.5rem">
        <button class="secondary-button register-unknown-btn" data-face-id="${face.id}" data-image-url="${escapeHtml(face.image_url || "")}" type="button">Register this person</button>
      </div>
    </article>
  `).join("");

  container.querySelectorAll(".register-unknown-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      setView("settings");
      setFeedback("info", "Navigate to the Register section below to register this face. You can upload the saved image.");
    });
  });
}

// ---------------------------------------------------------------------------
// Admin activity log
// ---------------------------------------------------------------------------

function renderAdmins() {
  const tbody = document.getElementById("admins-body");
  if (!tbody) return;
  const admins = state.admins || [];

  if (!admins.length) {
    tbody.innerHTML = `<tr><td colspan="2"><div class="empty-state">No admin accounts found.</div></td></tr>`;
    return;
  }

  tbody.innerHTML = admins.map((admin) => `
    <tr>
      <td class="cell-compact">${admin.id}</td>
      <td>${escapeHtml(admin.username)}${state.session?.username === admin.username ? ' <span class="badge checkin">Current</span>' : ""}</td>
    </tr>
  `).join("");
}

async function handleAdminCreate(event) {
  event.preventDefault();
  if (!adminCreateForm) return;

  const formData = new FormData(adminCreateForm);
  const username = String(formData.get("username") || "").trim();
  const password = String(formData.get("password") || "");
  const submitButton = adminCreateForm.querySelector('button[type="submit"]');

  if (!username || password.length < 6) {
    setAdminCreateFeedback("error", "Username is required and password must be at least 6 characters.");
    return;
  }

  submitButton.disabled = true;
  submitButton.textContent = "Adding...";
  setAdminCreateFeedback("", "");

  try {
    const response = await api("/api/admins", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    adminCreateForm.reset();
    setAdminCreateFeedback("success", `${response.admin.username} can now log in to the dashboard.`);
    await Promise.all([loadAdmins(), loadAdminLogs()]);
  } catch (error) {
    setAdminCreateFeedback("error", error.message || "Could not create admin.");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Add Admin";
  }
}

function setAdminCreateFeedback(type, message) {
  if (!adminCreateFeedback) return;
  if (!message) {
    adminCreateFeedback.className = "feedback-banner";
    adminCreateFeedback.textContent = "";
    return;
  }
  adminCreateFeedback.className = `feedback-banner ${type} show`;
  adminCreateFeedback.textContent = message;
}

function renderAdminLogs() {
  const tbody = document.getElementById("admin-logs-body");
  if (!tbody) return;
  const logs = state.adminLogs || [];

  if (!logs.length) {
    tbody.innerHTML = `<tr><td colspan="4"><div class="empty-state">No admin activity logged yet.</div></td></tr>`;
    return;
  }

  tbody.innerHTML = logs.map((log) => `
    <tr>
      <td class="record-meta">${log.timestamp ? formatDateTime(log.timestamp) : "&mdash;"}</td>
      <td class="cell-compact">${escapeHtml(log.admin_username)}</td>
      <td>${badge(log.action_type, actionTypeBadgeGroup(log.action_type))}</td>
      <td>${escapeHtml(log.details || "")}</td>
    </tr>
  `).join("");
}

function actionTypeBadgeGroup(actionType) {
  const t = (actionType || "").toUpperCase();
  if (t === "LOGIN") return "checkin";
  if (t === "EMPLOYEE_DELETED") return "violation";
  if (t.includes("CREATED") || t.includes("EDITED")) return "warning";
  if (t.includes("EXPORT")) return "neutral";
  if (t.includes("MANUAL")) return "late";
  return "neutral";
}

// ---------------------------------------------------------------------------
// Attendance rules
// ---------------------------------------------------------------------------

const RULE_LABELS = {
  work_start: "Work Start Time",
  late_warning: "Late Warning Threshold",
  late_violation: "Late Violation Threshold",
  lunch_start: "Lunch Break Start",
  lunch_end: "Lunch Break End",
  afternoon_warning: "Afternoon Warning",
  afternoon_violation: "Afternoon Violation",
  work_end: "Work End / Overtime Start",
};

function renderAttendanceRules() {
  const container = document.getElementById("attendance-rules-panel");
  if (!container) return;
  const rules = state.attendanceRules;

  if (!rules) {
    container.innerHTML = `<div class="empty-state">Loading attendance rules&hellip;</div>`;
    return;
  }

  const fields = Object.entries(RULE_LABELS).map(([key, label]) => `
    <div class="field-group" style="max-width:340px">
      <label class="input-label" for="rule-${key}">${escapeHtml(label)}</label>
      <input type="time" id="rule-${key}" name="${key}" value="${escapeHtml(rules[key] || "")}" style="padding:.4rem .6rem;border:1px solid var(--border);border-radius:6px;font-size:.9rem">
    </div>
  `).join("");

  container.innerHTML = `
    <div style="display:flex;flex-wrap:wrap;gap:1rem">
      ${fields}
    </div>
    <div style="margin-top:1rem">
      <button id="save-rules-btn" class="primary-button" type="button">Save Rules</button>
      <div id="rules-feedback" class="feedback-banner" style="margin-top:.5rem;display:inline-block;margin-left:1rem"></div>
    </div>
  `;

  document.getElementById("save-rules-btn").addEventListener("click", async () => {
    const btn = document.getElementById("save-rules-btn");
    const feedback = document.getElementById("rules-feedback");
    const updatedRules = {};
    for (const key of Object.keys(RULE_LABELS)) {
      const input = document.getElementById(`rule-${key}`);
      if (input) updatedRules[key] = input.value;
    }

    btn.disabled = true;
    btn.textContent = "Saving...";
    try {
      const response = await api("/api/attendance-rules", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updatedRules),
      });
      state.attendanceRules = response.rules;
      feedback.className = "feedback-banner success show";
      feedback.textContent = "Attendance rules saved.";
      setFeedback("success", "Attendance rules updated.");
    } catch (err) {
      feedback.className = "feedback-banner error show";
      feedback.textContent = err.message || "Could not save rules.";
    } finally {
      btn.disabled = false;
      btn.textContent = "Save Rules";
    }
  });
}

// ---------------------------------------------------------------------------
// Shared download helper
// ---------------------------------------------------------------------------

async function downloadFile(button, url, defaultFilename, loadingLabel) {
  button.disabled = true;
  const originalLabel = button.textContent;
  button.textContent = loadingLabel;

  try {
    const response = await fetch(url, { cache: "no-store" });

    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || `Export failed: ${response.status}`);
    }

    const blob = await response.blob();
    const downloadUrl = URL.createObjectURL(blob);
    const filename = extractFilename(response.headers.get("Content-Disposition")) || defaultFilename;

    const tempAnchor = document.createElement("a");
    tempAnchor.href = downloadUrl;
    tempAnchor.download = filename;
    document.body.appendChild(tempAnchor);
    tempAnchor.click();
    document.body.removeChild(tempAnchor);
    URL.revokeObjectURL(downloadUrl);

    setFeedback("success", `Downloaded ${filename}.`);
  } catch (error) {
    setFeedback("error", error.message || "Could not download file.");
    console.error(error);
  } finally {
    button.disabled = false;
    button.textContent = originalLabel;
  }
}

function getInitials(name) {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function avatarHtml(imageUrl, name, size = 40) {
  const px = `${size}px`;
  const sizeStyle = `width:${px};height:${px}`;
  const fontSize = `${Math.round(size * 0.3)}px`;
  const initials = escapeHtml(getInitials(name));
  const safeName = escapeHtml(name || "");

  if (imageUrl) {
    const safeUrl = escapeHtml(imageUrl);
    return `<div class="avatar-wrap"><img src="${safeUrl}" class="avatar" style="${sizeStyle}" alt="${safeName}" onerror="this.classList.add('avatar-error')"><span class="avatar avatar-fallback" style="${sizeStyle};font-size:${fontSize}">${initials}</span></div>`;
  }
  return `<span class="avatar avatar-fallback" style="${sizeStyle};font-size:${fontSize}">${initials}</span>`;
}

boot().catch((error) => {
  refreshLabel.textContent = "Dashboard failed to load";
  setFeedback("error", error.message);
  console.error(error);
});
