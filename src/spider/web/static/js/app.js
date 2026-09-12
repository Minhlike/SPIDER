// SPIDER OSINT Platform V2.0 - Complete Client-Side Application Engine
// Intelligence-First, Vietnamese Default, 6-Tab Flow, Real-Time Provenance Trace

let currentView = "dashboard";
let currentCaseTab = "summary";
let currentCaseId = null;
let currentRunId = null;
let currentLanguage = localStorage.getItem("spider_lang") || "vi";
let currentTheme = localStorage.getItem("spider_theme") || "light";
let cyInstance = null;
let socket = null;
let classifyTimeout = null;
let classificationSequence = 0;
let classificationController = null;
let currentCaseEntities = [];
let currentCaseObservations = [];
let casePollingInterval = null;

// --- 1. i18n Translation Dictionary ---
const i18n = {
  vi: {
    target_type_label: "Bạn muốn tìm theo",
    target_type_auto: "Tự nhận diện",
    target_type_phone: "Số điện thoại (+mã quốc gia)",
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
    lbl_request_budget: "Giới hạn yêu cầu mạng",
    unbounded_hint: "Không giới hạn vẫn tuân thủ rate limit, quota, timeout từng nguồn, chống lặp và nút dừng.",
    lbl_scope_confirm: "Mục tiêu nằm trong phạm vi được phép điều tra an toàn",
    btn_start: "Bắt đầu điều tra tự động",
    btn_cancel: "Hủy bỏ",
    btn_refresh: "Làm mới",
    btn_export: "Dữ liệu JSON",
    btn_reader_report: "Tải báo cáo dễ đọc",
    btn_delete: "Xóa vụ án",
    btn_save: "Lưu cài đặt",
    btn_shutdown: "Tắt SPIDER",
    btn_stop_run: "Dừng lượt điều tra",
    btn_resume_run: "Tiếp tục lượt điều tra",
    tab_summary: "Tổng quan",
    tab_live: "Tiến trình",
    tab_findings: "Phát hiện",
    tab_sources: "Nguồn dữ liệu",
    tab_evidence: "Bằng chứng",
    tab_graph: "Mạng liên kết",
    kpi_entities_found: "Thực thể phát hiện",
    kpi_assertions: "Liên kết có bằng chứng",
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
    col_confidence: "Cách đánh giá",
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
    confirm_delete: "Bạn có chắc chắn muốn xóa cuộc điều tra này không?",
    confirm_shutdown: "Tắt SPIDER an toàn? Các tác vụ đang chạy sẽ được dừng theo quy trình shutdown."
  },
  en: {
    target_type_label: "Search as",
    target_type_auto: "Detect automatically",
    target_type_phone: "Phone (+country code)",
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
    lbl_request_budget: "Network request limit",
    unbounded_hint: "Unlimited still respects rate limits, quotas, per-source timeouts, loop detection, and Stop.",
    lbl_scope_confirm: "Target is within authorized investigation scope",
    btn_start: "Start automatic investigation",
    btn_cancel: "Cancel",
    btn_refresh: "Refresh",
    btn_export: "JSON data",
    btn_reader_report: "Download readable report",
    btn_delete: "Delete Case",
    btn_save: "Save Settings",
    btn_shutdown: "Stop SPIDER",
    btn_stop_run: "Stop investigation run",
    btn_resume_run: "Resume investigation run",
    tab_summary: "Summary",
    tab_live: "Live Progress",
    tab_findings: "Findings",
    tab_sources: "Sources",
    tab_evidence: "Evidence",
    tab_graph: "Graph",
    kpi_entities_found: "Entities Discovered",
    kpi_assertions: "Evidence-backed links",
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
    col_confidence: "Assessment",
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
    confirm_delete: "Are you sure you want to delete this investigation?",
    confirm_shutdown: "Stop SPIDER safely? Running tasks will follow the normal shutdown procedure."
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

function updateRunControls(status, resumable = false) {
  const button = document.getElementById("btn-stop-run");
  const resume = document.getElementById("btn-resume-run");
  if (!button || !resume) return;
  button.style.display = currentRunId && ["QUEUED", "RUNNING", "PENDING"].includes(status)
    ? "inline-flex" : "none";
  button.disabled = false;
  resume.style.display = currentRunId && resumable ? "inline-flex" : "none";
  resume.disabled = false;
}

async function stopCurrentRun() {
  if (!currentRunId) return;
  const button = document.getElementById("btn-stop-run");
  if (button) button.disabled = true;
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(currentRunId)}/stop`, {
      method: "POST"
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail?.message || "Stop failed");
    updateRunControls(result.status);
    showNotification(currentLanguage === "vi"
      ? "Đã dừng lượt điều tra; bằng chứng đã ghi nhận vẫn được giữ."
      : "Investigation stopped; committed evidence was retained.");
    if (currentCaseId) await loadCaseDetail(currentCaseId);
  } catch (_) {
    if (button) button.disabled = false;
    showNotification(currentLanguage === "vi"
      ? "Không dừng được lượt này; trạng thái chưa được thay đổi."
      : "This run could not be stopped; its state was not changed.");
  }
}

async function resumeCurrentRun() {
  if (!currentRunId) return;
  const priorRunId = currentRunId;
  const button = document.getElementById("btn-resume-run");
  if (button) button.disabled = true;
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(priorRunId)}/resume`, {
      method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail?.message || "Resume failed");
    currentRunId = result.run_id;
    updateRunControls(result.status, false);
    showNotification(currentLanguage === "vi"
      ? "Đã tiếp tục từ checkpoint; công việc đã hoàn tất sẽ không tự chạy lại."
      : "Resumed from checkpoint; completed work will not be replayed automatically.");
    if (currentCaseId) await loadCaseDetail(currentCaseId);
  } catch (_) {
    if (button) button.disabled = false;
    showNotification(currentLanguage === "vi"
      ? "Checkpoint này không thể tiếp tục."
      : "This checkpoint could not be resumed.");
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
      currentRunId = payload.run_id || currentRunId;
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
    const finalStatus = payload.run_result?.status || "COMPLETED";
    showNotification(finalStatus === "COMPLETED" ? "Điều tra hoàn tất" : `Điều tra kết thúc: ${finalStatus}`);
    if (currentView === "dashboard") loadDashboard();
    if (currentCaseId === payload.case_id) {
      document.getElementById("tab-live-badge").style.display = "none";
      const statusBadge = document.getElementById("case-status-badge");
      if (statusBadge) {
        statusBadge.className = `badge badge-${finalStatus.toLowerCase()}`;
        statusBadge.textContent = finalStatus;
      }
      updateRunControls(finalStatus);
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
    onTargetInputDebounced();
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

let reportVocabulary = {};
async function loadReportVocabulary() {
  try {
    const response = await fetch("/api/report-vocabulary");
    if (response.ok) reportVocabulary = await response.json();
  } catch (_) { /* The safe fallback states uncertainty without exposing codes. */ }
}
function friendlyLabel(code) {
  return reportVocabulary[currentLanguage]?.[code] ||
    (currentLanguage === "vi" ? "Chưa đủ thông tin để kết luận" : "Not enough information to conclude");
}
function renderReaderReport(insights) {
  const box = document.getElementById("reader-report");
  const report = insights.reader_report?.[currentLanguage];
  box.replaceChildren();
  if (!report) return;
  const heading = document.createElement("h3");
  heading.textContent = report.title;
  const conclusion = document.createElement("p");
  conclusion.textContent = report.conclusion;
  box.append(heading, conclusion);
  for (const section of report.sections) {
    const title = document.createElement("h4");
    title.textContent = section.title;
    const list = document.createElement("ul");
    for (const text of section.items) {
      const item = document.createElement("li");
      item.textContent = text;
      list.appendChild(item);
    }
    box.append(title, list);
  }
}

// --- 5. New Investigation Classifier & Start ---
let inputCatalogue = null;
let inputCatalogueRequest = null;
async function loadInputCatalogue() {
  if (inputCatalogue) return inputCatalogue;
  if (inputCatalogueRequest) return inputCatalogueRequest;
  inputCatalogueRequest = (async () => {
    const status = document.getElementById("input-support-status");
    try {
      const response = await fetch("/api/input-catalogue");
      const data = await response.json();
      if (!response.ok || !Array.isArray(data.inputs)) throw new Error("unavailable");
      inputCatalogue = new Map(data.inputs.map(item => [item.type, item]));
      const unsupported = [];
      for (const option of document.getElementById("target-type-select").options) {
        if (!option.value) continue;
        option.disabled = inputCatalogue.get(option.value)?.supported !== true;
        if (option.disabled) unsupported.push(option.value);
      }
      status.textContent = unsupported.length ? (currentLanguage === "vi"
        ? `Chưa có luồng thu thập khả dụng: ${unsupported.join(", ")}. Các lựa chọn này đang tắt.`
        : `No available collection workflow: ${unsupported.join(", ")}. These options are disabled.`) : "";
      return inputCatalogue;
    } catch (_) {
      status.textContent = currentLanguage === "vi"
        ? "Chưa đọc được năng lực backend. Hãy thử lại trước khi bắt đầu điều tra."
        : "Backend capabilities unavailable. Retry before starting an investigation.";
      return null;
    } finally { inputCatalogueRequest = null; }
  })();
  return inputCatalogueRequest;
}

function classificationExplanation(data) {
  const vi = currentLanguage === "vi";
  if (data.needs_confirmation) {
    return data.reason === "numeric_identifier"
      ? (vi ? "Chuỗi số có thể là username hoặc số điện thoại. Hãy chọn loại; số Việt Nam được chuẩn hóa về +84." : "Digits may identify a username or a phone. Choose a type; Vietnamese numbers normalize to +84.")
      : (vi ? "Chuỗi này có thể là tên miền hoặc username. Hãy chọn loại trước khi điều tra." : "This could be a domain or a username. Choose a type before investigating.");
  }
  if (data.reason === "unknown_suffix") return vi
    ? "Gợi ý username: dấu chấm không đủ để xác định tên miền. Hậu tố này không có trong danh sách công khai ngoại tuyến; nếu là máy chủ nội bộ, hãy chọn Hostname."
    : "Username suggested: a dot alone does not identify a domain. This suffix is absent from the offline public list; choose Hostname for an internal host.";
  if (data.decision_source === "explicit") return vi ? "Sẽ dùng loại bạn đã chỉ định. Điều này chưa xác minh chủ sở hữu." : "Your selected type will be used. This does not verify ownership.";
  return vi ? "Nhận diện dựa trên định dạng, chưa xác minh tài khoản hoặc chủ sở hữu. Có thể chọn lại loại ở trên." : "Detected from syntax; account existence and ownership are unverified. You can change the type above.";
}

function onTargetInputDebounced(resetType = true) {
  clearTimeout(classifyTimeout);
  classificationSequence++;
  if (classificationController) classificationController.abort();
  if (resetType) document.getElementById("target-type-select").value = "";
  document.getElementById("type-preview").textContent = currentLanguage === "vi" ? "CHƯA XÁC ĐỊNH" : "UNCLASSIFIED";
  document.getElementById("type-preview").className = "badge badge-running";
  document.getElementById("classification-explanation").textContent = "";
  document.getElementById("source-preflight").textContent = "";
  document.getElementById("btn-browser-investigate").style.display = "none";
  if (document.getElementById("target-input").value.trim()) {
    classifyTimeout = setTimeout(classifyCurrentTarget, 250);
  }
}

async function onTargetTypeChanged() {
  const selected = document.getElementById("target-type-select").value;
  const target = document.getElementById("target-input");
  const status = document.getElementById("public-ip-status");
  if (["IP_ADDRESS", "IPV6_ADDRESS"].includes(selected) && !target.value.trim()) {
    status.textContent = currentLanguage === "vi" ? "Đang xác định IP công khai hiện tại..." : "Detecting the current public IP...";
    try {
      const version = selected === "IPV6_ADDRESS" ? 6 : 4;
      const response = await fetch(`/api/network/public-address?version=${version}`);
      const data = await response.json();
      if (!response.ok || !data.ip) throw new Error(data.detail?.code || "UNAVAILABLE");
      if (document.getElementById("target-type-select").value !== selected || target.value.trim()) return;
      target.value = data.ip;
      status.textContent = currentLanguage === "vi"
        ? `Đã điền IPv${version} công khai từ WhatIsMyIP; hãy kiểm tra rồi bấm bắt đầu.`
        : `Public IPv${version} filled from WhatIsMyIP; review it before starting.`;
    } catch (_) {
      status.textContent = currentLanguage === "vi"
        ? "Không xác định được IP công khai. Bạn vẫn có thể nhập IP thủ công."
        : "The public IP could not be detected. You can still enter it manually.";
    }
  } else {
    status.textContent = "";
  }
  onTargetInputDebounced(false);
}

async function classifyCurrentTarget(browserAssisted = true) {
  clearTimeout(classifyTimeout);
  const sequence = ++classificationSequence;
  if (classificationController) classificationController.abort();
  classificationController = new AbortController();
  const preview = document.getElementById("type-preview");
  const explanation = document.getElementById("classification-explanation");
  const preflight = document.getElementById("source-preflight");
  try {
    const res = await fetch("/api/classify", {
      method: "POST", headers: {"Content-Type": "application/json"},
      signal: classificationController.signal,
      body: JSON.stringify({target: document.getElementById("target-input").value.trim(),
        target_type: document.getElementById("target-type-select").value || null,
        investigation_mode: document.getElementById("investigation-mode-select").value,
        browser_assisted: browserAssisted})
    });
    const data = await res.json();
    if (sequence !== classificationSequence) return null;
    if (!res.ok) throw new Error("invalid_target");
    preview.textContent = data.type;
    preview.className = data.needs_confirmation ? "badge badge-running" : "badge badge-success";
    document.getElementById("btn-browser-investigate").style.display =
      (!data.needs_confirmation && ["USERNAME", "EMAIL"].includes(data.type)) ? "inline-flex" : "none";
    explanation.textContent = classificationExplanation(data);
    const sourcePlan = data.source_preflight || {};
    const ready = (sourcePlan.sources || []).filter(s => s.applicability !== "NOT_APPLICABLE" && s.request_accounting === "SUPPORTED").map(s => s.provider_id);
    const blocked = (sourcePlan.sources || []).filter(s => s.applicability !== "NOT_APPLICABLE" && s.request_accounting !== "SUPPORTED").map(s => s.provider_id);
    const inapplicable = (sourcePlan.sources || []).filter(s => s.applicability === "NOT_APPLICABLE").map(s => `${s.provider_id} (${s.applicability_reason})`);
    const vi = currentLanguage === "vi";
    const parts = [vi ? `Nguồn dự kiến: ${ready.join(", ") || "không có"}.` : `Planned sources: ${ready.join(", ") || "none"}.`];
    if (sourcePlan.investigation_mode === "PERSONAL_FOOTPRINT") {
      parts.unshift(vi ? "Chế độ: dấu vết cá nhân." : "Mode: personal footprint.");
    } else if (sourcePlan.investigation_mode === "INFRASTRUCTURE") {
      parts.unshift(vi ? "Chế độ: hạ tầng Internet." : "Mode: Internet infrastructure.");
    }
    if ((sourcePlan.sources || []).some(s => s.identifier_disclosure === "SHA256_EMAIL")) {
      parts.push(vi ? "Gravatar nhận mã băm SHA-256 dẫn xuất từ email; email thô không nằm trong URL request." : "Gravatar receives a SHA-256 value derived from the email; the raw email is not placed in the request URL.");
    }
    if (blocked.length) parts.push(vi ? `Đang khóa vì chưa kiểm toán request: ${blocked.join(", ")}.` : `Blocked until request accounting is audited: ${blocked.join(", ")}.`);
    if (inapplicable.length) parts.push(vi ? `Không chạy do sai loại đầu vào: ${inapplicable.join(", ")}.` : `Skipped for this input type: ${inapplicable.join(", ")}.`);
    if (!sourcePlan.internet_api_keys_applicable && ["USERNAME", "EMAIL"].includes(data.type)) {
      parts.push(vi ? "Shodan/Censys/FOFA không áp dụng cho tìm tài khoản cá nhân." : "Shodan/Censys/FOFA do not apply to personal-account discovery.");
    }
    if ((sourcePlan.sources || []).some(s => s.provider_id === "coccoc_browser" && s.applicability === "APPLICABLE")) {
      parts.push(vi
        ? "Bấm ‘Bắt đầu điều tra tự động’ sẽ mở Cốc Cốc để kiểm tra các trang công khai; nếu Cốc Cốc đang mở bằng profile này, hãy đóng nó rồi chạy lại."
        : "Clicking ‘Start automated investigation’ will open Cốc Cốc for public-page checks; if that profile is already open, close Cốc Cốc and run again.");
    }
    preflight.textContent = parts.join(" ");
    return data;
  } catch (error) {
    if (sequence !== classificationSequence || error.name === "AbortError") return null;
    preview.textContent = currentLanguage === "vi" ? "CẦN KIỂM TRA" : "CHECK INPUT";
    preview.className = "badge badge-missing";
    explanation.textContent = currentLanguage === "vi"
      ? "Không xác định được loại. Kiểm tra đầu vào và lựa chọn; số điện thoại cần +mã quốc gia."
      : "Cannot classify this input. Check the value and selected type; phones need +country code.";
    preflight.textContent = "";
    return null;
  }
}

async function startInvestigation(browserAssisted = "auto") {
  const targetVal = document.getElementById("target-input").value.trim();
  if (!targetVal) {
    alert(currentLanguage === "vi" ? "Vui lòng nhập mục tiêu điều tra!" : "Please enter a target value!");
    return;
  }

  const profile = document.getElementById("profile-select").value;
  const depth = parseInt(document.getElementById("depth-select").value, 10);
  const timeoutValue = document.getElementById("timeout-select").value;
  const requestValue = document.getElementById("request-budget-select").value;
  const timeout = timeoutValue === "unlimited" ? null : parseInt(timeoutValue, 10);
  const isAuthorized = document.getElementById("authorized-checkbox").checked;

  const btn = document.getElementById("btn-start-investigate");
  const browserBtn = document.getElementById("btn-browser-investigate");
  btn.disabled = true;
  browserBtn.disabled = true;
  btn.innerHTML = `<span>&#x21BB;</span> ${currentLanguage === "vi" ? "Đang khởi tạo..." : "Initializing..."}`;

  try {
    const classification = await classifyCurrentTarget(browserAssisted !== false);
    if (!classification || targetVal !== document.getElementById("target-input").value.trim()) return;
    if (classification.needs_confirmation) {
      document.getElementById("target-type-select").focus();
      return;
    }
    const catalogue = await loadInputCatalogue();
    if (!catalogue || catalogue.get(classification.type)?.supported !== true) {
      document.getElementById("classification-explanation").textContent = currentLanguage === "vi"
        ? "Loại này chưa có luồng thu thập khả dụng. Chưa khởi chạy điều tra."
        : "No available collection workflow exists for this type. Investigation has not started.";
      return;
    }
    // Clicking the primary action is the explicit start signal. Personal
    // targets use the visible signed-in browser by default when available.
    const effectiveBrowserAssisted = browserAssisted === true ||
      (browserAssisted === "auto" && ["USERNAME", "EMAIL"].includes(classification.type));
    const maxRequests = requestValue === "unlimited" ? null :
      (requestValue === "auto" ? (effectiveBrowserAssisted ? 500 : 100) : parseInt(requestValue, 10));
    const res = await fetch("/api/investigate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target: targetVal,
        target_type: document.getElementById("target-type-select").value || null,
        investigation_mode: document.getElementById("investigation-mode-select").value,
        browser_assisted: effectiveBrowserAssisted,
        policy_profile: profile,
        budget: {
          max_depth: depth,
          max_entities: 500,
          max_requests: maxRequests,
          timeout_seconds: timeout,
          username_source_scope: document.getElementById("username-sites-select").value
        },
        scope_authorized: isAuthorized
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail?.message || err.detail || "Investigation dispatch failed");
    }

    const data = await res.json();
    currentCaseId = data.case_id;
    currentRunId = data.run_id;
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
    browserBtn.disabled = false;
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
  document.getElementById('insight-target').innerHTML = '<option value="">Chọn mục tiêu / Select target</option>';
  currentView = "case_detail";
  currentCaseId = caseId;
  currentRunId = null;
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

async function shutdownSpider() {
  if (!window.confirm(t("confirm_shutdown"))) return;
  const button = document.getElementById("btn-shutdown");
  button.disabled = true;
  try {
    const response = await fetch("/api/system/shutdown", {method: "POST"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Shutdown request failed");
    document.body.innerHTML = `<main style="max-width:640px;margin:15vh auto;font-family:system-ui;padding:32px;text-align:center">
      <h1>SPIDER đã tắt an toàn</h1><p>Bạn có thể đóng tab này. Lần sau chỉ cần mở run_spider.bat.</p></main>`;
  } catch (error) {
    button.disabled = false;
    alert(error.message);
  }
}

function scopedCaseUrl(caseId, suffix) {
  const params = new URLSearchParams({scoped: 'true', question: document.getElementById('insight-question').value});
  const target = document.getElementById('insight-target').value;
  if (target) params.set('target_id', target);
  return `/api/cases/${caseId}/${suffix}?${params}`;
}

async function loadCaseDetail(caseId) {
  try {
    const scopeQuery = new URLSearchParams({question: document.getElementById('insight-question').value});
    const selectedTarget = document.getElementById('insight-target').value;
    if (selectedTarget) scopeQuery.set('target_id', selectedTarget);
    const [caseRes, insightsRes, egressRes] = await Promise.all([
      fetch(`/api/cases/${caseId}`).then(r => r.json()),
      fetch(`/api/cases/${caseId}/insights?${scopeQuery}`).then(r => r.json()),
      fetch(`/api/cases/${caseId}/egress?${scopeQuery}`).then(r => r.json())
    ]);
    if (caseId !== currentCaseId) return;
    const scope = insightsRes.scope || {};
    const selector = document.getElementById('insight-target');
    selector.replaceChildren(new Option(currentLanguage === 'vi' ? 'Chọn mục tiêu' : 'Select target', ''));
    (scope.targets || []).forEach(target => selector.add(new Option(`${target.type}: ${target.value}`, target.id)));
    selector.value = selectedTarget || scope.target_id || '';
    document.getElementById('scope-explanation').textContent = scope.selection_required
      ? (currentLanguage === 'vi' ? 'Chọn mục tiêu để xem bằng chứng riêng, tránh lẫn dữ liệu.' : 'Select a target to view its evidence separately.')
      : `${currentLanguage === 'vi' ? 'Bằng chứng chưa xác định mục tiêu bị loại' : 'Unscoped evidence excluded'}: ${scope.unscoped_observations_excluded || 0}`;
    document.getElementById('egress-explanation').textContent = friendlyLabel(egressRes.state);
    document.getElementById('egress-events').textContent = (egressRes.events || []).map(e =>
      `${e.provider_id} → ${e.destination} | ${friendlyLabel(e.derivation)} | ${friendlyLabel(e.authentication)}`).join('\n');
    renderReaderReport(insightsRes);
    const coverage = insightsRes.coverage_report || {};
    document.getElementById('coverage-explanation').textContent = `${currentLanguage === 'vi' ? 'Bước kiểm tra có kết quả xác định / Còn chưa rõ' : 'Steps with a determined outcome / Still unclear'}: ${coverage.decided || 0} / ${coverage.unknown || 0}`;
    const recommendation = coverage.next_best_action || {};
    if (recommendation.action) {
      document.getElementById('coverage-explanation').textContent += ` · ${currentLanguage === 'vi' ? 'Bước tiếp theo' : 'Next step'}: ${friendlyLabel(recommendation.action)} (${friendlyLabel(recommendation.basis || 'NOT_YET_VERIFIED')})`;
    }
    document.getElementById('coverage-steps').textContent = (coverage.steps || []).map(s => `${s.provider_id}: ${friendlyLabel(s.reason in (reportVocabulary[currentLanguage] || {}) ? s.reason : s.state)}`).join('\n');
    const analysis = insightsRes.evidence_analysis || {};
    document.getElementById('evidence-analysis').textContent = [
      ...(analysis.link_proofs || []).map(p => `${friendlyLabel(p.kind)}: ${p.source} → ${p.target} [${p.observation_id}]`),
      ...(analysis.ownership_hypotheses || []).map(h => `${friendlyLabel("OWNERSHIP_HYPOTHESIS")}: ${h.account?.canonical_value || "—"} · ${friendlyLabel(h.status)} · ${currentLanguage === "vi" ? "chưa xác minh chủ sở hữu" : "owner unverified"}`),
      ...(analysis.next_best_action?.action ? [`${currentLanguage === "vi" ? "Bước nên làm tiếp" : "Suggested next step"}: ${friendlyLabel(analysis.next_best_action.action)} (${friendlyLabel(analysis.next_best_action.basis)})`] : []),
      ...(analysis.temporal_events || []).map(e => `${friendlyLabel(e.view)}: ${friendlyLabel(e.event)} | ${e.observed_at} [${e.observation_id}]`),
      ...(analysis.hypotheses || []).map(h => `${h.claim_id}: ${friendlyLabel(h.decision)} | ${friendlyLabel("SUPPORTING_EVIDENCE")}: ${h.SUPPORTING_EVIDENCE.length}; ${friendlyLabel("CONTRADICTING_EVIDENCE")}: ${h.CONTRADICTING_EVIDENCE.length}; ${friendlyLabel("UNKNOWN")}: ${h.UNKNOWN.length}`),
      currentLanguage === 'vi' ? 'Liên kết công khai chưa xác minh cùng chủ sở hữu.' : 'Public links do not verify common ownership.'
    ].join('\n');
    document.getElementById('evidence-bundle-download').href = `/api/cases/${caseId}/bundle?${scopeQuery}`;

    // Header Info
    document.getElementById("case-title").textContent = caseRes.name || "Cuộc điều tra";
    const status = insightsRes.status || caseRes.status || "PENDING";
    currentRunId = insightsRes.run_id || currentRunId;
    const statusBadge = document.getElementById("case-status-badge");
    statusBadge.textContent = friendlyLabel(status);
    statusBadge.className = `badge badge-${status.toLowerCase()}`;
    updateRunControls(status, insightsRes.resumable === true);

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
function coverageDescription(source) {
  const c = source.coverage;
  if (!c) {
    const reasons = {
      NO_PUBLIC_PRIMARY_EMAIL_PROFILE: currentLanguage === "vi" ? "Đã kiểm tra Gravatar; không thấy hồ sơ công khai gắn với mã băm email chính" : "Gravatar checked; no public profile for the primary email hash",
      PUBLIC_PROFILE_FOUND: currentLanguage === "vi" ? "Đã tìm thấy hồ sơ công khai gắn trực tiếp với email" : "A public profile directly linked to the email was found",
      RATE_LIMIT: currentLanguage === "vi" ? "Chưa kết luận do nguồn giới hạn lượt truy cập" : "Unknown because the source rate limited the request",
      ACCESS_DENIED: currentLanguage === "vi" ? "Chưa kết luận do nguồn từ chối truy cập" : "Unknown because the source denied access",
      UPSTREAM_ERROR: currentLanguage === "vi" ? "Chưa kết luận do dịch vụ nguồn bị lỗi" : "Unknown because the upstream service failed",
      NETWORK_OR_RESPONSE_ERROR: currentLanguage === "vi" ? "Chưa kết luận do lỗi mạng hoặc phản hồi không hợp lệ" : "Unknown because the network or response failed",
      BROWSER_NETWORK_UNAVAILABLE: currentLanguage === "vi" ? "Cốc Cốc không truy cập được Internet; chưa kiểm tra website nào" : "Cốc Cốc could not reach the Internet; no websites were checked",
      CT_LOG_UNAVAILABLE: currentLanguage === "vi" ? "Nhật ký chứng chỉ chưa trả lời được; chưa thể kết luận về tên miền phụ" : "The certificate log did not respond; subdomains remain unknown",
      DNS_PARTIAL_RESPONSE: currentLanguage === "vi" ? "Một số loại bản ghi DNS chưa trả lời được; dữ liệu đang có vẫn được giữ" : "Some DNS record types did not respond; available records were retained",
      UNMETERED_PROVIDER: currentLanguage === "vi" ? "Tạm dừng để không chạy nguồn không đếm được request; đây không phải kết quả rỗng" : "Paused because requests cannot be counted; this is not a negative result",
    };
    return reasons[source.collection_reason] || friendlyLabel(source.collection_reason || source.status);
  }
  const priority = Object.entries(c.priority_sites || {}).map(([name, value]) => {
    const codes = [value.reason, value.outcome, value.state].filter(Boolean);
    const code = codes.find(item => item in (reportVocabulary[currentLanguage] || {})) || "UNKNOWN";
    const outcome = friendlyLabel(code);
    return `${name}: ${outcome}`;
  }).join(" · ");
  const search = c.search_discovery;
  const searchParts = [];
  if (search?.candidate_profiles) {
    searchParts.push(currentLanguage === "vi"
      ? `${search.candidate_profiles} hồ sơ đã mở lại và cần đối chiếu chủ tài khoản`
      : `${search.candidate_profiles} reopened ${search.candidate_profiles === 1 ? "profile" : "profiles"} needing ownership corroboration`);
  }
  if (search?.unverified_leads) {
    searchParts.push(currentLanguage === "vi"
      ? `${search.unverified_leads} liên kết tìm kiếm chưa xác minh`
      : `${search.unverified_leads} unverified search ${search.unverified_leads === 1 ? "link" : "links"}`);
  }
  const searchCounts = searchParts.length ? ` (${searchParts.join(", ")})` : "";
  const searchNote = search && search.engine ? `${search.engine}: ${friendlyLabel(search.outcome || "UNKNOWN")}${searchCounts}` : "";
  const summary = currentLanguage === "vi"
    ? `${c.checked || 0}/${c.selected || 0} website đã thử kiểm tra · ${c.found || 0} hồ sơ cần đối chiếu · ${c.not_found || 0} không thấy · ${c.unknown || 0} chưa xác định · ${c.invalid || 0} username không hợp lệ · ${c.unprocessed || 0} chưa xử lý · ${c.non_unique_detections || 0} kết quả không phân biệt được với đối chứng · ${(c.controls_pending || 0) + (c.controls_unknown || 0)} đối chứng chưa kết luận`
    : `${c.checked || 0}/${c.selected || 0} websites checked · ${c.found || 0} profiles needing corroboration · ${c.not_found || 0} not found · ${c.unknown || 0} unknown · ${c.invalid || 0} invalid usernames · ${c.unprocessed || 0} unprocessed · ${c.non_unique_detections || 0} results indistinguishable from controls · ${(c.controls_pending || 0) + (c.controls_unknown || 0)} inconclusive controls`;
  return [priority, searchNote, summary].filter(Boolean).join(" · ");
}

function executionReceiptDescription(source) {
  const vi = currentLanguage === "vi";
  const state = source.execution_state || "NOT_SCHEDULED";
  const requests = Number(source.request_count || 0);
  const observations = Number(source.observations_count || 0);
  const messages = {
    NOT_APPLICABLE: vi ? "Không áp dụng cho loại mục tiêu này" : "Not applicable to this target type",
    NOT_SCHEDULED: vi ? "Có thể áp dụng nhưng chưa được lập lịch" : "Applicable but not scheduled",
      BLOCKED_UNMETERED: vi ? "Tạm dừng vì không thể đếm request mạng; các nguồn có kiểm soát vẫn tiếp tục" : "Paused because requests cannot be counted; audited sources can still continue",
    RUNNING: vi ? "Đang chạy; chưa phát request" : "Running; no request dispatched yet",
    EXECUTED_NO_NETWORK: vi ? "Đã thực thi nhưng không phát request mạng" : "Executed without a network request",
    CALLED: vi ? `Đã gọi ${requests} request; đóng góp ${observations} quan sát` : `Called with ${requests} requests; contributed ${observations} observations`,
  };
  return messages[state] || state;
}

function renderTypeSpecificInsights(insights) {
  const container = document.getElementById("type-specific-container");
  const emptyContainer = document.getElementById("empty-reason-container");
  container.innerHTML = "";
  emptyContainer.style.display = "none";

  const targetType = insights.target_type;
  const investigationMode = insights.investigation_mode || (targetType === "EMAIL" || targetType === "USERNAME" ? "PERSONAL_FOOTPRINT" : "INFRASTRUCTURE");
  const entitiesCount = insights.entities_count || 0;

  if (["EMAIL", "USERNAME"].includes(targetType)) {
    const card = document.createElement("div");
    card.className = "intelligence-card";
    card.id = "public-profile-card";
    const profiles = insights.public_profiles || [];
    card.innerHTML = `<div class="intelligence-card-header"><strong>${currentLanguage === "vi" ? "Hồ sơ công khai & căn cứ liên hệ" : "Public profiles & linkage evidence"}</strong><span class="badge badge-ready">${profiles.length}</span></div>
      <p>${escapeHtml(insights.profile_evidence?.[currentLanguage === "vi" ? "message_vi" : "message_en"] || "")}</p>
      <p>${currentLanguage === "vi" ? "Trùng email công khai chứng minh hồ sơ có đăng email đó; trùng username chỉ là ứng viên cần đối chiếu." : "A public email match shows that a profile lists that email. A username match is a candidate requiring corroboration."}</p>
      <p>${currentLanguage === "vi" ? "Nguồn tìm hồ sơ đã chạy" : "Profile sources executed"}: ${escapeHtml((insights.profile_evidence?.checked_sources || []).join(", ") || "—")}</p>`;
    profiles.forEach(profile => {
      const entry = document.createElement("div");
      entry.className = "detail-row";
      const bases = {
        exact_public_email: currentLanguage === "vi" ? "Email công khai trùng khớp" : "Exact public email",
        email_hash_public_profile: currentLanguage === "vi" ? "Hồ sơ công khai gắn với mã băm của email chính" : "Public profile linked to the primary email hash",
        verified_account_from_email_profile: currentLanguage === "vi" ? "Tài khoản được hồ sơ Gravatar xác minh liên kết" : "Account link verified by the Gravatar profile",
        username_only: currentLanguage === "vi" ? "Trùng username — chưa xác minh chủ sở hữu" : "Shared username — owner unverified",
        signed_in_browser_candidate: currentLanguage === "vi" ? "Ứng viên từ Cốc Cốc đã đăng nhập — cần mở và đối chiếu" : "Candidate from signed-in Cốc Cốc — open and corroborate",
        coccoc_search_candidate: currentLanguage === "vi" ? "Ứng viên từ Cốc Cốc Search — cần mở và đối chiếu" : "Candidate from Cốc Cốc Search — open and corroborate",
      };
      const basis = bases[profile.match_basis] || (currentLanguage === "vi" ? "Liên hệ công khai — cần đối chiếu" : "Public linkage — corroboration required");
      const work = [profile.job_title, profile.company].filter(Boolean).join(" · ");
      entry.innerHTML = `<div><small>${escapeHtml(profile.platform)} · ${currentLanguage === "vi" ? "Tên/tiêu đề công khai" : "Public name/title"}</small><br><strong>${escapeHtml(profile.display_name || profile.platform)}</strong><p>${escapeHtml(basis)}</p><p>${escapeHtml(profile.bio || "")}</p>${profile.location ? `<p>${currentLanguage === "vi" ? "Vị trí tự khai" : "Self-reported location"}: ${escapeHtml(profile.location)}</p>` : ""}${work ? `<p>${currentLanguage === "vi" ? "Nghề nghiệp/tổ chức tự khai" : "Self-reported role/organization"}: ${escapeHtml(work)}</p>` : ""}${profile.website ? `<p>Website: ${escapeHtml(profile.website)}</p>` : ""}<small>${escapeHtml(profile.provider_id)} · ${escapeHtml(friendlyLabel(profile.verification_state || "PUBLIC_SELF_PUBLISHED"))} · ${escapeHtml(profile.observed_at || "")}</small></div>`;
      const link = document.createElement("a");
      try {
        const url = new URL(profile.profile_url);
        if (["https:", "http:"].includes(url.protocol) && !url.username && !url.password) {
          link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer";
          link.textContent = profile.profile_url; entry.appendChild(link);
        }
      } catch (_) { /* Invalid source URLs are not made clickable. */ }
      (profile.explicit_links || []).forEach(item => {
        try {
          const url = new URL(item.url);
          if (["https:", "http:"].includes(url.protocol) && !url.username && !url.password) {
            const line = document.createElement("div");
            const label = document.createElement("small");
            label.textContent = currentLanguage === "vi" ? "Liên kết tự công bố: " : "Self-published link: ";
            const anchor = document.createElement("a");
            anchor.href = url.href; anchor.target = "_blank"; anchor.rel = "noopener noreferrer";
            anchor.textContent = item.url;
            line.append(label, anchor); entry.appendChild(line);
          }
        } catch (_) { /* Invalid source URLs are not made clickable. */ }
      });
      card.appendChild(entry);
    });
    container.appendChild(card);
  }

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
        ${escapeHtml(insights.reader_report?.[currentLanguage]?.conclusion || t("empty_reason_desc"))}
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
  if (targetType === "EMAIL" && investigationMode === "INFRASTRUCTURE" && insights.email_insights) {
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
  if ((targetType === "DOMAIN" || targetType === "HOSTNAME" || (targetType === "EMAIL" && investigationMode === "INFRASTRUCTURE" && insights.domain_insights)) && insights.domain_insights) {
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
      <div class="card-grid-2" style="margin-top:16px;">
        <div>
          <div class="detail-key">Bảo vệ DNS quan sát được:</div>
          <div class="detail-row"><span class="detail-key">SPF:</span><span class="detail-val"><small>${escapeHtml((dom.dns_security?.spf || []).join(" · ") || "Chưa thu thập được")}</small></span></div>
          <div class="detail-row"><span class="detail-key">DMARC:</span><span class="detail-val"><small>${escapeHtml((dom.dns_security?.dmarc || []).join(" · ") || "Chưa thu thập được")}</small></span></div>
          <div class="detail-row"><span class="detail-key">CAA:</span><span class="detail-val"><small>${escapeHtml((dom.dns_security?.caa || []).join(" · ") || "Chưa thu thập được")}</small></span></div>
        </div>
        <div>
          <div class="detail-key">Chứng chỉ công khai đã quan sát:</div>
          ${(dom.certificates || []).length ? `<ul class="detail-list">${dom.certificates.slice(0, 8).map(c => `<li>${escapeHtml(c.issuer_name || "Nhà phát hành chưa rõ")}<br><small>${escapeHtml(c.not_before || "")} → ${escapeHtml(c.not_after || "")}</small></li>`).join("")}</ul>` : "<em>Chưa thu thập được từ nhật ký chứng chỉ</em>"}
        </div>
      </div>
      <div class="card-grid-2" style="margin-top:16px;">
        <div>
          <div class="detail-key">Dịch vụ Internet công khai từ nguồn đã cấu hình:</div>
          ${(dom.public_services || []).length ? `<ul class="detail-list">${dom.public_services.slice(0, 10).map(s => `<li>${escapeHtml([s.engine, s.host || s.ip, s.port, s.protocol].filter(v => v !== undefined && v !== "").join(" · "))}</li>`).join("")}</ul>` : "<em>Chưa thu thập được; chỉ xuất hiện khi nguồn Internet intelligence có dữ liệu.</em>"}
        </div>
        <div>
          <div class="detail-key">Dấu hiệu công nghệ do nguồn công khai ghi nhận:</div>
          <div class="chips-container">${(dom.technology_signals || []).length ? dom.technology_signals.slice(0, 20).map(value => `<span class="chip">${escapeHtml(value)}</span>`).join("") : "<em>Chưa thu thập được; đây không phải kết quả suy đoán từ SPIDER.</em>"}</div>
        </div>
      </div>
      <div style="margin-top:16px;">
        <div class="detail-key">Quan sát HTTPS đã được ủy quyền:</div>
        ${(dom.web_metadata || []).length ? `<ul class="detail-list">${dom.web_metadata.slice(0, 5).map(item => `<li><strong>${escapeHtml(String(item.http_status || ""))}</strong> · ${escapeHtml(item.url || "")}<br><small>${escapeHtml(item.title || "Không có tiêu đề")} · HSTS: ${item.has_hsts ? "có" : "chưa thấy"} · CSP: ${item.has_csp ? "có" : "chưa thấy"}</small></li>`).join("")}</ul>` : "<em>Chỉ chạy khi bạn xác nhận phạm vi được ủy quyền và chọn profile kiểm tra chủ động.</em>"}
      </div>
      <div style="margin-top:16px;">
        <div class="detail-key">Mạng và vị trí ước lượng của IP quan sát được:</div>
        ${(dom.network_profiles || []).length ? `<ul class="detail-list">${dom.network_profiles.slice(0, 12).map(item => `<li><strong>${escapeHtml(item.ip || "IP theo nguồn")}</strong> · ${escapeHtml(item.asn || "ASN chưa rõ")} · ${escapeHtml(item.organization || item.isp || item.network_name || "Tổ chức chưa rõ")}<br><small>${escapeHtml([item.city, item.region, item.country].filter(Boolean).join(", ") || "Vị trí chưa có nguồn")}${item.prefix || item.cidr ? ` · ${escapeHtml(item.prefix || item.cidr)}` : ""} · Đây có thể là CDN/edge, không khẳng định máy chủ gốc.</small></li>`).join("")}</ul>` : "<em>Chưa có phản hồi registry/IP intelligence cho các IP đã quan sát.</em>"}
      </div>
    `;
    container.appendChild(card);
  }

  // C. IP & BGP INTELLIGENCE CARD
  if ((targetType === "IP_ADDRESS" || targetType === "IPV6_ADDRESS") && insights.ip_insights) {
    const ip = insights.ip_insights;
    const yesNoUnknown = value => value === true ? (currentLanguage === "vi" ? "Có" : "Yes")
      : value === false ? (currentLanguage === "vi" ? "Không" : "No") : (currentLanguage === "vi" ? "Chưa xác định" : "Unknown");
    const location = [ip.city, ip.region, ip.country].filter(Boolean).join(", ") || "-";
    const coordinates = (ip.latitude !== null && ip.latitude !== undefined && ip.longitude !== null && ip.longitude !== undefined)
      ? `${ip.latitude}, ${ip.longitude}` : "-";
    const sourceRows = (ip.source_observations || []).map(source => `
      <tr><td>${escapeHtml(source.provider_id || "-")}</td><td>${escapeHtml(source.record_kind || "-")}</td>
      <td>${escapeHtml(source.observed_at ? new Date(source.observed_at).toLocaleString() : "-")}</td>
      <td>${escapeHtml(friendlyLabel("UNCALIBRATED"))}</td></tr>`).join("");
    const contacts = (ip.contacts || []).flatMap(contact => (contact.emails || []).map(email =>
      `${(contact.roles || []).join(", ") || "contact"}: ${email}`));
    const card = document.createElement("div");
    card.className = "intelligence-card";
    card.innerHTML = `
      <div class="intelligence-card-header">
        <span class="intelligence-card-title">&#x1F5A5; Hồ sơ tình báo địa chỉ IP</span>
        <span class="badge badge-ready">MULTI-SOURCE IP</span>
      </div>
      <div class="card-grid-2">
        <div>
          <div class="detail-row"><span class="detail-key">Địa chỉ IP:</span><span class="detail-val"><code>${escapeHtml(ip.ip || "-")}</code></span></div>
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
          <div class="detail-row"><span class="detail-key">ISP:</span><span class="detail-val">${escapeHtml(ip.isp || "-")}</span></div>
          <div class="detail-row"><span class="detail-key">RIR:</span><span class="detail-val">${escapeHtml(ip.rir || "-")}</span></div>
          <div class="detail-row"><span class="detail-key">Tên dải mạng:</span><span class="detail-val">${escapeHtml(ip.network_name || "-")}</span></div>
        </div>
        <div>
          <div class="detail-row"><span class="detail-key">Vị trí gần đúng:</span><span class="detail-val">${escapeHtml(location)}</span></div>
          <div class="detail-row"><span class="detail-key">Mã bưu chính:</span><span class="detail-val">${escapeHtml(ip.postal_code || "-")}</span></div>
          <div class="detail-row"><span class="detail-key">Múi giờ:</span><span class="detail-val">${escapeHtml(ip.time_zone || "-")}</span></div>
          <div class="detail-row"><span class="detail-key">Tọa độ ước lượng:</span><span class="detail-val">${escapeHtml(coordinates)}</span></div>
          <div class="detail-row"><span class="detail-key">Proxy / VPN / Datacenter:</span><span class="detail-val">${escapeHtml(`${yesNoUnknown(ip.is_proxy)} / ${yesNoUnknown(ip.is_vpn)} / ${yesNoUnknown(ip.is_datacenter)}`)}</span></div>
          <div class="detail-row"><span class="detail-key">Loại proxy:</span><span class="detail-val">${escapeHtml(ip.proxy_type || "-")}</span></div>
          <div class="detail-row"><span class="detail-key">Mô tả proxy:</span><span class="detail-val">${escapeHtml(ip.proxy_type_description || "-")}</span></div>
          <div class="detail-row"><span class="detail-key">Dải proxy:</span><span class="detail-val"><code>${escapeHtml(ip.proxy_range || "-")}</code></span></div>
        </div>
      </div>
      <div style="margin-top:14px;">
        <div class="detail-key">Reverse DNS / Hostnames:</div>
        <div class="chips-container">${(ip.associated_hostnames || []).length ? ip.associated_hostnames.map(h => `<span class="chip">${escapeHtml(h)}</span>`).join("") : "<em>Chưa phát hiện</em>"}</div>
      </div>
      <div style="margin-top:14px;">
        <div class="detail-key">Liên hệ vận hành công khai:</div>
        <div class="chips-container">${contacts.length ? contacts.map(item => `<span class="chip">${escapeHtml(item)}</span>`).join("") : "<em>Chưa có trong RDAP</em>"}</div>
      </div>
      <p class="form-hint" style="margin-top:14px;">Vị trí IP là ước lượng cấp mạng và không xác định cá nhân hoặc địa chỉ nhà.</p>
      <div style="margin-top:14px; overflow-x:auto;">
        <div class="detail-key">Nguồn và thời điểm quan sát:</div>
        <table><thead><tr><th>Nguồn</th><th>Loại dữ liệu</th><th>Quan sát lúc</th><th>Độ tin cậy</th></tr></thead>
        <tbody>${sourceRows || '<tr><td colspan="4"><em>Chưa có dữ liệu bổ sung</em></td></tr>'}</tbody></table>
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
    const digest = ph.public_candidate_digest || {};
    const candidates = Array.isArray(digest.candidates) ? digest.candidates : [];
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
      <div style="margin-top:14px;">
        <div class="detail-key">${currentLanguage === "vi" ? "Liên hệ công khai có bằng chứng" : "Publicly evidenced links"}:</div>
        ${candidates.length ? `<ul class="detail-list">${candidates.map(item => `<li><strong>${escapeHtml(item.type)}:</strong> ${escapeHtml(item.value)}<br><small>${escapeHtml((item.rank_reasons || []).join(" · "))}</small></li>`).join("")}</ul>` :
          `<em>${currentLanguage === "vi" ? "Chưa có liên hệ công khai được ghi nhận. Điều này không xác định hay phủ định chủ số." : "No public link has been recorded. This neither identifies nor rules out a subscriber."}</em>`}
      </div>
      ${(digest.contradictions || []).length ? `<p class="warning-text">${currentLanguage === "vi" ? "Có ứng viên công khai cạnh tranh; SPIDER không chọn một người làm chủ số." : "Competing public candidates exist; SPIDER does not select a subscriber."}</p>` : ""}
    `;
    container.appendChild(card);
  }
}

// --- 7. Tab 2: Live Progress Loader ---
async function loadCaseProgress(caseId) {
  try {
    const insightsRes = await fetch(scopedCaseUrl(caseId, 'insights')).then(r => r.json());
    const tbody = document.getElementById("live-tasks-tbody");
    tbody.innerHTML = "";

    const tasks = insightsRes.provider_contributions || [];
    const runStatus = insightsRes.status || "PENDING";
    const liveStatus = document.getElementById("live-run-status");
    liveStatus.textContent = friendlyLabel(runStatus);
    liveStatus.className = `badge badge-${runStatus.toLowerCase()}`;
    liveStatus.dataset.status = runStatus;

    if (tasks.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:var(--text-muted); padding:20px;">Đang chuẩn bị lập lịch các tác vụ OSINT...</td></tr>`;
      return;
    }

    tasks.forEach(t => {
      const tr = document.createElement("tr");
      const duration = t.duration_ms ? `${(t.duration_ms).toFixed(1)}ms` : "-";
      tr.innerHTML = `
        <td><strong>${escapeHtml(t.provider_id)}</strong></td>
        <td>${currentLanguage === "vi" ? "Kiểm tra nguồn đã chọn" : "Check selected source"}</td>
        <td><code>${escapeHtml(insightsRes.target || "-")}</code></td>
        <td><span class="badge badge-${(t.status || "ready").toLowerCase()}">${escapeHtml(friendlyLabel(t.status))}</span></td>
        <td>${escapeHtml(duration)}</td>
        <td><strong>${escapeHtml(String(t.observations_count || 0))}</strong></td>
        <td><small style="color:var(--text-muted);">${escapeHtml(coverageDescription(t))}</small></td>
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
    currentCaseEntities = await fetch(scopedCaseUrl(currentCaseId, 'entities')).then(r => r.json());
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
    const insights = await fetch(scopedCaseUrl(currentCaseId, 'insights')).then(r => r.json());
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
        <td><span class="badge badge-${(p.status || "ready").toLowerCase()}">${escapeHtml(friendlyLabel(p.status))}</span></td>
        <td>${p.duration_ms ? p.duration_ms.toFixed(1) : "-"}</td>
        <td><strong>${escapeHtml(String(p.observations_count || 0))}</strong></td>
        <td><small style="color:var(--text-muted);"><strong>${escapeHtml(executionReceiptDescription(p))}</strong><br>${escapeHtml(coverageDescription(p))}</small></td>
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
    currentCaseObservations = await fetch(scopedCaseUrl(currentCaseId, 'observations')).then(r => r.json());
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
        <td><strong>${escapeHtml(friendlyLabel("UNCALIBRATED"))}</strong></td>
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
    const data = await fetch(scopedCaseUrl(caseId, 'graph')).then(r => r.json());
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
    const explainParams = new URLSearchParams({case_id: currentCaseId, entity_id: entityId});
    const targetId = document.getElementById('insight-target').value;
    if (targetId) explainParams.set('target_id', targetId);
    const res = await fetch(`/api/explain?${explainParams}`);
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
            <div style="font-size:12px;">${escapeHtml(friendlyLabel("UNCALIBRATED"))}</div>
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
        <td><strong>${escapeHtml(p.provider_id)}</strong></td>
        <td><code>${escapeHtml(p.version)}</code></td>
        <td><span class="badge badge-${p.state.toLowerCase()}">${escapeHtml(p.state)}</span></td>
        <td>${p.capabilities.map(c => `<span class="chip" style="font-size:11px;">${escapeHtml(c)}</span>`).join(" ")}</td>
        <td><code>${escapeHtml(p.network_class)}</code></td>
        <td><small style="color:var(--text-muted);">${escapeHtml(p.health_message)}<br>
          ${currentLanguage === 'vi' ? 'Kiểm thử contract' : 'Contract verification'}: ${p.contract_verified ? 'PASS' : 'NOT YET VERIFIED'}<br>
          ${currentLanguage === 'vi' ? 'Kiểm thử nguồn thực tế' : 'Live verification'}: ${p.live_verified ? 'PASS' : 'NOT YET VERIFIED'}</small></td>
        <td>
          <button class="btn btn-secondary" style="padding:4px 10px; font-size:11.5px;" onclick="testProviderLive('${escapeHtml(p.provider_id)}')">
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
  showNotification(currentLanguage === "vi" ? `Đang kiểm tra khả dụng của ${providerId}...` : `Checking availability of ${providerId}...`);
  try {
    const res = await fetch(`/api/providers/${providerId}/test`, { method: "POST" });
    const data = await res.json();
    alert(`[${providerId}] Trạng thái: ${data.state}
Chẩn đoán: ${data.message}
Contract: ${data.contract_verified ? 'PASS' : 'NOT YET VERIFIED'}
Live: ${data.live_verified ? 'PASS' : 'NOT YET VERIFIED'}`);
    if (currentView === "providers") loadProviders();
  } catch (e) {
    alert(`Lỗi kiểm tra [${providerId}]: ${e.message}`);
  }
}

// --- 14. Settings Modal Engine ---
const apiFields = {
  shodan: {SHODAN_API_KEY: "setting-key-shodan"},
  censys: {CENSYS_API_TOKEN: "setting-key-censys", CENSYS_ORGANIZATION_ID: "setting-censys-org"},
  fofa: {FOFA_EMAIL: "setting-fofa-email", FOFA_KEY: "setting-key-fofa"},
  whatismyip: {WHATISMYIP_API_KEY: "setting-key-whatismyip"}
};
let settingsBusy = false;
let settingsEpoch = 0;
function clearApiInputs(engine) {
  const groups = engine ? [apiFields[engine]] : Object.values(apiFields);
  groups.forEach(group => Object.values(group).forEach(id => { document.getElementById(id).value = ""; }));
}
function setSettingsBusy(busy) {
  settingsBusy = busy;
  document.querySelectorAll('#settings-modal input, #settings-modal select, #settings-modal button').forEach(el => { el.disabled = busy; });
}
function apiStateText(test) {
  const vi = currentLanguage === 'vi';
  const labels = {
    VALID: test.engine === 'whatismyip'
      ? (vi ? 'Key hợp lệ; API trả về IP công khai đúng định dạng.' : 'Key valid; the API returned a valid public IP.')
      : (vi ? 'Khóa hợp lệ. Chưa kiểm thử quyền tìm kiếm.' : 'Account verified. Search permission not tested.'),
    VALID_FREE_PLAN: vi ? 'Token hợp lệ trên Free Plan. Chưa kiểm thử quyền Search API.' : 'Token valid on Free Plan. Search entitlement not tested.',
    INVALID_TOKEN: vi ? 'Token Censys không hợp lệ.' : 'Invalid Censys token.',
    NO_SEARCH_ENTITLEMENT: vi ? 'Token hợp lệ nhưng không có quyền Search API.' : 'Token is valid but has no Search API entitlement.',
    QUOTA_LIMIT: vi ? 'Đã chạm quota.' : 'Quota limit reached.',
    RATE_LIMIT: vi ? 'Bị giới hạn tốc độ; thử lại sau.' : 'Rate limited; retry later.',
    KEY_VALID: vi ? 'FOFA key hợp lệ. Chưa kiểm thử quyền truy vấn.' : 'FOFA key valid. Query entitlement not tested.',
    NO_QUERY_ENTITLEMENT: vi ? 'FOFA key hợp lệ nhưng không có quyền truy vấn.' : 'FOFA key is valid but has no query entitlement.',
    INVALID_KEY: vi ? 'FOFA key không hợp lệ.' : 'Invalid FOFA key.',
    DISABLED_KEY: vi ? 'Key đã bị tắt hoặc thu hồi.' : 'The key is disabled or revoked.',
    MISSING_CREDENTIAL: vi ? 'Thiếu thông tin xác thực.' : 'Missing credentials.',
    INVALID_CREDENTIAL: vi ? 'Thông tin xác thực không hợp lệ hoặc không khớp tài khoản.' : 'Invalid credentials or account mismatch.',
    'PLAN/QUOTA_LIMIT': vi ? 'Bị giới hạn quyền, gói hoặc quota.' : 'Permission, plan or quota limit.',
    NETWORK_ERROR: vi ? 'Không xác minh được kết nối. Kiểm tra mạng hoặc runtime.' : 'Connection could not be verified. Check network or runtime.'
  };
  const warning = test.warning === 'ACCOUNT_EMAIL_MISMATCH' ? (vi ? ' Cảnh báo: email lưu khác email tài khoản; key vẫn hợp lệ.' : ' Warning: saved email differs; key remains valid.') : '';
  return `${test.state}: ${labels[test.state] || ''}${warning}${test.cached ? (vi ? ' (Kết quả gần đây)' : ' (Recent result)') : ''}`;
}
function renderApiSettings(s) {
  Object.entries(apiFields).forEach(([engine, fields]) => {
    Object.entries(fields).forEach(([name, id]) => {
      document.getElementById(id).placeholder = s.api_keys?.[name] ?
        (currentLanguage === 'vi' ? 'Đã lưu bảo mật; nhập để thay đổi' : 'Securely saved; enter to replace') :
        (currentLanguage === 'vi' ? 'Chưa lưu' : 'Not saved');
    });
    const state = s.credential_status?.[engine];
    const text = state?.test ? apiStateText(state.test) : state?.configured ?
      (currentLanguage === 'vi' ? 'Đã lưu đủ thông tin. Chưa kiểm thử kết nối.' : 'Credentials saved. Connection not tested.') :
      (currentLanguage === 'vi' ? 'Thiếu trường: ' : 'Missing fields: ') + (state?.missing_fields || []).join(', ');
    document.getElementById(`key-state-${engine}`).textContent = text;
  });
  document.querySelectorAll('[data-key-test]').forEach(el => { el.textContent = currentLanguage === 'vi' ? 'Lưu và thử kết nối' : 'Save and test connection'; });
  document.querySelectorAll('[data-key-delete]').forEach(el => { el.textContent = currentLanguage === 'vi' ? 'Xóa khóa đã lưu' : 'Delete saved credentials'; });
  document.getElementById('api-key-help').textContent = currentLanguage === 'vi' ?
    'Để trống để giữ giá trị đã lưu. Lưu khóa chưa có nghĩa là kết nối thành công.' :
    'Leave blank to retain saved values. Saving credentials does not verify the connection.';
}
async function openSettingsModal() {
  const epoch = ++settingsEpoch;
  clearApiInputs();
  document.getElementById('settings-modal').classList.add('open');
  try {
    const response = await fetch('/api/settings', {cache: 'no-store'});
    if (!response.ok) throw new Error('Settings unavailable');
    const s = await response.json();
    if (epoch !== settingsEpoch) return;
    document.getElementById('setting-language').value = s.language || currentLanguage;
    document.getElementById('setting-theme').value = s.theme || currentTheme;
    document.getElementById('setting-profile').value = s.default_policy_profile || 'passive_standard';
    document.getElementById('setting-depth').value = s.max_depth ?? 1;
    document.getElementById('setting-timeout').value = s.timeout_seconds || 60;
    renderApiSettings(s);
  } catch (_) {
    showNotification(currentLanguage === 'vi' ? 'Không đọc được cài đặt bảo mật.' : 'Protected settings unavailable.');
  }
}
function closeSettingsModal() {
  settingsEpoch++;
  clearApiInputs();
  document.getElementById('settings-modal').classList.remove('open');
}
function collectApiInputs(engine) {
  const result = {};
  const groups = engine ? [apiFields[engine]] : Object.values(apiFields);
  groups.forEach(group => Object.entries(group).forEach(([name, id]) => {
    const value = document.getElementById(id).value.trim();
    if (value) result[name] = value;
  }));
  return result;
}
async function postSettings(payload) {
  const response = await fetch('/api/settings', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  });
  if (!response.ok) throw new Error('Save failed');
  const data = await response.json();
  renderApiSettings(data);
  return data;
}
async function saveSettings() {
  if (settingsBusy) return;
  setSettingsBusy(true);
  try {
    const lang = document.getElementById('setting-language').value;
    const theme = document.getElementById('setting-theme').value;
    await postSettings({language: lang, theme,
      default_policy_profile: document.getElementById('setting-profile').value,
      max_depth: Number(document.getElementById('setting-depth').value),
      timeout_seconds: Number(document.getElementById('setting-timeout').value), api_keys: collectApiInputs()});
    currentLanguage = lang;
    currentTheme = theme;
    localStorage.setItem('spider_lang', lang);
    localStorage.setItem('spider_theme', theme);
    applyTheme();
    applyTranslations();
    closeSettingsModal();
    showNotification(currentLanguage === 'vi' ? 'Đã lưu cài đặt. Khóa mới chưa được kiểm thử.' : 'Settings saved. New credentials have not been tested.');
  } catch (_) {
    showNotification(currentLanguage === 'vi' ? 'Lưu thất bại. Không xác nhận khóa đã được lưu.' : 'Save failed. Credentials were not confirmed saved.');
  } finally { clearApiInputs(); setSettingsBusy(false); }
}
async function testApiEngine(engine) {
  if (settingsBusy) return;
  setSettingsBusy(true);
  const label = document.getElementById(`key-state-${engine}`);
  try {
    await postSettings({api_keys: collectApiInputs(engine)});
    clearApiInputs(engine);
    label.textContent = currentLanguage === 'vi' ? 'Đang kiểm thử tài khoản...' : 'Checking account...';
    const response = await fetch(`/api/settings/test/${engine}`, {method: 'POST'});
    if (!response.ok) throw new Error('Check unavailable');
    label.textContent = apiStateText(await response.json());
  } catch (_) {
    label.textContent = currentLanguage === 'vi' ? 'Không hoàn tất lưu/kiểm thử. Chưa xác minh thành công.' : 'Save/check did not complete. Success has not been verified.';
  } finally { clearApiInputs(engine); setSettingsBusy(false); }
}
async function deleteApiEngine(engine) {
  if (settingsBusy) return;
  setSettingsBusy(true);
  try {
    await postSettings({api_keys: Object.fromEntries(Object.keys(apiFields[engine]).map(name => [name, '']))});
    clearApiInputs(engine);
  } catch (_) {
    document.getElementById(`key-state-${engine}`).textContent = currentLanguage === 'vi' ? 'Xóa khóa thất bại.' : 'Could not delete credentials.';
  } finally { clearApiInputs(engine); setSettingsBusy(false); }
}

// --- 15. Export & Delete Actions ---
async function exportCaseData() {
  if (!currentCaseId) return;
  try {
    const response = await fetch(scopedCaseUrl(currentCaseId, 'export'));
    if (!response.ok) throw new Error("Report unavailable");
    const fullExport = await response.json();

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

async function exportReadableReport() {
  if (!currentCaseId) return;
  try {
    const response = await fetch(scopedCaseUrl(currentCaseId, 'report') + `&language=${currentLanguage}`);
    if (!response.ok) throw new Error("unavailable");
    const url = URL.createObjectURL(new Blob([await response.text()], {type: "text/markdown;charset=utf-8"}));
    const link = document.createElement("a");
    link.href = url;
    link.download = "SPIDER-report.md";
    link.click();
    URL.revokeObjectURL(url);
  } catch (_) {
    alert(currentLanguage === "vi" ? "Chưa xuất được báo cáo. Hãy chọn mục tiêu và thử lại." : "Report unavailable. Select a target and retry.");
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
  loadInputCatalogue();
  loadReportVocabulary();
});
