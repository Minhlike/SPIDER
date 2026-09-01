// SPIDER Local Web UI Frontend Engine
let currentView = "dashboard";
let currentCaseId = null;
let cyInstance = null;
let socket = null;

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function initWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws`;
  
  socket = new WebSocket(wsUrl);
  socket.onopen = () => {
    console.log("WebSocket connected to SPIDER backend");
    document.getElementById("ws-indicator").style.backgroundColor = "var(--accent-emerald)";
  };
  socket.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleRealtimeEvent(msg.event, msg.data);
    } catch (e) {
      console.error("WS Parse error", e);
    }
  };
  socket.onclose = () => {
    document.getElementById("ws-indicator").style.backgroundColor = "var(--accent-rose)";
    setTimeout(initWebSocket, 3000);
  };
}

function handleRealtimeEvent(eventType, payload) {
  console.log("Realtime Event:", eventType, payload);
  if (eventType === "RUN_STARTED") {
    showNotification(`Investigation started for ${escapeHtml(payload.target)}`);
    if (currentView === "dashboard") loadDashboard();
  } else if (eventType === "RUN_COMPLETED") {
    showNotification(`Investigation completed!`);
    if (currentView === "dashboard") loadDashboard();
    if (currentCaseId === payload.case_id) loadCaseDetail(currentCaseId);
  } else if (eventType === "GRAPH_REBUILT") {
    showNotification(`Knowledge graph rebuilt successfully!`);
    if (currentCaseId === payload.case_id) loadKnowledgeGraph(currentCaseId);
  }
}

function showNotification(msg) {
  const bar = document.getElementById("notification-bar");
  if (bar) {
    bar.textContent = msg;
    bar.style.display = "block";
    setTimeout(() => { bar.style.display = "none"; }, 4000);
  }
}

function switchView(viewName) {
  currentView = viewName;
  document.querySelectorAll(".nav-item").forEach(el => el.classList.remove("active"));
  document.querySelectorAll(".view-panel").forEach(el => el.classList.remove("active"));
  
  const navEl = document.getElementById(`nav-${viewName}`);
  if (navEl) navEl.classList.add("active");
  
  const panelEl = document.getElementById(`view-${viewName}`);
  if (panelEl) panelEl.classList.add("active");

  if (viewName === "dashboard") loadDashboard();
  if (viewName === "providers") loadProviders();
  if (viewName === "investigate") setupInvestigateForm();
}

// 1. Dashboard Loader
async function loadDashboard() {
  try {
    const [casesRes, providersRes] = await Promise.all([
      fetch("/api/cases").then(r => r.json()),
      fetch("/api/providers").then(r => r.json())
    ]);

    document.getElementById("kpi-cases").textContent = casesRes.length;
    let readyProviders = providersRes.filter(p => p.state === "READY").length;
    document.getElementById("kpi-providers").textContent = `${readyProviders}/${providersRes.length}`;

    // Render Recent Cases Table
    const tbody = document.getElementById("recent-cases-tbody");
    tbody.innerHTML = "";
    casesRes.slice(0, 8).forEach(c => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><a href="#" onclick="openCase('${escapeHtml(c.id)}'); return false;" style="color:var(--accent-cyan); font-weight:600;">${escapeHtml(c.name)}</a></td>
        <td><code>${escapeHtml(c.id.substring(0, 8))}</code></td>
        <td><span class="badge badge-${c.status.toLowerCase()}">${escapeHtml(c.status)}</span></td>
        <td style="color:var(--text-muted)">${escapeHtml(c.created_at.substring(0, 19))}</td>
        <td>
          <button class="btn btn-secondary" style="padding:4px 8px; font-size:12px;" onclick="openCase('${escapeHtml(c.id)}')">Explore Graph</button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error("Error loading dashboard", e);
  }
}

// 2. Providers Loader
async function loadProviders() {
  try {
    const providers = await fetch("/api/providers").then(r => r.json());
    const tbody = document.getElementById("providers-tbody");
    tbody.innerHTML = "";
    providers.forEach(p => {
      const stateBadge = p.state === "READY" ? "badge-ready" : (p.state === "MISSING_CREDENTIAL" ? "badge-missing" : "badge-broken");
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(p.provider_id)}</strong></td>
        <td>${escapeHtml(p.version)}</td>
        <td><span class="badge ${stateBadge}">${escapeHtml(p.state)}</span></td>
        <td>${escapeHtml(p.capabilities.join(", "))}</td>
        <td>${escapeHtml(p.network_class)}</td>
        <td style="color:var(--text-muted); font-size:12px;">${escapeHtml(p.health_message)}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error("Error loading providers", e);
  }
}

// 3. New Investigation Setup
function setupInvestigateForm() {
  const targetInput = document.getElementById("target-input");
  const typePreview = document.getElementById("type-preview");
  targetInput.oninput = () => {
    const val = targetInput.value.trim().toLowerCase();
    let type = "USERNAME";
    if (val.includes("@") && !val.endsWith(".com")) type = "ACCOUNT";
    else if (val.includes("@")) type = "EMAIL";
    else if (val.startsWith("as") && !isNaN(val.substring(2))) type = "ASN";
    else if (val.includes("/") && /\d/.test(val)) type = "CIDR";
    else if (val.includes(".") && /[a-z]/.test(val)) type = "DOMAIN";
    else if (val.split(".").length === 4 && val.split(".").every(x => !isNaN(x))) type = "IP_ADDRESS";
    
    typePreview.textContent = type;
  };
}

async function startInvestigation() {
  const target = document.getElementById("target-input").value.trim();
  if (!target) return alert("Please enter a target");

  const profile = document.getElementById("profile-select").value;
  const authorized = document.getElementById("authorized-checkbox").checked;
  const maxDepth = parseInt(document.getElementById("depth-select").value);

  if (profile === "active_authorized" && !authorized) {
    return alert("Active investigation profile requires explicit Scope Authorization checkbox.");
  }

  const btn = document.getElementById("btn-start-investigate");
  btn.disabled = true;
  btn.textContent = "Launching Investigation...";

  try {
    const res = await fetch("/api/investigate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target: target,
        policy_profile: profile,
        authorized_scope: authorized,
        max_depth: maxDepth
      })
    }).then(r => r.json());

    openCase(res.case_id);
  } catch (e) {
    alert("Investigation failed to start: " + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Start Investigation";
  }
}

// 4. Case & Knowledge Graph View
async function openCase(caseId) {
  currentCaseId = caseId;
  switchView("case_detail");
  loadCaseDetail(caseId);
}

async function loadCaseDetail(caseId) {
  try {
    const caseData = await fetch(`/api/cases/${caseId}`).then(r => r.json());
    document.getElementById("case-title").textContent = caseData.name;
    document.getElementById("case-meta").textContent = `ID: ${caseData.id} | Status: ${caseData.status} | Created: ${caseData.created_at.substring(0, 19)}`;
    document.getElementById("case-kpi-entities").textContent = caseData.entities_count;
    document.getElementById("case-kpi-assertions").textContent = caseData.assertions_count;

    loadKnowledgeGraph(caseId);
  } catch (e) {
    console.error("Error loading case detail", e);
  }
}

async function loadKnowledgeGraph(caseId) {
  const cyContainer = document.getElementById("cy-container");
  const entityType = document.getElementById("filter-entity-type").value;
  const minConf = document.getElementById("filter-min-conf").value;
  const search = document.getElementById("filter-search").value;

  let url = `/api/cases/${caseId}/graph?min_confidence=${minConf}&max_nodes=300`;
  if (entityType) url += `&entity_type=${entityType}`;
  if (search) url += `&search=${encodeURIComponent(search)}`;

  const graphData = await fetch(url).then(r => r.json());
  
  document.getElementById("graph-node-count-badge").textContent = `Showing ${graphData.returned_nodes} of ${graphData.total_nodes} nodes (${graphData.total_edges} edges)`;

  if (cyInstance) cyInstance.destroy();

  cyInstance = cytoscape({
    container: cyContainer,
    elements: graphData.elements,
    style: [
      {
        selector: "node",
        style: {
          "background-color": "#06b6d4",
          "label": "data(label)",
          "color": "#ffffff",
          "font-size": "11px",
          "text-valign": "bottom",
          "text-margin-y": 5,
          "width": "mapData(observation_count, 1, 20, 20, 50)",
          "height": "mapData(observation_count, 1, 20, 20, 50)"
        }
      },
      {
        selector: "node[type = 'DOMAIN']",
        style: { "background-color": "#3b82f6" }
      },
      {
        selector: "node[type = 'HOSTNAME']",
        style: { "background-color": "#06b6d4" }
      },
      {
        selector: "node[type = 'IP_ADDRESS']",
        style: { "background-color": "#10b981" }
      },
      {
        selector: "node[type = 'ASN']",
        style: { "background-color": "#f59e0b" }
      },
      {
        selector: "node[type = 'ORGANIZATION']",
        style: { "background-color": "#8b5cf6" }
      },
      {
        selector: "node[type = 'ACCOUNT']",
        style: { "background-color": "#ec4899" }
      },
      {
        selector: "edge",
        style: {
          "width": 2,
          "line-color": "#475569",
          "target-arrow-color": "#475569",
          "target-arrow-shape": "triangle",
          "curve-style": "bezier",
          "label": "data(label)",
          "font-size": "9px",
          "color": "#94a3b8"
        }
      },
      {
        selector: "edge[type = 'RESOLVES_TO']",
        style: { "line-color": "#10b981", "target-arrow-color": "#10b981" }
      },
      {
        selector: "edge[type = 'BELONGS_TO_ASN']",
        style: { "line-color": "#f59e0b", "target-arrow-color": "#f59e0b" }
      },
      {
        selector: "edge[type = 'SUBDOMAIN_OF']",
        style: { "line-color": "#3b82f6", "target-arrow-color": "#3b82f6" }
      }
    ],
    layout: {
      name: "cose",
      animate: false,
      idealEdgeLength: 80,
      nodeOverlap: 20
    }
  });

  // Edge click for Explain
  cyInstance.on("tap", "edge", (evt) => {
    const edge = evt.target;
    explainAssertion(edge.data("id"));
  });

  // Node click for Neighborhood Expansion
  cyInstance.on("tap", "node", (evt) => {
    const node = evt.target;
    inspectNode(node.data());
  });
}

// 5. Explain Assertion Drawer
async function explainAssertion(assertionId) {
  try {
    const exp = await fetch(`/api/explain/${assertionId}`).then(r => r.json());
    document.getElementById("drawer-title").textContent = "Assertion Provenance Trail";
    
    let html = `
      <div style="margin-bottom:16px;">
        <h3 style="color:var(--accent-cyan); font-size:16px; margin-bottom:8px;">${escapeHtml(exp.source_entity.canonical_name)} &rarr; ${escapeHtml(exp.assertion_type)} &rarr; ${escapeHtml(exp.target_entity.canonical_name)}</h3>
        <p style="font-size:13px; color:var(--text-secondary); margin-bottom:4px;"><strong>Confidence:</strong> ${(exp.confidence * 100).toFixed(0)}% | <strong>Rule:</strong> ${escapeHtml(exp.inference_rule)}</p>
        <p style="font-size:13px; color:var(--text-secondary);"><strong>Independent Sources:</strong> ${escapeHtml(exp.source_families.join(", "))}</p>
      </div>
      <h4 style="font-size:14px; margin-bottom:8px;">Evidence Records (${exp.evidence_count})</h4>
      <div style="display:flex; flex-direction:column; gap:10px;">
    `;

    exp.evidence.forEach(ev => {
      html += `
        <div style="background:var(--bg-card); padding:12px; border-radius:6px; border:1px solid var(--border-color); font-size:12px;">
          <p><strong>Provider:</strong> ${escapeHtml(ev.provider_id)} (${escapeHtml(ev.upstream_family)})</p>
          <p style="margin-top:4px;"><strong>Raw Artifact SHA-256:</strong></p>
          <code style="word-break:break-all; font-size:11px; color:var(--accent-cyan);">${escapeHtml(ev.raw_artifact_sha256 || "N/A")}</code>
          <p style="color:var(--text-muted); margin-top:4px;">Observed: ${escapeHtml(ev.timestamp ? ev.timestamp.substring(0,19) : "N/A")}</p>
        </div>
      `;
    });

    html += `</div>`;
    document.getElementById("drawer-content").innerHTML = html;
    document.getElementById("side-drawer").classList.add("open");
  } catch (e) {
    console.error("Error explaining assertion", e);
  }
}

function inspectNode(nodeData) {
  document.getElementById("drawer-title").textContent = "Entity Inspector";
  let html = `
    <div style="margin-bottom:16px;">
      <h3 style="color:var(--accent-cyan); font-size:16px; margin-bottom:8px;">${escapeHtml(nodeData.label)}</h3>
      <span class="badge badge-ready">${escapeHtml(nodeData.type)}</span>
      <p style="font-size:13px; color:var(--text-secondary); margin-top:8px;">Observations Count: ${nodeData.observation_count}</p>
      <p style="font-size:13px; color:var(--text-secondary); margin-top:4px;">First Seen: ${escapeHtml(nodeData.first_seen || "N/A")}</p>
    </div>
  `;
  document.getElementById("drawer-content").innerHTML = html;
  document.getElementById("side-drawer").classList.add("open");
}

function closeDrawer() {
  document.getElementById("side-drawer").classList.remove("open");
}

async function triggerRebuild() {
  if (!currentCaseId) return;
  if (!confirm("Rebuild entire Knowledge Graph for this case from immutable observation log?")) return;
  
  try {
    const res = await fetch(`/api/cases/${currentCaseId}/rebuild`, { method: "POST" }).then(r => r.json());
    alert(`Rebuild Complete! Processed: ${res.observations_processed} observations. Entities: ${res.entities_rebuilt}, Assertions: ${res.assertions_rebuilt}`);
    loadCaseDetail(currentCaseId);
  } catch (e) {
    alert("Rebuild failed: " + e.message);
  }
}

async function exportCaseData() {
  if (!currentCaseId) return;
  window.open(`/api/cases/${currentCaseId}/export`, "_blank");
}

async function deleteCurrentCase() {
  if (!currentCaseId) return;
  if (!confirm("Are you sure you want to permanently delete this case?")) return;

  try {
    await fetch(`/api/cases/${currentCaseId}`, { method: "DELETE" });
    alert("Case deleted successfully");
    switchView("dashboard");
  } catch (e) {
    alert("Failed to delete case: " + e.message);
  }
}

// Initial bootstrap
window.onload = () => {
  initWebSocket();
  switchView("dashboard");
};
