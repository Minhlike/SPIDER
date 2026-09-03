// SPIDER OSINT Platform V2.0 - Complete Client-Side Application Engine
// Intelligence-First, Vietnamese Default, 6-Tab Flow, Real-Time Provenance Trace

let currentView = "dashboard";
let currentCaseTab = "summary";
let currentCaseId = null;
let currentLanguage = localStorage.getItem("spider_lang") || "vi";
let currentTheme = localStorage.getItem("spider_theme") || "light";
let cyInstance = null;
let socket = null;
let classifyTimeout = null;
let currentCaseEntities = [];
let currentCaseObservations = [];
let casePollingInterval = null;

// --- 1. i18n Translation Dictionary ---
const i18n = {
  vi: {
    nav_dashboard: "Bảng điều khiển",
    nav_investigate: "Cuộc điều tra mới",
    nav_providers: "Trạng thái nguồn dữ liệu",
    status_connected: "Trực tuyến",
    theme_light: "Sáng",
    theme_dark: "Tối",
    settings_title: "Cài đặt hệ thống",
    kpi_cases: "Tổng số vụ điều tra",
    kpi_providers: "Nguồn dữ liệu sẵn sàng",
    kpi_entities: "Thực thể đã lưu trữ",
    kpi_observations: "Bằng chứng quan sát",
    recent_investigations: "Các cuộc điều tra gần đây",
    btn_new_case: "Tạo điều tra mới",
    col_case_name: "Tên vụ án",
    col_case_id: "Mã vụ án",
    col_status: "Trạng thái",
    col_created: "Thời gian tạo",
    col_actions: "Thao tác",
    new_inv_heading: "Bắt đầu điều tra OSINT đa nguồn",
    new_inv_subheading: "Hệ thống sẽ tự động phân loại mục tiêu, áp dụng chính sách thụ động an toàn và thu thập thông tin có chứng cứ.",
    lbl_target: "Mục tiêu điều tra (Tên miền, Email, IP, Tên người dùng, Số điện thoại...)",
    lbl_detected_type: "Loại nhận diện:",
    lbl_policy: "Hồ sơ an toàn mạng (Policy Profile)",
    lbl_depth: "Độ sâu thu thập (Max Depth)",
    lbl_timeout: "Thời gian tối đa (Timeout)",
    lbl_scope_confirm: "Mục tiêu nằm trong phạm vi được phép điều tra an toàn",
    btn_start: "Bắt đầu điều tra",
    btn_cancel: "Hủy bỏ",
    btn_refresh: "Làm mới",
    btn_export: "Xuất JSON",
    btn_delete: "Xóa vụ án",
    btn_save: "Lưu cài đặt",
    tab_summary: "Tổng quan",
    tab_live: "Tiến trình",
    tab_findings: "Phát hiện",
    tab_sources: "Nguồn dữ liệu",
    tab_evidence: "Bằng chứng",
    tab_graph: "Mạng liên kết",
    kpi_entities_found: "Thực thể phát hiện",
    kpi_assertions: "Mối quan hệ xác thực",
    kpi_sources_run: "Nguồn dữ liệu đã chạy",
    task_execution_progress: "Chi tiết thực thi tác vụ & Tiến trình thời gian thực",
    col_provider: "Nguồn (Provider)",
    col_capability: "Khả năng OSINT",
    col_target: "Mục tiêu",
    col_duration: "Thời gian",
    col_yield: "Quan sát thu được",
    col_details: "Chi tiết",
    col_canonical_val: "Giá trị chuẩn hóa",
    col_type: "Loại",
    col_obs_count: "Số quan sát",
    col_first_seen: "Lần đầu thấy",
    col_provider_id: "Mã nguồn",
    col_duration_ms: "Thời gian (ms)",
    col_obs_yield: "Đóng góp (Bằng chứng)",
    col_health_msg: "Chẩn đoán & Ghi chú",
    col_test: "Thử nghiệm trực tiếp",
    col_source: "Nguồn cụ thể",
    col_family: "Nhóm nguồn",
    col_confidence: "Độ tin cậy",
    providers_matrix_title: "Bảng chẩn đoán sức khỏe & Khả năng nguồn OSINT",
    col_version: "Phiên bản",
    col_capabilities: "Khả năng OSINT",
    col_net_class: "Cấp độ mạng",
    col_health_diagnostic: "Chẩn đoán sức khỏe",
    col_live_test: "Thử nghiệm",
    drawer_inspector_title: "Chi tiết nguồn gốc & Bằng chứng",
    setting_lang: "Ngôn ngữ giao diện",
    setting_theme: "Giao diện (Theme)",
    setting_default_profile: "Hồ sơ chính sách mạng mặc định",
    setting_max_depth: "Độ sâu mặc định (Max Depth)",
    setting_timeout: "Thời gian chờ mặc định (giây)",
    setting_api_keys: "Quản lý Khóa API (Tùy chọn - Lưu trữ cục bộ bảo mật)",
    empty_reason_heading: "Không tìm thấy thông tin bổ sung cho mục tiêu này",
    empty_reason_desc: "Các nguồn dữ liệu sau đã được thực thi nhưng không phát hiện thêm liên kết mới:",
    no_cases: "Chưa có cuộc điều tra nào. Nhấn 'Tạo điều tra mới' để bắt đầu.",
    loading: "Đang tải dữ liệu...",
    confirm_delete: "Bạn có chắc chắn muốn xóa cuộc điều tra này không?"
  },
  en: {
    nav_dashboard: "Dashboard",
    nav_investigate: "New Investigation",
    nav_providers: "Provider Health",
    status_connected: "Online",
    theme_light: "Light",
    theme_dark: "Dark",
    settings_title: "System Settings",
    kpi_cases: "Investigation Cases",
    kpi_providers: "Active Providers",
    kpi_entities: "Stored Entities",
    kpi_observations: "Observations",
    recent_investigations: "Recent Investigations",
    btn_new_case: "New Investigation",
    col_case_name: "Case Name",
    col_case_id: "Case ID",
    col_status: "Status",
    col_created: "Created At",
    col_actions: "Actions",
    new_inv_heading: "Start Multi-Source OSINT Investigation",
    new_inv_subheading: "The system automatically classifies targets, enforces safe passive policies, and gathers evidence-backed intelligence.",
    lbl_target: "Target Value (Domain, Email, IP, Username, Phone...)",
    lbl_detected_type: "Detected Type:",
    lbl_policy: "Network Safety Policy Profile",
    lbl_depth: "Max Recursion Depth",
    lbl_timeout: "Execution Timeout",
    lbl_scope_confirm: "Target is within authorized investigation scope",
    btn_start: "Start Investigation",
    btn_cancel: "Cancel",
    btn_refresh: "Refresh",
    btn_export: "Export JSON",
    btn_delete: "Delete Case",
    btn_save: "Save Settings",
    tab_summary: "Summary",
    tab_live: "Live Progress",
    tab_findings: "Findings",
    tab_sources: "Sources",
    tab_evidence: "Evidence",
    tab_graph: "Graph",
    kpi_entities_found: "Entities Discovered",
    kpi_assertions: "Materialized Assertions",
    kpi_sources_run: "Sources Executed",
    task_execution_progress: "Task Execution & Realtime Progress",
    col_provider: "Provider",
    col_capability: "OSINT Capability",
    col_target: "Target",
    col_duration: "Duration",
    col_yield: "Observations",
    col_details: "Details",
    col_canonical_val: "Canonical Value",
    col_type: "Type",
    col_obs_count: "Observations",
    col_first_seen: "First Seen",
    col_provider_id: "Provider ID",
    col_duration_ms: "Duration (ms)",
    col_obs_yield: "Yield (Evidence)",
    col_health_msg: "Diagnostic & Notes",
    col_test: "Live Test",
    col_source: "Upstream Source",
    col_family: "Source Family",
    col_confidence: "Confidence",
    providers_matrix_title: "Provider Diagnostics & Capabilities Matrix",
    col_version: "Version",
    col_capabilities: "Capabilities",
    col_net_class: "Network Class",
    col_health_diagnostic: "Health Diagnostic",
    col_live_test: "Test",
    drawer_inspector_title: "Evidence & Provenance Inspector",
    setting_lang: "Interface Language",
    setting_theme: "Theme",
    setting_default_profile: "Default Network Policy Profile",
    setting_max_depth: "Default Max Depth",
    setting_timeout: "Default Timeout (seconds)",
    setting_api_keys: "API Key Management (Optional - Securely Stored Locally)",
    empty_reason_heading: "No additional intelligence found for this target",
    empty_reason_desc: "The following sources executed but found no new observable links:",
    no_cases: "No investigations found. Click 'New Investigation' to begin.",
    loading: "Loading data...",
    confirm_delete: "Are you sure you want to delete this investigation?"
  }
};

function t(key) {
  const dict = i18n[currentLanguage] || i18n.vi;
  return dict[key] || key;
}

function applyTranslations() {
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    if (key && t(key)) {
      el.textContent = t(key);
    }
  });
  const langLabel = document.getElementById("lang-label");
  if (langLabel) langLabel.textContent = currentLanguage.toUpperCase();
  const themeLabel = document.getElementById("theme-label");
  if (themeLabel) themeLabel.textContent = currentTheme === "dark" ? t("theme_dark") : t("theme_light");
  const themeIcon = document.getElementById("theme-icon");
  if (themeIcon) themeIcon.innerHTML = currentTheme === "dark" ? "&#x1F319;" : "&#x2600;";
}

function toggleLanguage() {
  currentLanguage = currentLanguage === "vi" ? "en" : "vi";
  localStorage.setItem("spider_lang", currentLanguage);
  applyTranslations();
  if (currentView === "dashboard") loadDashboard();
  if (currentView === "providers") loadProviders();
  if (currentView === "case_detail" && currentCaseId) loadCaseDetail(currentCaseId);
}

function toggleTheme() {
  currentTheme = currentTheme === "light" ? "dark" : "light";
  localStorage.setItem("spider_theme", currentTheme);
  applyTheme();
}

function applyTheme() {
  if (currentTheme === "dark") {
    document.body.classList.add("dark-theme");
  } else {
    document.body.classList.remove("dark-theme");
  }
  applyTranslations();
  if (cyInstance) {
    cyInstance.style().update();
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function showNotification(msg) {
  const bar = document.getElementById("notification-bar");
  if (bar) {
    bar.textContent = msg;
    bar.style.display = "block";
    setTimeout(() => { bar.style.display = "none"; }, 4000);
  }
}

// --- 2. WebSocket Realtime Engine ---
function initWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws`;
  
  socket = new WebSocket(wsUrl);
  socket.onopen = () => {
    const ind = document.getElementById("ws-indicator");
    if (ind) ind.style.backgroundColor = "var(--accent-emerald)";
  };
  socket.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleRealtimeEvent(msg.event, msg.data);
    } catch (e) {
      console.error("WS parse error", e);
    }
  };
  socket.onclose = () => {
    const ind = document.getElementById("ws-indicator");
    if (ind) ind.style.backgroundColor = "var(--accent-rose)";
    setTimeout(initWebSocket, 3000);
  };
}

function handleRealtimeEvent(eventType, payload) {
  if (eventType === "RUN_STARTED") {
    showNotification(`Bắt đầu điều tra: ${payload.target || "mục tiêu"}`);
    if (currentView === "dashboard") loadDashboard();
    if (currentCaseId === payload.case_id) {
      document.getElementById("tab-live-badge").style.display = "inline-block";
      const statusBadge = document.getElementById("case-status-badge");
      if (statusBadge) {
        statusBadge.className = "badge badge-running";
        statusBadge.textContent = "RUNNING";
      }
      loadCaseProgress(currentCaseId);
    }
  } else if (eventType === "TASK_STARTED" || eventType === "TASK_COMPLETED") {
    if (currentCaseId === payload.case_id) {
      loadCaseProgress(currentCaseId);
    }
  } else if (eventType === "RUN_COMPLETED") {
    showNotification(`Điều tra hoàn tất!`);
    if (currentView === "dashboard") loadDashboard();
    if (currentCaseId === payload.case_id) {
      document.getElementById("tab-live-badge").style.display = "none";
      const statusBadge = document.getElementById("case-status-badge");
      if (statusBadge) {
        statusBadge.className = "badge badge-completed";
        statusBadge.textContent = "COMPLETED";
      }
      loadCaseDetail(currentCaseId);
    }
  }
}

// --- 3. View Switcher ---
function switchView(viewName) {
  currentView = viewName;
  document.querySelectorAll(".nav-item").forEach(el => el.classList.remove("active"));
  document.querySelectorAll(".view-panel").forEach(el => el.classList.remove("active"));
  
  const navEl = document.getElementById(`nav-${viewName}`);
  if (navEl) navEl.classList.add("active");
  
  const panelEl = document.getElementById(`view-${viewName}`);
  if (panelEl) panelEl.classList.add("active");

  const breadcrumb = document.getElementById("header-breadcrumb");
  if (viewName === "dashboard") {
    breadcrumb.textContent = t("nav_dashboard");
    loadDashboard();
  } else if (viewName === "investigate") {
    breadcrumb.textContent = t("nav_investigate");
    document.getElementById("target-input").value = "";
    document.getElementById("type-preview").textContent = "CHƯA XÁC ĐỊNH";
    document.getElementById("type-preview").className = "badge badge-running";
  } else if (viewName === "providers") {
    breadcrumb.textContent = t("nav_providers");
    loadProviders();
  }
}

// --- 4. Dashboard Loader ---
async function loadDashboard() {
  try {
    const [casesRes, providersRes] = await Promise.all([
      fetch("/api/cases").then(r => r.json()),
      fetch("/api/providers").then(r => r.json())
    ]);

    document.getElementById("kpi-cases").textContent = casesRes.length;
    let readyProviders = providersRes.filter(p => p.state === "READY").length;
    document.getElementById("kpi-providers").textContent = `${readyProviders}/${providersRes.length}`;

    let totalEntities = 0;
    let totalObservations = 0;

    const tbody = document.getElementById("recent-cases-tbody");
    tbody.innerHTML = "";

    if (casesRes.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-muted); padding:30px;">${escapeHtml(t("no_cases"))}</td></tr>`;
      document.getElementById("kpi-entities").textContent = "0";
      document.getElementById("kpi-observations").textContent = "0";
      return;
    }

    casesRes.slice(0, 10).forEach(c => {
      totalEntities += (c.metrics && c.metrics.entities) || 0;
      totalObservations += (c.metrics && c.metrics.observations) || 0;

      const tr = document.createElement("tr");
      const createdDate = c.created_at ? new Date(c.created_at).toLocaleString() : "-";
      tr.innerHTML = `
        <td><a href="#" onclick="openCase('${escapeHtml(c.id)}'); return false;" style="color:var(--accent-primary); font-weight:700;">${escapeHtml(c.name)}</a></td>
        <td><code>${escapeHtml(c.id.substring(0, 8))}</code></td>
        <td><span class="badge badge-${(c.status || "pending").toLowerCase()}">${escapeHtml(c.status || "PENDING")}</span></td>
        <td style="color:var(--text-muted);">${escapeHtml(createdDate)}</td>
        <td>
          <button class="btn btn-secondary" style="padding:4px 10px; font-size:12px;" onclick="openCase('${escapeHtml(c.id)}')">Xem chi tiết</button>
        </td>
      `;
      tbody.appendChild(tr);
    });

    document.getElementById("kpi-entities").textContent = totalEntities || "-";
    document.getElementById("kpi-observations").textContent = totalObservations || "-";
  } catch (err) {
    console.error("Failed to load dashboard", err);
  }
}

// --- 5. New Investigation Classifier & Start ---
function onTargetInputDebounced() {
  clearTimeout(classifyTimeout);
  const targetVal = document.getElementById("target-input").value.trim();
  const previewEl = document.getElementById("type-preview");

  if (!targetVal) {
    previewEl.textContent = "CHƯA XÁC ĐỊNH";
    previewEl.className = "badge badge-running";
    return;
  }

  classifyTimeout = setTimeout(async () => {
    try {
      const res = await fetch(`/api/classify?target=${encodeURIComponent(targetVal)}`);
      if (res.ok) {
        const data = await res.json();
        previewEl.textContent = data.type || "UNKNOWN";
        previewEl.className = "badge badge-success";
      } else {
        previewEl.textContent = "UNKNOWN";
        previewEl.className = "badge badge-missing";
      }
    } catch (e) {
      previewEl.textContent = "UNKNOWN";
    }
  }, 250);
}

async function startInvestigation() {
  const targetVal = document.getElementById("target-input").value.trim();
  if (!targetVal) {
    alert(currentLanguage === "vi" ? "Vui lòng nhập mục tiêu điều tra!" : "Please enter a target value!");
    return;
  }

  const profile = document.getElementById("profile-select").value;
  const depth = parseInt(document.getElementById("depth-select").value, 10);
  const timeout = parseInt(document.getElementById("timeout-select").value, 10);
  const isAuthorized = document.getElementById("authorized-checkbox").checked;

  const btn = document.getElementById("btn-start-investigate");
  btn.disabled = true;
  btn.innerHTML = `<span>&#x21BB;</span> ${currentLanguage === "vi" ? "Đang khởi tạo..." : "Initializing..."}`;

  try {
    const res = await fetch("/api/investigate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target: targetVal,
        policy_profile: profile,
        budget: {
          max_depth: depth,
          max_entities: 50,
          timeout_seconds: timeout
        },
        scope_authorized: isAuthorized
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Investigation dispatch failed");
    }

    const data = await res.json();
    currentCaseId = data.case_id;
    document.getElementById("case-status-badge").textContent = data.status;

    // Switch directly to Case Detail View on Live Progress Tab
    switchView("case_detail");
    switchCaseTab("live");
    document.getElementById("tab-live-badge").style.display = "inline-block";
    loadCaseDetail(currentCaseId);
    showNotification(currentLanguage === "vi" ? "Cuộc điều tra đã được gửi vào hàng đợi xử lý ngầm!" : "Investigation queued for background execution!");
  } catch (ex) {
    alert("Error: " + ex.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<span>&#x25B6;</span> <span>${escapeHtml(t("btn_start"))}</span>`;
  }
}

// --- 6. Case Detail & Tabs Management ---
function switchCaseTab(tabName) {
  currentCaseTab = tabName;
  document.querySelectorAll(".case-tab-btn").forEach(el => el.classList.remove("active"));
  document.querySelectorAll(".case-tab-content").forEach(el => el.classList.remove("active"));

  const btn = document.getElementById(`tab-btn-${tabName}`);
  if (btn) btn.classList.add("active");

  const content = document.getElementById(`case-tab-content-${tabName}`);
  if (content) content.classList.add("active");

  if (tabName === "graph" && currentCaseId) {
    loadKnowledgeGraph(currentCaseId);
  } else if (tabName === "sources" && currentCaseId) {
    loadCaseSources();
  } else if (tabName === "evidence" && currentCaseId) {
    loadCaseEvidence();
  } else if (tabName === "findings" && currentCaseId) {
    loadCaseFindings();
  }
}

function openCase(caseId) {
  currentView = "case_detail";
  currentCaseId = caseId;
  document.querySelectorAll(".view-panel").forEach(el => el.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach(el => el.classList.remove("active"));
  document.getElementById("view-case_detail").classList.add("active");
  document.getElementById("header-breadcrumb").textContent = `Vụ án #${caseId.substring(0, 8)}`;
  switchCaseTab("summary");
  loadCaseDetail(caseId);
}

function refreshCurrentCase() {
  if (currentCaseId) loadCaseDetail(currentCaseId);
}

async function loadCaseDetail(caseId) {
  try {
    const [caseRes, insightsRes] = await Promise.all([
      fetch(`/api/cases/${caseId}`).then(r => r.json()),
      fetch(`/api/cases/${caseId}/insights`).then(r => r.json())
    ]);

    // Header Info
    document.getElementById("case-title").textContent = caseRes.name || "Cuộc điều tra";
    const status = insightsRes.status || caseRes.status || "PENDING";
    const statusBadge = document.getElementById("case-status-badge");
    statusBadge.textContent = status;
    statusBadge.className = `badge badge-${status.toLowerCase()}`;

    const created = caseRes.created_at ? new Date(caseRes.created_at).toLocaleString() : "-";
    document.getElementById("case-meta").innerHTML = `
      <strong>ID:</strong> <code>${caseId}</code> | 
      <strong>Mục tiêu gốc:</strong> <code>${escapeHtml(insightsRes.target || "-")}</code> (${escapeHtml(insightsRes.target_type || "UNKNOWN")}) |
      <strong>Tạo lúc:</strong> ${escapeHtml(created)}
    `;

    // Metrics
    document.getElementById("sum-kpi-entities").textContent = insightsRes.entities_count || 0;
    document.getElementById("sum-kpi-assertions").textContent = insightsRes.assertions_count || 0;
    document.getElementById("sum-kpi-observations").textContent = insightsRes.observations_count || 0;
    document.getElementById("sum-kpi-sources").textContent = (insightsRes.provider_contributions || []).filter(p => p.tasks_count > 0).length;
    document.getElementById("findings-tab-count").textContent = insightsRes.entities_count || 0;
    document.getElementById("evidence-tab-count").textContent = insightsRes.observations_count || 0;

    // Render Type-Specific Intelligence or Empty Reason
    renderTypeSpecificInsights(insightsRes);

    // If still running, poll every 2 seconds
    if (status === "RUNNING" || status === "QUEUED" || status === "PENDING") {
      document.getElementById("tab-live-badge").style.display = "inline-block";
      if (!casePollingInterval) {
        casePollingInterval = setInterval(() => {
          if (currentCaseId === caseId && currentView === "case_detail") {
            loadCaseDetail(caseId);
          } else {
            clearInterval(casePollingInterval);
            casePollingInterval = null;
          }
        }, 2000);
      }
    } else {
      document.getElementById("tab-live-badge").style.display = "none";
      if (casePollingInterval) {
        clearInterval(casePollingInterval);
        casePollingInterval = null;
      }
    }

    loadCaseProgress(caseId);
  } catch (err) {
    console.error("Failed to load case detail", err);
  }
}

// Render Type Specific Intelligence Cards
function renderTypeSpecificInsights(insights) {
  const container = document.getElementById("type-specific-container");
  const emptyContainer = document.getElementById("empty-reason-container");
  container.innerHTML = "";
  emptyContainer.style.display = "none";

  const targetType = insights.target_type;
  const entitiesCount = insights.entities_count || 0;

  // If 0 findings and empty reason exists:
  if (entitiesCount <= 1 && insights.empty_reason?.is_empty && !["QUEUED", "RUNNING", "PENDING"].includes(insights.status)) {
    const sources = insights.provider_contributions || [];
    const r = {
      empty_sources: sources.filter(p => p.tasks_count > 0 && p.status === "NO_FINDINGS").map(p => p.provider_id),
      missing_credentials: sources.filter(p => p.credential_state === "MISSING_CREDENTIAL").map(p => p.provider_id)
    };
    emptyContainer.style.display = "block";
    emptyContainer.className = "empty-reason-card";
    emptyContainer.innerHTML = `
      <div class="empty-reason-title">
        <span>&#x26A0;</span> ${escapeHtml(t("empty_reason_heading"))}
      </div>
      <p style="font-size:13px; color:var(--text-secondary); margin-bottom:12px;">
        ${escapeHtml(t("empty_reason_desc"))}
      </p>
      <div class="card-grid-2">
        <div>
          <div class="detail-key" style="margin-bottom:6px;">Các nguồn đã thực thi (Kết quả rỗng):</div>
          <div class="chips-container">
            ${(r.empty_sources || []).map(s => `<span class="chip">${escapeHtml(s)}</span>`).join("") || "<em>Không có</em>"}
          </div>
        </div>
        <div>
          <div class="detail-key" style="margin-bottom:6px;">Nguồn thiếu cấu hình API Key:</div>
          <div class="chips-container">
            ${(r.missing_credentials || []).map(s => `<span class="chip" style="color:var(--accent-amber);">${escapeHtml(s)}</span>`).join("") || "<em>Không có</em>"}
          </div>
        </div>
      </div>
    `;
  }

  // A. EMAIL INTELLIGENCE CARD
  if (targetType === "EMAIL" && insights.email_insights) {
    const em = insights.email_insights;
    const card = document.createElement("div");
    card.className = "intelligence-card";
    card.innerHTML = `
      <div class="intelligence-card-header">
        <span class="intelligence-card-title">&#x2709; Phân tích Hạ tầng Email & Tên miền liên kết</span>
        <span class="badge badge-ready">EMAIL INTELLIGENCE</span>
      </div>
      <div class="card-grid-2">
        <div>
          <div class="detail-row">
            <span class="detail-key">Địa chỉ Email:</span>
            <span class="detail-val"><code>${escapeHtml(em.email || "-")}</code></span>
          </div>
          <div class="detail-row">
            <span class="detail-key">Tên miền trích xuất:</span>
            <span class="detail-val"><strong style="color:var(--accent-primary);">${escapeHtml(em.extracted_domain || "-")}</strong></span>
          </div>
          <div class="detail-row">
            <span class="detail-key">Bản ghi SPF:</span>
            <span class="detail-val"><small>${escapeHtml(em.spf_record || "Chưa phát hiện")}</small></span>
          </div>
          <div class="detail-row">
            <span class="detail-key">Bản ghi DMARC:</span>
            <span class="detail-val"><small>${escapeHtml(em.dmarc_record || "Chưa phát hiện")}</small></span>
          </div>
        </div>
        <div>
          <div class="detail-key">Máy chủ tiếp nhận thư (MX Hostnames):</div>
          <div class="chips-container">
            ${(em.mail_servers && em.mail_servers.length) ? em.mail_servers.map(m => `<span class="chip chip-primary">${escapeHtml(m)}</span>`).join("") : "<em>Chưa có máy chủ MX</em>"}
          </div>
          <div class="detail-key" style="margin-top:12px;">Địa chỉ IP máy chủ thư giải quyết được:</div>
          <div class="chips-container">
            ${(em.ip_addresses && em.ip_addresses.length) ? em.ip_addresses.map(ip => `<span class="chip">${escapeHtml(ip)}</span>`).join("") : "<em>Chưa có IP</em>"}
          </div>
        </div>
      </div>
    `;
    container.appendChild(card);
  }

  // B. DOMAIN INTELLIGENCE CARD
  if ((targetType === "DOMAIN" || targetType === "HOSTNAME" || (targetType === "EMAIL" && insights.domain_insights)) && insights.domain_insights) {
    const dom = insights.domain_insights;
    const card = document.createElement("div");
    card.className = "intelligence-card";
    card.innerHTML = `
      <div class="intelligence-card-header">
        <span class="intelligence-card-title">&#x1F310; Bản đồ Hạ tầng Tên miền & DNS</span>
        <span class="badge badge-ready">DOMAIN & DNS</span>
      </div>
      <div class="card-grid-3">
        <div>
          <div class="detail-key">Địa chỉ IP phân giải được:</div>
          <div class="chips-container">
            ${(dom.ip_addresses && dom.ip_addresses.length) ? dom.ip_addresses.map(ip => `<span class="chip chip-primary">${escapeHtml(ip)}</span>`).join("") : "<em>Không có IP</em>"}
          </div>
        </div>
        <div>
          <div class="detail-key">Máy chủ tên miền (Nameservers):</div>
          <div class="chips-container">
            ${(dom.nameservers && dom.nameservers.length) ? dom.nameservers.map(ns => `<span class="chip">${escapeHtml(ns)}</span>`).join("") : "<em>Không có NS</em>"}
          </div>
        </div>
        <div>
          <div class="detail-key">Máy chủ tiếp nhận thư (Mail Servers):</div>
          <div class="chips-container">
            ${(dom.mail_servers && dom.mail_servers.length) ? dom.mail_servers.map(mx => `<span class="chip">${escapeHtml(mx)}</span>`).join("") : "<em>Không có MX</em>"}
          </div>
        </div>
      </div>
      <div style="margin-top:16px;">
        <div class="detail-key">Tên miền phụ phát hiện được (Subdomains):</div>
        <div class="chips-container" style="max-height:120px; overflow-y:auto;">
          ${(dom.subdomains && dom.subdomains.length) ? dom.subdomains.map(s => `<span class="chip">${escapeHtml(s)}</span>`).join("") : "<em>Chưa phát hiện tên miền phụ</em>"}
        </div>
      </div>
    `;
    container.appendChild(card);
  }

  // C. IP & BGP INTELLIGENCE CARD
  if ((targetType === "IP_ADDRESS" || targetType === "IPV6_ADDRESS" || insights.ip_insights) && insights.ip_insights && insights.ip_insights.asn) {
    const ip = insights.ip_insights;
    const card = document.createElement("div");
    card.className = "intelligence-card";
    card.innerHTML = `
      <div class="intelligence-card-header">
        <span class="intelligence-card-title">&#x1F5A5; Thông tin Định tuyến BGP & Đăng ký Hạ tầng (RDAP)</span>
        <span class="badge badge-ready">ROUTING & REGISTRY</span>
      </div>
      <div class="card-grid-2">
        <div>
          <div class="detail-row">
            <span class="detail-key">Số hiệu mạng (ASN):</span>
            <span class="detail-val"><strong style="color:var(--accent-primary);">${escapeHtml(ip.asn || "-")}</strong></span>
          </div>
          <div class="detail-row">
            <span class="detail-key">Dải mạng (CIDR):</span>
            <span class="detail-val"><code>${escapeHtml(ip.cidr || "-")}</code></span>
          </div>
          <div class="detail-row">
            <span class="detail-key">Tổ chức quản lý (Org):</span>
            <span class="detail-val">${escapeHtml(ip.organization || "-")}</span>
          </div>
        </div>
        <div>
          <div class="detail-key">Tên máy chủ gắn với IP (Hostnames):</div>
          <div class="chips-container">
            ${(ip.associated_hostnames && ip.associated_hostnames.length) ? ip.associated_hostnames.map(h => `<span class="chip">${escapeHtml(h)}</span>`).join("") : "<em>Chưa có hostname gắn kết</em>"}
          </div>
        </div>
      </div>
    `;
    container.appendChild(card);
  }

  // D. USERNAME & ACCOUNTS CARD
  if (targetType === "USERNAME" && insights.username_insights) {
    const un = insights.username_insights;
    const card = document.createElement("div");
    card.className = "intelligence-card";
    card.innerHTML = `
      <div class="intelligence-card-header">
        <span class="intelligence-card-title">&#x1F464; Tài khoản mạng xã hội & Danh tính trực tuyến</span>
        <span class="badge badge-ready">ACCOUNT ENUMERATION</span>
      </div>
      <div>
        <div class="detail-key">Tài khoản & Hồ sơ tìm thấy:</div>
        <div class="chips-container" style="margin-top:10px;">
          ${(un.accounts && un.accounts.length) ? un.accounts.map(a => `
            <span class="chip chip-primary" style="display:inline-flex; align-items:center; gap:6px;">
              <span>&#x1F517;</span> <strong>${escapeHtml(a.platform)}:</strong> ${escapeHtml(a.account)}
            </span>
          `).join("") : "<em>Chưa phát hiện tài khoản trên các nền tảng kiểm tra</em>"}
        </div>
      </div>
    `;
    container.appendChild(card);
  }

  // E. PHONE INTELLIGENCE CARD
  if (targetType === "PHONE" && insights.phone_insights) {
    const ph = insights.phone_insights;
    const card = document.createElement("div");
    card.className = "intelligence-card";
    card.innerHTML = `
      <div class="intelligence-card-header">
        <span class="intelligence-card-title">&#x1F4DE; Phân tích Số điện thoại Viễn thông</span>
        <span class="badge badge-ready">TELECOM INTELLIGENCE</span>
      </div>
      <div class="card-grid-2">
        <div class="detail-row">
          <span class="detail-key">Số chuẩn E.164:</span>
          <span class="detail-val"><code>${escapeHtml(ph.phone || "-")}</code></span>
        </div>
        <div class="detail-row">
          <span class="detail-key">Quốc gia nhận diện:</span>
          <span class="detail-val"><strong>${escapeHtml(ph.country || "Chưa rõ")}</strong></span>
        </div>
      </div>
    `;
    container.appendChild(card);
  }
}

// --- 7. Tab 2: Live Progress Loader ---
async function loadCaseProgress(caseId) {
  try {
    const insightsRes = await fetch(`/api/cases/${caseId}/insights`).then(r => r.json());
    const tbody = document.getElementById("live-tasks-tbody");
    tbody.innerHTML = "";

    const tasks = insightsRes.provider_contributions || [];
    const runStatus = insightsRes.status || "PENDING";
    document.getElementById("live-run-status").textContent = runStatus;
    document.getElementById("live-run-status").className = `badge badge-${runStatus.toLowerCase()}`;

    if (tasks.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:var(--text-muted); padding:20px;">Đang chuẩn bị lập lịch các tác vụ OSINT...</td></tr>`;
      return;
    }

    tasks.forEach(t => {
      const tr = document.createElement("tr");
      const duration = t.duration_ms ? `${(t.duration_ms).toFixed(1)}ms` : "-";
      tr.innerHTML = `
        <td><strong>${escapeHtml(t.provider_id)}</strong></td>
        <td><code>BROAD_RECON</code></td>
        <td><code>${escapeHtml(insightsRes.target || "-")}</code></td>
        <td><span class="badge badge-${(t.status || "ready").toLowerCase()}">${escapeHtml(t.status || "READY")}</span></td>
        <td>${escapeHtml(duration)}</td>
        <td><strong>${escapeHtml(String(t.observations_count || 0))}</strong></td>
        <td><small style="color:var(--text-muted);">${escapeHtml(t.health_message || t.error || "Thực thi bình thường")}</small></td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Failed to load live progress", err);
  }
}

// --- 8. Tab 3: Findings Loader ---
async function loadCaseFindings() {
  if (!currentCaseId) return;
  try {
    currentCaseEntities = await fetch(`/api/cases/${currentCaseId}/entities`).then(r => r.json());
    renderFilteredFindings();
  } catch (e) {
    console.error("Failed to load findings", e);
  }
}

function renderFilteredFindings() {
  const filterType = document.getElementById("findings-filter-type").value;
  const search = document.getElementById("findings-search").value.toLowerCase();
  const tbody = document.getElementById("findings-tbody");
  tbody.innerHTML = "";

  const filtered = currentCaseEntities.filter(e => {
    if (filterType && e.type !== filterType) return false;
    if (search && !e.canonical_name.toLowerCase().includes(search)) return false;
    return true;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-muted); padding:20px;">Không có thực thể nào khớp bộ lọc.</td></tr>`;
    return;
  }

  filtered.forEach(e => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${escapeHtml(e.canonical_name)}</strong></td>
      <td><span class="badge badge-ready">${escapeHtml(e.type)}</span></td>
      <td>${escapeHtml(String(e.observation_count || 1))}</td>
      <td style="color:var(--text-muted);">${e.first_seen ? new Date(e.first_seen).toLocaleString() : "-"}</td>
      <td>
        <button class="btn btn-secondary" style="padding:4px 8px; font-size:12px;" onclick="openNodeInspector('${escapeHtml(e.id)}')">
          &#x1F50D; Nguồn gốc
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// --- 9. Tab 4: Sources Loader ---
async function loadCaseSources() {
  if (!currentCaseId) return;
  try {
    const insights = await fetch(`/api/cases/${currentCaseId}/insights`).then(r => r.json());
    const tbody = document.getElementById("sources-tbody");
    tbody.innerHTML = "";

    const list = insights.provider_contributions || [];
    if (list.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:20px;">Chưa có thông tin đóng góp từ nguồn.</td></tr>`;
      return;
    }

    list.forEach(p => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(p.provider_id)}</strong></td>
        <td><span class="badge badge-${(p.status || "ready").toLowerCase()}">${escapeHtml(p.status || "READY")}</span></td>
        <td>${p.duration_ms ? p.duration_ms.toFixed(1) : "-"}</td>
        <td><strong>${escapeHtml(String(p.observations_count || 0))}</strong></td>
        <td><small style="color:var(--text-muted);">${escapeHtml(p.health_message || "Sẵn sàng")}</small></td>
        <td>
          <button class="btn btn-secondary" style="padding:4px 8px; font-size:11.5px;" onclick="testProviderLive('${escapeHtml(p.provider_id)}')">
            &#x25B6; Thử nghiệm
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error("Failed to load sources", e);
  }
}

// --- 10. Tab 5: Evidence Loader ---
async function loadCaseEvidence() {
  if (!currentCaseId) return;
  try {
    currentCaseObservations = await fetch(`/api/cases/${currentCaseId}/observations`).then(r => r.json());
    const tbody = document.getElementById("evidence-tbody");
    tbody.innerHTML = "";

    if (currentCaseObservations.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:var(--text-muted); padding:20px;">Chưa có bản ghi quan sát nào được lưu.</td></tr>`;
      return;
    }

    currentCaseObservations.slice(0, 100).forEach(o => {
      const tr = document.createElement("tr");
      const val = o.canonical_value || o.observable_value || "-";
      const created = o.created_at ? new Date(o.created_at).toLocaleTimeString() : "-";
      tr.innerHTML = `
        <td><code>${escapeHtml(val)}</code></td>
        <td><span class="badge badge-ready">${escapeHtml(o.observable_type || "-")}</span></td>
        <td><strong>${escapeHtml(o.upstream_source || o.provider_id || "-")}</strong></td>
        <td><small>${escapeHtml(o.upstream_family || "-")}</small></td>
        <td><strong>${(o.confidence * 100).toFixed(0)}%</strong></td>
        <td style="color:var(--text-muted);">${escapeHtml(created)}</td>
        <td>
          <button class="btn btn-secondary" style="padding:3px 8px; font-size:11.5px;" onclick="inspectObservationJson('${escapeHtml(o.id)}')">
            &#x1F4C4; Dữ liệu thô
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error("Failed to load evidence", e);
  }
}

// --- 11. Tab 6: Cytoscape Knowledge Graph ---
async function loadKnowledgeGraph(caseId) {
  if (!caseId) return;
  const container = document.getElementById("cy-container");
  if (!container) return;

  const filterType = document.getElementById("filter-entity-type").value;
  const minConf = parseFloat(document.getElementById("filter-min-conf").value || "0.0");
  const search = (document.getElementById("filter-search").value || "").toLowerCase();

  const badge = document.getElementById("graph-node-count-badge");
  badge.textContent = "Đang tải...";

  try {
    const data = await fetch(`/api/cases/${caseId}/graph`).then(r => r.json());
    let nodes = (data.elements || []).filter(element => element.group === "nodes");
    let edges = (data.elements || []).filter(element => element.group === "edges");

    // Filter nodes
    if (filterType) nodes = nodes.filter(n => n.data.type === filterType);
    if (search) nodes = nodes.filter(n => (n.data.label || "").toLowerCase().includes(search));

    const validNodeIds = new Set(nodes.map(n => n.data.id));
    edges = edges.filter(e => validNodeIds.has(e.data.source) && validNodeIds.has(e.data.target));
    if (minConf > 0) edges = edges.filter(e => (e.data.confidence || 1.0) >= minConf);

    badge.textContent = `${nodes.length} thực thể, ${edges.length} liên kết`;

    if (cyInstance) {
      cyInstance.destroy();
    }

    const isDark = document.body.classList.contains("dark-theme");

    cyInstance = cytoscape({
      container: container,
      elements: { nodes: nodes, edges: edges },
      style: [
        {
          selector: "node",
          style: {
            "label": "data(label)",
            "font-size": "11px",
            "text-valign": "bottom",
            "text-margin-y": 5,
            "color": isDark ? "#f8fafc" : "#0f172a",
            "background-color": isDark ? "#06b6d4" : "#0284c7",
            "width": 24,
            "height": 24,
            "border-width": 2,
            "border-color": isDark ? "#38bdf8" : "#0369a1"
          }
        },
        {
          selector: 'node[type = "DOMAIN"]',
          style: { "background-color": "#2563eb", "border-color": "#1d4ed8", "width": 28, "height": 28 }
        },
        {
          selector: 'node[type = "IP_ADDRESS"], node[type = "IPV6_ADDRESS"]',
          style: { "background-color": "#10b981", "border-color": "#059669" }
        },
        {
          selector: 'node[type = "EMAIL"]',
          style: { "background-color": "#f59e0b", "border-color": "#d97706" }
        },
        {
          selector: 'node[type = "ACCOUNT"]',
          style: { "background-color": "#8b5cf6", "border-color": "#7c3aed" }
        },
        {
          selector: "edge",
          style: {
            "width": 1.5,
            "line-color": isDark ? "#334155" : "#cbd5e1",
            "target-arrow-color": isDark ? "#334155" : "#cbd5e1",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            "label": "data(label)",
            "font-size": "9px",
            "color": isDark ? "#94a3b8" : "#64748b",
            "text-rotation": "autorotate"
          }
        },
        {
          selector: ":selected",
          style: {
            "border-width": 3,
            "border-color": "#f43f5e",
            "line-color": "#f43f5e",
            "target-arrow-color": "#f43f5e"
          }
        }
      ],
      layout: {
        name: nodes.length <= 1 ? "grid" : "cose",
        animate: false,
        padding: 40,
        nodeOverlap: 20
      }
    });

    cyInstance.on("tap", "node", (evt) => {
      const node = evt.target;
      openNodeInspector(node.data("id"));
    });
  } catch (err) {
    console.error("Failed to render graph", err);
    badge.textContent = "Lỗi kết nối đồ thị";
  }
}

function redoGraphLayout() {
  if (cyInstance) {
    const layout = cyInstance.layout({ name: "cose", animate: true, animationDuration: 400 });
    layout.run();
  }
}

// --- 12. Inspector Drawer (Provenance & Evidence) ---
async function openNodeInspector(entityId) {
  const drawer = document.getElementById("side-drawer");
  const content = document.getElementById("drawer-content");
  content.innerHTML = `<div style="text-align:center; padding:30px; color:var(--text-muted);">${escapeHtml(t("loading"))}</div>`;
  drawer.classList.add("open");

  try {
    const res = await fetch(`/api/explain?case_id=${currentCaseId}&entity_id=${entityId}`);
    if (!res.ok) throw new Error("Could not fetch provenance trace");
    const data = await res.json();

    content.innerHTML = `
      <div style="margin-bottom:18px;">
        <span class="badge badge-ready">${escapeHtml(data.entity.type)}</span>
        <h3 style="font-size:18px; font-weight:800; margin-top:8px; word-break:break-all;">${escapeHtml(data.entity.canonical_name)}</h3>
        <p style="font-size:12px; color:var(--text-muted); margin-top:4px;">ID: <code>${escapeHtml(data.entity.id)}</code></p>
      </div>

      <div class="intelligence-card" style="padding:14px; margin-bottom:16px;">
        <div class="intelligence-card-title" style="margin-bottom:10px; font-size:13.5px;">&#x1F4CA; Thống kê & Nguồn gốc</div>
        <div class="detail-row">
          <span class="detail-key">Số lần được quan sát:</span>
          <span class="detail-val">${escapeHtml(String(data.entity.observation_count || 1))} lần</span>
        </div>
        <div class="detail-row">
          <span class="detail-key">Lần đầu ghi nhận:</span>
          <span class="detail-val">${data.entity.first_seen ? new Date(data.entity.first_seen).toLocaleString() : "-"}</span>
        </div>
      </div>

      <h4 style="font-size:14px; font-weight:700; margin-bottom:10px;">Dấu vết bằng chứng (${(data.provenance_chain || []).length}):</h4>
      <div style="display:flex; flex-direction:column; gap:10px;">
        ${(data.provenance_chain || []).map(p => `
          <div style="background:var(--bg-card); border:1px solid var(--border-color); border-radius:6px; padding:12px; font-size:12.5px;">
            <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
              <strong style="color:var(--accent-primary);">${escapeHtml(p.upstream_source || p.provider_id)}</strong>
              <span class="badge badge-running">${escapeHtml(p.upstream_family || "OSINT")}</span>
            </div>
            <div style="color:var(--text-muted); font-size:11.5px; margin-bottom:6px;">Task ID: <code>${escapeHtml(p.task_id ? p.task_id.substring(0, 8) : "-")}</code></div>
            <div style="font-size:12px;">Độ tin cậy: <strong>${(p.confidence * 100).toFixed(0)}%</strong></div>
          </div>
        `).join("") || "<p style='color:var(--text-muted);'>Không có chuỗi dấu vết bổ sung.</p>"}
      </div>
    `;
  } catch (e) {
    content.innerHTML = `<div style="color:var(--accent-rose); padding:20px;">Lỗi: ${escapeHtml(e.message)}</div>`;
  }
}

function inspectObservationJson(obsId) {
  const obs = currentCaseObservations.find(o => o.id === obsId);
  if (!obs) return;

  const drawer = document.getElementById("side-drawer");
  const content = document.getElementById("drawer-content");
  content.innerHTML = `
    <div style="margin-bottom:16px;">
      <span class="badge badge-ready">${escapeHtml(obs.observable_type)}</span>
      <h3 style="font-size:16px; font-weight:800; margin-top:8px;">Bản ghi Quan sát Thô</h3>
      <p style="font-size:12px; color:var(--text-muted);">Mã: <code>${escapeHtml(obs.id)}</code></p>
    </div>
    <pre style="background:var(--bg-primary); border:1px solid var(--border-color); border-radius:6px; padding:12px; font-size:12px; overflow:auto; max-height:75vh; font-family:monospace;">${escapeHtml(JSON.stringify(obs, null, 2))}</pre>
  `;
  drawer.classList.add("open");
}

function closeDrawer() {
  document.getElementById("side-drawer").classList.remove("open");
}

// --- 13. Provider Health View Loader & Live Testing ---
async function loadProviders() {
  try {
    const providers = await fetch("/api/providers").then(r => r.json());
    const tbody = document.getElementById("providers-tbody");
    tbody.innerHTML = "";

    providers.forEach(p => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(p.id)}</strong></td>
        <td><code>${escapeHtml(p.version)}</code></td>
        <td><span class="badge badge-${p.state.toLowerCase()}">${escapeHtml(p.state)}</span></td>
        <td>${p.capabilities.map(c => `<span class="chip" style="font-size:11px;">${escapeHtml(c)}</span>`).join(" ")}</td>
        <td><code>${escapeHtml(p.network_class)}</code></td>
        <td><small style="color:var(--text-muted);">${escapeHtml(p.health_message)}</small></td>
        <td>
          <button class="btn btn-secondary" style="padding:4px 10px; font-size:11.5px;" onclick="testProviderLive('${escapeHtml(p.id)}')">
            &#x25B6; ${escapeHtml(t("col_test"))}
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Failed to load providers", err);
  }
}

async function testProviderLive(providerId) {
  showNotification(currentLanguage === "vi" ? `Đang kiểm tra kết nối với ${providerId}...` : `Testing ${providerId}...`);
  try {
    const res = await fetch(`/api/providers/${providerId}/test`, { method: "POST" });
    const data = await res.json();
    alert(`[${providerId}] Trạng thái: ${data.state}
Chẩn đoán: ${data.message}`);
    if (currentView === "providers") loadProviders();
  } catch (e) {
    alert(`Lỗi kiểm tra [${providerId}]: ${e.message}`);
  }
}

// --- 14. Settings Modal Engine ---
async function openSettingsModal() {
  const modal = document.getElementById("settings-modal");
  modal.classList.add("open");

  try {
    const s = await fetch("/api/settings").then(r => r.json());
    document.getElementById("setting-language").value = s.language || currentLanguage;
    document.getElementById("setting-theme").value = s.theme || currentTheme;
    document.getElementById("setting-profile").value = s.default_policy_profile || "passive_standard";
    document.getElementById("setting-depth").value = s.max_depth !== undefined ? s.max_depth : 1;
    document.getElementById("setting-timeout").value = s.timeout_seconds || 60;
  } catch (e) {
    console.error("Failed to load settings", e);
  }
}

function closeSettingsModal() {
  document.getElementById("settings-modal").classList.remove("open");
}

async function saveSettings() {
  const lang = document.getElementById("setting-language").value;
  const theme = document.getElementById("setting-theme").value;
  const profile = document.getElementById("setting-profile").value;
  const depth = parseInt(document.getElementById("setting-depth").value, 10);
  const timeout = parseInt(document.getElementById("setting-timeout").value, 10);

  const shodanKey = document.getElementById("setting-key-shodan").value.trim();
  const censysKey = document.getElementById("setting-key-censys").value.trim();
  const fofaKey = document.getElementById("setting-key-fofa").value.trim();

  const apiKeys = {};
  if (shodanKey) apiKeys["SHODAN"] = shodanKey;
  if (censysKey) apiKeys["CENSYS"] = censysKey;
  if (fofaKey) apiKeys["FOFA"] = fofaKey;

  try {
    const response = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        language: lang,
        theme: theme,
        default_policy_profile: profile,
        max_depth: depth,
        timeout_seconds: timeout,
        api_keys: apiKeys
      })
    });

    if (!response.ok) throw new Error("Không thể lưu cài đặt bảo mật");
    currentLanguage = lang;
    currentTheme = theme;
    localStorage.setItem("spider_lang", lang);
    localStorage.setItem("spider_theme", theme);
    applyTheme();
    closeSettingsModal();
    showNotification(currentLanguage === "vi" ? "Đã lưu cài đặt thành công!" : "Settings saved successfully!");
  } catch (e) {
    alert("Error saving settings: " + e.message);
  } finally {
    ["shodan", "censys", "fofa"].forEach(key => {
      document.getElementById(`setting-key-${key}`).value = "";
    });
  }
}

// --- 15. Export & Delete Actions ---
async function exportCaseData() {
  if (!currentCaseId) return;
  try {
    const [caseData, entities, assertions, observations] = await Promise.all([
      fetch(`/api/cases/${currentCaseId}`).then(r => r.json()),
      fetch(`/api/cases/${currentCaseId}/entities`).then(r => r.json()),
      fetch(`/api/cases/${currentCaseId}/assertions`).then(r => r.json()),
      fetch(`/api/cases/${currentCaseId}/observations`).then(r => r.json())
    ]);

    const fullExport = {
      case: caseData,
      entities: entities,
      assertions: assertions,
      observations: observations,
      exported_at: new Date().toISOString()
    };

    const blob = new Blob([JSON.stringify(fullExport, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `SPIDER_CASE_${currentCaseId.substring(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    alert("Export failed: " + e.message);
  }
}

async function deleteCurrentCase() {
  if (!currentCaseId) return;
  if (!confirm(t("confirm_delete"))) return;

  try {
    await fetch(`/api/cases/${currentCaseId}`, { method: "DELETE" });
    showNotification(currentLanguage === "vi" ? "Đã xóa vụ án thành công!" : "Case deleted successfully!");
    switchView("dashboard");
  } catch (e) {
    alert("Delete failed: " + e.message);
  }
}

// --- 16. App Bootstrap ---
window.addEventListener("DOMContentLoaded", () => {
  applyTheme();
  applyTranslations();
  initWebSocket();
  loadDashboard();
});
