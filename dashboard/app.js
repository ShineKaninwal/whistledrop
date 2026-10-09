/* WhistleDrop moderator console. Plain JavaScript, no build step. */
(() => {
  "use strict";

  // Same origin by default (the FastAPI app serves this dashboard).
  // If you host the dashboard elsewhere, set this to the API URL, e.g. "https://api.example.com".
  const API_BASE = "";

  const STATUS_LABELS = {
    SUBMITTED: "Submitted",
    UNDER_REVIEW: "Under review",
    RESOLVED: "Resolved",
    DISMISSED: "Dismissed",
  };
  const CATEGORY_LABELS = {
    SECURITY: "Security",
    HARASSMENT: "Harassment",
    CORRUPTION: "Corruption",
    TECHNICAL: "Technical",
    OTHER: "Other",
  };

  const state = { page: 1, pageSize: 15, category: "", status: "", q: "", total: 0, pages: 0 };
  let token = sessionStorage.getItem("wd-token"); // cleared when the tab closes
  let currentReport = null;
  let listRequestId = 0;
  let lastFocused = null;

  const $ = (id) => document.getElementById(id);

  /* ---------- small helpers ---------- */

  // Builds DOM nodes with textContent only, so report text can never inject HTML.
  function h(tag, props = {}, ...children) {
    const el = document.createElement(tag);
    for (const [key, value] of Object.entries(props)) {
      if (key === "class") el.className = value;
      else if (key === "text") el.textContent = value;
      else el.setAttribute(key, value);
    }
    for (const child of children) el.append(child);
    return el;
  }

  const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
  const formatDate = (iso) => dateFormat.format(new Date(iso));

  function badge(status) {
    return h("span", { class: `badge badge-${status}`, text: STATUS_LABELS[status] || status });
  }

  function toast(message, type = "info") {
    const el = h("div", { class: `toast ${type === "error" ? "error" : ""}`, text: message });
    $("toasts").append(el);
    setTimeout(() => el.remove(), type === "error" ? 6000 : 3200);
  }

  class ApiError extends Error {
    constructor(message, status, details) {
      super(message);
      this.status = status;
      this.details = details;
    }
  }

  function describe(error) {
    if (Array.isArray(error.details) && error.details.length) {
      return error.details.map((d) => d.message).join(" ");
    }
    return error.message || "Something went wrong.";
  }

  async function api(path, { method = "GET", body, auth = true } = {}) {
    const headers = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (auth && token) headers.Authorization = `Bearer ${token}`;

    let response;
    try {
      response = await fetch(API_BASE + path, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch {
      throw new ApiError("Can't reach the server. Check your connection and try again.", 0);
    }

    let payload = null;
    try { payload = await response.json(); } catch { /* non-JSON error page */ }

    if (response.status === 401 && auth) {
      endSession("Your session expired. Sign in again.");
      throw new ApiError("Session expired.", 401);
    }
    if (!response.ok || !payload || payload.success === false) {
      const err = payload && payload.error;
      throw new ApiError((err && err.message) || `Request failed (${response.status}).`, response.status, err && err.details);
    }
    return payload.data;
  }

  /* ---------- theme ---------- */

  function applyTheme(theme) {
    if (theme) document.documentElement.setAttribute("data-theme", theme);
  }
  function toggleTheme() {
    const current = document.documentElement.getAttribute("data-theme")
      || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = current === "dark" ? "light" : "dark";
    applyTheme(next);
    localStorage.setItem("wd-theme", next); // a display preference only
  }

  /* ---------- session ---------- */

  function showLogin(message) {
    $("console-view").hidden = true;
    $("login-view").hidden = false;
    const error = $("login-error");
    error.hidden = !message;
    error.textContent = message || "";
    $("username").focus();
  }

  function showConsole() {
    $("login-view").hidden = true;
    $("console-view").hidden = false;
    refreshAll();
  }

  function endSession(message) {
    token = null;
    sessionStorage.removeItem("wd-token");
    closeDrawer();
    showLogin(message);
  }

  async function onLogin(event) {
    event.preventDefault();
    const username = $("username").value.trim();
    const password = $("password").value;
    const error = $("login-error");
    error.hidden = true;
    if (!username || !password) {
      error.textContent = "Enter your username and password.";
      error.hidden = false;
      return;
    }
    const button = $("login-submit");
    button.disabled = true;
    try {
      const data = await api("/api/auth/login", { method: "POST", body: { username, password }, auth: false });
      token = data.access_token;
      sessionStorage.setItem("wd-token", token);
      $("password").value = "";
      showConsole();
    } catch (e) {
      error.textContent = describe(e);
      error.hidden = false;
    } finally {
      button.disabled = false;
    }
  }

  /* ---------- stats + list ---------- */

  async function loadStats() {
    try {
      const stats = await api("/api/moderator/stats");
      $("stat-total").textContent = stats.total;
      for (const key of Object.keys(STATUS_LABELS)) {
        $(`stat-${key.toLowerCase()}`).textContent = stats.by_status[key] ?? 0;
      }
    } catch (e) {
      if (e.status !== 401) toast(`Couldn't load totals. ${describe(e)}`, "error");
    }
  }

  const hasFilters = () => Boolean(state.q || state.category || state.status);

  function stateRow(title, text, actionLabel, action) {
    const cell = h("td", { colspan: "6" }, h("strong", { text: title }), h("span", { text }));
    if (actionLabel) {
      const button = h("button", { class: "btn", type: "button", text: actionLabel });
      button.addEventListener("click", action);
      cell.append(h("div", {}, button));
    }
    return h("tr", { class: "state-row" }, cell);
  }

  function renderRows(items) {
    const body = $("report-rows");
    body.replaceChildren();
    if (!items.length) {
      body.append(
        hasFilters()
          ? stateRow("No reports match these filters", "Try a different search or clear the filters.", "Clear filters", clearFilters)
          : stateRow("No reports yet", "Reports submitted through the public API will appear here.")
      );
      return;
    }
    for (const report of items) {
      const open = h("button", { class: "btn", type: "button", text: "Open", "aria-label": `Open report ${report.case_code}` });
      const row = h(
        "tr",
        { class: "row" },
        h("td", {}, h("span", { class: "code", text: report.case_code })),
        h("td", { text: CATEGORY_LABELS[report.category] || report.category }),
        h("td", {}, badge(report.status)),
        h("td", { class: "when", text: formatDate(report.created_at) }),
        h("td", { class: "when", text: formatDate(report.updated_at) }),
        h("td", {}, open)
      );
      row.addEventListener("click", () => openReport(report.case_code));
      body.append(row);
    }
  }

  async function loadReports() {
    const requestId = ++listRequestId;
    $("report-rows").replaceChildren(stateRow("Loading reports…", ""));
    const params = new URLSearchParams({ page: state.page, page_size: state.pageSize });
    if (state.q) params.set("q", state.q);
    if (state.category) params.set("category", state.category);
    if (state.status) params.set("status", state.status);

    try {
      const data = await api(`/api/moderator/reports?${params}`);
      if (requestId !== listRequestId) return; // a newer request replaced this one
      state.total = data.total;
      state.pages = data.pages;
      renderRows(data.items);
      updatePager(data);
    } catch (e) {
      if (requestId !== listRequestId || e.status === 401) return;
      $("report-rows").replaceChildren(stateRow("Couldn't load reports", describe(e), "Try again", loadReports));
      $("page-info").textContent = "";
    }
  }

  function updatePager(data) {
    const from = data.total ? (data.page - 1) * data.page_size + 1 : 0;
    const to = Math.min(data.page * data.page_size, data.total);
    $("page-info").textContent = data.total ? `Showing ${from}–${to} of ${data.total}` : "No results";
    $("prev").disabled = data.page <= 1;
    $("next").disabled = data.page >= data.pages;
  }

  function refreshAll() {
    loadStats();
    loadReports();
  }

  function syncLedger() {
    document.querySelectorAll(".ledger-cell").forEach((cell) => {
      cell.setAttribute("aria-pressed", String(cell.dataset.status === state.status));
    });
    $("filter-status").value = state.status;
  }

  function clearFilters() {
    Object.assign(state, { q: "", category: "", status: "", page: 1 });
    $("search").value = "";
    $("filter-category").value = "";
    syncLedger();
    loadReports();
  }

  /* ---------- detail drawer ---------- */

  async function openReport(caseCode) {
    lastFocused = document.activeElement;
    try {
      currentReport = await api(`/api/moderator/reports/${encodeURIComponent(caseCode)}`);
    } catch (e) {
      if (e.status !== 401) toast(`Couldn't open the report. ${describe(e)}`, "error");
      return;
    }
    renderDrawer();
    $("backdrop").hidden = false;
    $("drawer").hidden = false;
    $("drawer-close").focus();
  }

  function renderDrawer() {
    const r = currentReport;
    $("drawer-code").textContent = r.case_code;
    $("d-category").textContent = CATEGORY_LABELS[r.category] || r.category;
    $("d-status").replaceChildren(badge(r.status));
    $("d-created").textContent = formatDate(r.created_at);
    $("d-updated").textContent = formatDate(r.updated_at);
    $("d-description").textContent = r.description;

    const evidence = $("d-evidence");
    evidence.replaceChildren();
    if (r.evidence_url) {
      evidence.append(h("a", { href: r.evidence_url, target: "_blank", rel: "noopener noreferrer nofollow", text: r.evidence_url }));
    } else {
      evidence.append(h("span", { class: "muted", text: "No evidence link was provided." }));
    }

    const select = $("f-status");
    select.replaceChildren(h("option", { value: r.status, text: `${STATUS_LABELS[r.status]} (current)` }));
    for (const next of r.allowed_transitions) {
      select.append(h("option", { value: next, text: STATUS_LABELS[next] }));
    }
    select.value = r.status;

    const note = $("f-note");
    note.hidden = false;
    note.textContent = r.allowed_transitions.length
      ? "Leave the update empty to show the standard message for the new status."
      : "This status is final. You can still edit the update shown to the reporter.";

    $("f-message").value = r.status_message || "";
    $("f-count").textContent = $("f-message").value.length;
    $("f-error").hidden = true;
  }

  function closeDrawer() {
    if ($("drawer").hidden) return;
    $("drawer").hidden = true;
    $("backdrop").hidden = true;
    currentReport = null;
    if (lastFocused && document.contains(lastFocused)) lastFocused.focus();
  }

  function onStatusChange() {
    // A new status usually needs a new message, so drop the old one if it was not edited.
    if ($("f-status").value !== currentReport.status && $("f-message").value === (currentReport.status_message || "")) {
      $("f-message").value = "";
      $("f-count").textContent = "0";
    }
  }

  async function onSave(event) {
    event.preventDefault();
    const status = $("f-status").value;
    const message = $("f-message").value.trim();
    const error = $("f-error");
    error.hidden = true;

    if (status === currentReport.status && !message) {
      error.textContent = "Write a status update, or choose the next status.";
      error.hidden = false;
      return;
    }
    const button = $("f-save");
    button.disabled = true;
    try {
      currentReport = await api(`/api/moderator/reports/${encodeURIComponent(currentReport.case_code)}/status`, {
        method: "PATCH",
        body: { status, message: message || null },
      });
      renderDrawer();
      toast("Update saved.");
      refreshAll();
    } catch (e) {
      if (e.status !== 401) {
        error.textContent = describe(e);
        error.hidden = false;
      }
    } finally {
      button.disabled = false;
    }
  }

  /* ---------- wiring ---------- */

  function debounce(fn, ms) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
  }

  function init() {
    applyTheme(localStorage.getItem("wd-theme"));

    $("login-form").addEventListener("submit", onLogin);
    $("logout").addEventListener("click", () => endSession());
    $("theme-toggle").addEventListener("click", toggleTheme);
    $("refresh").addEventListener("click", () => { refreshAll(); toast("Reports refreshed."); });

    $("search").addEventListener("input", debounce((e) => {
      state.q = e.target.value.trim();
      state.page = 1;
      loadReports();
    }, 300));
    $("filter-category").addEventListener("change", (e) => { state.category = e.target.value; state.page = 1; loadReports(); });
    $("filter-status").addEventListener("change", (e) => { state.status = e.target.value; state.page = 1; syncLedger(); loadReports(); });
    document.querySelectorAll(".ledger-cell").forEach((cell) => {
      cell.addEventListener("click", () => { state.status = cell.dataset.status; state.page = 1; syncLedger(); loadReports(); });
    });

    $("prev").addEventListener("click", () => { if (state.page > 1) { state.page -= 1; loadReports(); } });
    $("next").addEventListener("click", () => { if (state.page < state.pages) { state.page += 1; loadReports(); } });

    $("drawer-close").addEventListener("click", closeDrawer);
    $("backdrop").addEventListener("click", closeDrawer);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });
    $("status-form").addEventListener("submit", onSave);
    $("f-status").addEventListener("change", onStatusChange);
    $("f-message").addEventListener("input", (e) => { $("f-count").textContent = e.target.value.length; });

    if (token) showConsole(); else showLogin();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
