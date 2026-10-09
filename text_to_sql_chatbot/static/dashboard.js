/**
 * Dynamic Schema-Driven Multi-Database Dashboard Engine
 * Automatically generates tailored analytics, KPIs, visual charts, and filters for any connected database.
 * Supports in-place visual query building, direct SQL editing, and persistence.
 */

// ======================================================================
// Dashboard State
// ======================================================================

const state = {
  data: null,
  schemaMeta: { tables: {}, table_list: [] },
  customConfig: {
    overrides: {},    // metric_id -> custom spec
    custom_cards: []  // list of user added metric specs
  },
  isEditMode: false,
  activeModalMode: "builder",
  editingMetricId: null,
  editingMetricSpec: null,
  currentTab: "overview",
  isMatrixVisible: false,
  tableScope: "all",
  filters: {} // dynamic dimension -> selected value
};


// ======================================================================
// Formatting Helpers
// ======================================================================

function formatINR(val, compact = false) {
  if (val === null || val === undefined || isNaN(val)) return "₹0.00";
  const num = Number(val);
  if (num === 0) return "₹0.00";

  if (compact) {
    if (Math.abs(num) >= 1e7) {
      return `₹${(num / 1e7).toFixed(2)} Cr`;
    } else if (Math.abs(num) >= 1e5) {
      return `₹${(num / 1e5).toFixed(2)} L`;
    } else if (Math.abs(num) >= 1e3) {
      return `₹${(num / 1e3).toFixed(2)} K`;
    }
  }

  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2
  }).format(num);
}

function formatNumber(val) {
  if (val === null || val === undefined || isNaN(val)) return "0";
  return new Intl.NumberFormat("en-IN").format(Number(val));
}

function formatValueBySpec(val, formatType) {
  if (val === null || val === undefined) return "0";
  const num = Number(val);

  switch (formatType) {
    case "currency_inr":
      return formatINR(num, true);
    case "currency_inr_exact":
      return formatINR(num, false);
    case "percentage":
      return `${isNaN(num) ? val : num.toFixed(1)}%`;
    case "compact":
      if (Math.abs(num) >= 1e6) return `${(num / 1e6).toFixed(2)}M`;
      if (Math.abs(num) >= 1e3) return `${(num / 1e3).toFixed(1)}K`;
      return formatNumber(num);
    case "number":
    default:
      return formatNumber(num);
  }
}

function getIconSvg(iconKey) {
  const map = {
    chart: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 20V10"/><path d="M12 20V4"/><path d="M6 20v-6"/></svg>`,
    money: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>`,
    calendar: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>`,
    trending: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>`,
    target: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>`,
    shield: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`,
    users: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>`,
    file: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`
  };
  return map[iconKey] || map.chart;
}

function showToast(msg, type = "success") {
  const toast = document.getElementById("dashToast");
  const msgEl = document.getElementById("toastMessage");
  if (!toast || !msgEl) return;

  msgEl.textContent = msg;
  toast.className = `dash-toast show toast-${type}`;
  setTimeout(() => {
    toast.className = "dash-toast";
  }, 3500);
}


// ======================================================================
// API & Data Loader Functions
// ======================================================================

function populateTableScopeDropdown() {
  const select = document.getElementById("tableScopeSelect");
  if (!select) return;

  const tables = state.schemaMeta?.table_list || [];
  const options = [
    `<option value="all" ${state.tableScope === "all" ? "selected" : ""}>⚡ All Tables (Unified)</option>`,
    ...tables.map(t => `<option value="${t}" ${state.tableScope === t ? "selected" : ""}>📋 ${t}</option>`)
  ];
  select.innerHTML = options.join("");
}

async function loadSchemaMetadata() {
  try {
    const res = await fetch("/api/v1/dashboard/schema-meta");
    if (res.ok) {
      state.schemaMeta = await res.json();
      populateTableDropdown();
      populateTableScopeDropdown();
    }
  } catch (err) {
    console.warn("Failed to load schema metadata:", err);
  }
}

async function loadDashboardConfig() {
  try {
    const res = await fetch("/api/v1/dashboard/config");
    if (res.ok) {
      const data = await res.json();
      if (data.config) {
        state.customConfig = data.config;
      } else {
        const local = localStorage.getItem("text2sql_dashboard_config");
        if (local) {
          state.customConfig = JSON.parse(local);
        }
      }
    }
  } catch (err) {
    console.warn("Failed to load saved dashboard config:", err);
  }
}

async function loadDashboardMetrics() {
  try {
    const params = new URLSearchParams();
    if (state.tableScope && state.tableScope !== "all") {
      params.append("table_scope", state.tableScope);
    }
    for (const [k, v] of Object.entries(state.filters)) {
      if (v && v !== "all") params.append(k, v);
    }

    const queryStr = params.toString() ? `?${params.toString()}` : "";
    const res = await fetch(`/api/v1/dashboard/metrics${queryStr}`);
    
    if (res.ok) {
      state.data = await res.json();
    } else {
      const fallback = await fetch(`/dashboard/metrics${queryStr}`);
      state.data = await fallback.json();
    }
    
    populateTableScopeDropdown();
    renderDynamicFilters(state.data.filters);
    await renderDashboard();
  } catch (err) {
    console.error("Failed to load dashboard metrics:", err);
    showToast("Error fetching metrics from active database", "error");
  }
}

// Auto-generate dashboard for active database
async function triggerAutoGenerateDashboard() {
  try {
    showToast("Analyzing active database schema & generating dashboard...", "success");
    const res = await fetch("/api/v1/dashboard/generate", { method: "POST" });
    if (res.ok) {
      const data = await res.json();
      state.customConfig = { overrides: {}, custom_cards: [] };
      localStorage.removeItem("text2sql_dashboard_config");
      state.data = data.metrics;
      renderDynamicFilters(state.data.filters);
      await renderDashboard();
      showToast("✨ Dashboard successfully generated for active database!", "success");
    }
  } catch (err) {
    showToast(`Generation failed: ${err.message}`, "error");
  }
}


// ======================================================================
// Dynamic Global Filter Renderer
// ======================================================================

function renderDynamicFilters(filtersList = []) {
  const container = document.getElementById("dynamicFiltersContainer");
  const btnClear = document.getElementById("btnClearFilters");
  if (!container) return;

  if (!filtersList || filtersList.length === 0) {
    container.innerHTML = `<span class="stat-subtitle text-muted">No categorical dimensions found</span>`;
    if (btnClear) btnClear.style.display = "none";
    return;
  }

  // Preserve selected values if any
  container.innerHTML = filtersList.map(f => {
    const currentVal = state.filters[f.column] || "all";
    const opts = (f.options || []).map(opt => `
      <option value="${opt}" ${opt === currentVal ? "selected" : ""}>${opt}</option>
    `).join("");

    return `
      <select class="filter-select" data-dimension="${f.column}" title="Filter by ${f.label}">
        <option value="all">All ${f.label}s</option>
        ${opts}
      </select>
    `;
  }).join("");

  // Attach event listeners to filter dropdowns
  container.querySelectorAll(".filter-select").forEach(sel => {
    sel.addEventListener("change", (e) => {
      const dim = e.target.dataset.dimension;
      state.filters[dim] = e.target.value;
      loadDashboardMetrics();
    });
  });

  // Show/Hide Clear button
  const hasActive = Object.values(state.filters).some(v => v && v !== "all");
  if (btnClear) {
    btnClear.style.display = hasActive ? "inline-block" : "none";
  }
}


// ======================================================================
// Dashboard Render Engine
// ======================================================================

async function renderDashboard() {
  if (!state.data) return;
  const d = state.data;

  // 1. Active Database Badge
  const activeDbBadge = document.getElementById("activeDbBadge");
  if (activeDbBadge && d.active_database) {
    activeDbBadge.textContent = `${d.active_database} (${(d.db_type || "sqlite").toUpperCase()})`;
  }

  // 2. Render Dynamic Top KPI Cards
  renderTopGridCards(d.top_metrics || []);

  // 3. Render Dynamic Sidebar Cards
  renderSidebarCards(d.sidebar_metrics || []);

  // 4. Render Dynamic Ribbon Cards
  renderRibbonCards(d.ribbon_metrics || []);

  // 5. Render Primary Visual Donut Chart
  renderPrimaryChart(d.collection_analytics || {});

  // 6. Render Distribution Matrix Table
  renderMatrixTable(d.bucket_movement || {});

  // 7. Render Analytics Tab Bars
  renderAnalyticsTab(d.analytics || {});

  // 8. Rebind Edit Buttons
  bindMetricEditButtons();
}

// 2. Render Top KPI Grid
function renderTopGridCards(topMetrics) {
  const container = document.getElementById("topGridContainer");
  if (!container) return;

  const cardsHtml = topMetrics.map((card, idx) => {
    const override = state.customConfig.overrides?.[card.id];
    const spec = override || card;
    const displayVal = formatValueBySpec(spec.evaluatedValue !== undefined ? spec.evaluatedValue : card.value, spec.format || "number");
    const color = spec.color || "blue";
    const icon = spec.icon || "chart";

    return `
      <div class="top-metric-card" data-metric-id="${spec.id}" data-section="top">
        <div class="card-hover-actions">
          <button class="card-action-btn btn-edit-metric" title="Edit Metric" data-metric-id="${spec.id}">✏️</button>
        </div>
        <div class="top-card-body">
          <div class="metric-title">${spec.title}</div>
          <div class="metric-number">${displayVal}</div>
          <div class="metric-sub-label text-muted">${spec.subtitle || 'Tracked Metric'}</div>
        </div>
        <div class="top-card-icon icon-${color}">
          ${getIconSvg(icon)}
        </div>
      </div>
    `;
  }).join("");

  // Also include user custom cards for top grid
  const customTop = (state.customConfig.custom_cards || []).filter(c => c.section === "top");
  const customHtml = customTop.map(spec => `
    <div class="top-metric-card" data-metric-id="${spec.id}" data-section="top">
      <div class="card-hover-actions">
        <button class="card-action-btn btn-edit-metric" title="Edit Metric" data-metric-id="${spec.id}">✏️</button>
      </div>
      <div class="top-card-body">
        <div class="metric-title">${spec.title}</div>
        <div class="metric-number">${formatValueBySpec(spec.evaluatedValue || 0, spec.format || "number")}</div>
        <div class="metric-sub-label text-muted">${spec.subtitle || 'Custom Metric'}</div>
      </div>
      <div class="top-card-icon icon-${spec.color || 'blue'}">
        ${getIconSvg(spec.icon || 'chart')}
      </div>
    </div>
  `).join("");

  let addSlotHtml = "";
  if (state.isEditMode) {
    addSlotHtml = `
      <div class="add-card-slot" onclick="openMetricModal(null, 'top')">
        <span>➕ Add Top KPI</span>
      </div>
    `;
  }

  container.innerHTML = cardsHtml + customHtml + addSlotHtml;
}

// 3. Render Sidebar Cards
function renderSidebarCards(sidebarMetrics) {
  const container = document.getElementById("sidebarCardsContainer");
  if (!container) return;

  const cardsHtml = sidebarMetrics.map(card => {
    const override = state.customConfig.overrides?.[card.id];
    const spec = override || card;
    const displayVal = formatValueBySpec(spec.evaluatedValue !== undefined ? spec.evaluatedValue : card.value, spec.format || "currency_inr");
    const color = spec.color || "rose";

    return `
      <div class="stat-card-custom card-${color}" data-metric-id="${spec.id}" data-section="sidebar">
        <div class="card-hover-actions">
          <button class="card-action-btn btn-edit-metric" title="Edit Metric" data-metric-id="${spec.id}">✏️</button>
        </div>
        <div class="stat-header-label">${spec.title}</div>
        <div class="stat-value text-${color}">${displayVal}</div>
        <div class="stat-subtitle text-muted">${spec.subtitle || 'Measure'}</div>
      </div>
    `;
  }).join("");

  const customSide = (state.customConfig.custom_cards || []).filter(c => c.section === "sidebar");
  const customHtml = customSide.map(spec => `
    <div class="stat-card-custom card-${spec.color || 'blue'}" data-metric-id="${spec.id}" data-section="sidebar">
      <div class="card-hover-actions">
        <button class="card-action-btn btn-edit-metric" title="Edit Metric" data-metric-id="${spec.id}">✏️</button>
      </div>
      <div class="stat-header-label">${spec.title}</div>
      <div class="stat-value text-${spec.color || 'success'}">${formatValueBySpec(spec.evaluatedValue || 0, spec.format || "number")}</div>
      <div class="stat-subtitle text-muted">${spec.subtitle || 'Custom Metric'}</div>
    </div>
  `).join("");

  let addSlotHtml = "";
  if (state.isEditMode) {
    addSlotHtml = `
      <div class="add-card-slot" onclick="openMetricModal(null, 'sidebar')">
        <span>➕ Add Sidebar Stat</span>
      </div>
    `;
  }

  container.innerHTML = cardsHtml + customHtml + addSlotHtml;
}

// 4. Render Ribbon Cards
function renderRibbonCards(ribbonMetrics) {
  const container = document.getElementById("ribbonGridContainer");
  if (!container) return;

  const cardsHtml = ribbonMetrics.map(card => {
    const override = state.customConfig.overrides?.[card.id];
    const spec = override || card;
    const displayVal = formatValueBySpec(spec.evaluatedValue !== undefined ? spec.evaluatedValue : card.value, spec.format || "currency_inr");
    const color = spec.color || "blue";

    return `
      <div class="ribbon-card ribbon-${color}" data-metric-id="${spec.id}" data-section="ribbon">
        <div class="card-hover-actions">
          <button class="card-action-btn btn-edit-metric" title="Edit Metric" data-metric-id="${spec.id}">✏️</button>
        </div>
        <div class="ribbon-card-header">
          <span>${spec.title}</span>
          <span>⚡</span>
        </div>
        <div class="ribbon-value">${displayVal}</div>
      </div>
    `;
  }).join("");

  const customRibbon = (state.customConfig.custom_cards || []).filter(c => c.section === "ribbon");
  const customHtml = customRibbon.map(spec => `
    <div class="ribbon-card ribbon-${spec.color || 'blue'}" data-metric-id="${spec.id}" data-section="ribbon">
      <div class="card-hover-actions">
        <button class="card-action-btn btn-edit-metric" title="Edit Metric" data-metric-id="${spec.id}">✏️</button>
      </div>
      <div class="ribbon-card-header">
        <span>${spec.title}</span>
        <span>⚡</span>
      </div>
      <div class="ribbon-value">${formatValueBySpec(spec.evaluatedValue || 0, spec.format || "currency_inr")}</div>
    </div>
  `).join("");

  container.innerHTML = cardsHtml + customHtml;
}

// 5. Render Primary Visual Donut Chart
function renderPrimaryChart(chartData) {
  const titleEl = document.getElementById("primaryChartTitle");
  const subEl = document.getElementById("collectionAnalyticsSub");
  if (titleEl && chartData.title) titleEl.textContent = chartData.title;

  if (subEl) {
    subEl.textContent = `Total ${formatINR(chartData.total_amount || 0)} | ${formatNumber(chartData.total_collections || 0)} Records`;
  }

  document.getElementById("pillTotalAmount").textContent = formatINR(chartData.total_amount || 0);
  document.getElementById("pillUniqueCases").textContent = formatNumber(chartData.total_unique_cases || 0);
  document.getElementById("pillAvgPerCase").textContent = formatINR(chartData.avg_per_case || 0);

  const breakdown = chartData.breakdown || [];
  const listEl = document.getElementById("breakdownList");
  let primaryPct = "0%";

  if (listEl) {
    if (breakdown.length === 0) {
      listEl.innerHTML = `<div class="empty-placeholder-text">No categorical breakdown available</div>`;
    } else {
      listEl.innerHTML = breakdown.map(item => {
        if (item.percentage > 0 && primaryPct === "0%") {
          primaryPct = `${item.percentage}%`;
        }
        return `
          <div class="breakdown-item" data-type="${item.key}">
            <div class="breakdown-left">
              <span class="status-dot" style="background-color: ${item.color || '#38bdf8'}; box-shadow: 0 0 8px ${item.color || '#38bdf8'};"></span>
              <div>
                <div class="breakdown-name">${item.name}</div>
                <div class="breakdown-count">${formatNumber(item.count)} Records</div>
              </div>
            </div>
            <div class="breakdown-right">
              <div class="breakdown-amount">${formatINR(item.amount)}</div>
              <div class="breakdown-pct">${item.percentage || 0}%</div>
            </div>
          </div>
        `;
      }).join("");
    }
  }

  const donutPrimaryPct = document.getElementById("donutPrimaryPct");
  if (donutPrimaryPct) {
    donutPrimaryPct.textContent = primaryPct !== "0%" ? primaryPct : "100%";
  }

  drawDonutChart("donutChartCanvas", breakdown);
}

// Canvas Donut Renderer
function drawDonutChart(canvasId, breakdown) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  const width = 170;
  const height = 170;
  const dpr = window.devicePixelRatio || 1;

  canvas.width = width * dpr;
  canvas.height = height * dpr;
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;

  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  // Reset any previous transform
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.scale(dpr, dpr);

  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.min(centerX, centerY) - 8;
  const innerRadius = radius * 0.70;

  ctx.clearRect(0, 0, width, height);

  const validItems = (breakdown || []).filter(i => (i.amount || 0) > 0);
  const total = validItems.reduce((sum, i) => sum + i.amount, 0);

  if (total === 0) {
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, 2 * Math.PI);
    ctx.arc(centerX, centerY, innerRadius, 2 * Math.PI, 0, true);
    ctx.fillStyle = "rgba(255, 255, 255, 0.08)";
    ctx.fill();
    return;
  }

  let startAngle = -0.5 * Math.PI;

  validItems.forEach(item => {
    const sliceAngle = (item.amount / total) * 2 * Math.PI;
    const endAngle = startAngle + sliceAngle;

    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, startAngle, endAngle);
    ctx.arc(centerX, centerY, innerRadius, endAngle, startAngle, true);
    ctx.closePath();
    ctx.fillStyle = item.color || "#38bdf8";
    ctx.fill();

    ctx.strokeStyle = "#0b0f19";
    ctx.lineWidth = 2;
    ctx.stroke();

    startAngle = endAngle;
  });
}

// 6. Render Matrix Table
function renderMatrixTable(matrixData) {
  const titleEl = document.getElementById("matrixTitle");
  const colHeadEl = document.getElementById("matrixColHeader1");
  const tableBody = document.getElementById("bucketTableBody");

  if (titleEl && matrixData.title) titleEl.textContent = matrixData.title;
  if (colHeadEl && matrixData.dimension) colHeadEl.textContent = matrixData.dimension.toUpperCase();

  if (!tableBody) return;

  if (!matrixData || !matrixData.has_data || !matrixData.items || matrixData.items.length === 0) {
    tableBody.innerHTML = `<tr><td colspan="4" style="text-align:center; color: var(--text-muted); padding: 32px;">No matrix distribution records available</td></tr>`;
    return;
  }

  const maxCases = Math.max(...matrixData.items.map(i => i.cases), 1);
  tableBody.innerHTML = matrixData.items.map(item => `
    <tr>
      <td><span class="badge badge-bucket">${item.bucket}</span></td>
      <td><strong>${formatNumber(item.cases)}</strong></td>
      <td>${formatINR(item.dues)}</td>
      <td>
        <div class="table-bar-wrap" title="${item.share}% share">
          <div class="table-progress-bar" style="width: ${(item.cases / maxCases) * 100}%;"></div>
        </div>
      </td>
    </tr>
  `).join("");
}

// 7. Render Analytics Tab Bars
function renderAnalyticsTab(analytics) {
  if (!analytics) return;

  const geoTitle = document.getElementById("analyticsGeoTitle");
  const modeTitle = document.getElementById("analyticsModeTitle");
  if (geoTitle && analytics.geo_title) geoTitle.textContent = analytics.geo_title;
  if (modeTitle && analytics.mode_title) modeTitle.textContent = analytics.mode_title;

  const stateContainer = document.getElementById("stateBarsContainer");
  if (stateContainer && analytics.by_state) {
    if (analytics.by_state.length === 0) {
      stateContainer.innerHTML = `<div class="empty-placeholder-text">No dimension data available</div>`;
    } else {
      const maxAmt = Math.max(...analytics.by_state.map(s => s.amount), 1);
      stateContainer.innerHTML = analytics.by_state.map(s => `
        <div class="analytics-bar-row">
          <div class="bar-label-group">
            <span class="bar-name">${s.state}</span>
            <span class="bar-val">${formatINR(s.amount)} (${formatNumber(s.count)} records)</span>
          </div>
          <div class="bar-track">
            <div class="bar-fill fill-blue" style="width: ${(s.amount / maxAmt) * 100}%;"></div>
          </div>
        </div>
      `).join("");
    }
  }

  const modeContainer = document.getElementById("modeBarsContainer");
  if (modeContainer && analytics.by_mode) {
    if (analytics.by_mode.length === 0) {
      modeContainer.innerHTML = `<div class="empty-placeholder-text">No category data available</div>`;
    } else {
      const maxAmt = Math.max(...analytics.by_mode.map(m => m.amount), 1);
      modeContainer.innerHTML = analytics.by_mode.map(m => `
        <div class="analytics-bar-row">
          <div class="bar-label-group">
            <span class="bar-name">${m.mode}</span>
            <span class="bar-val">${formatINR(m.amount)} (${formatNumber(m.count)} records)</span>
          </div>
          <div class="bar-track">
            <div class="bar-fill fill-green" style="width: ${(m.amount / maxAmt) * 100}%;"></div>
          </div>
        </div>
      `).join("");
    }
  }
}


// ======================================================================
// Metric Customizer Modal & Builder Logic
// ======================================================================

function bindMetricEditButtons() {
  document.querySelectorAll(".btn-edit-metric").forEach(btn => {
    btn.onclick = (e) => {
      e.stopPropagation();
      const metricId = btn.dataset.metricId;
      openMetricModal(metricId);
    };
  });
}

function openMetricModal(metricId = null, defaultSection = "top") {
  state.editingMetricId = metricId;

  const backdrop = document.getElementById("metricModalBackdrop");
  const modalTitle = document.getElementById("modalTitleText");
  const btnDelete = document.getElementById("btnDeleteCustomMetric");

  let spec = null;
  if (metricId) {
    // Look up in custom overrides, custom cards, or auto-generated lists
    spec = state.customConfig.overrides?.[metricId] ||
           state.customConfig.custom_cards?.find(c => c.id === metricId) ||
           state.data?.top_metrics?.find(c => c.id === metricId) ||
           state.data?.sidebar_metrics?.find(c => c.id === metricId) ||
           state.data?.ribbon_metrics?.find(c => c.id === metricId) || {
             id: metricId,
             title: "Metric",
             section: defaultSection,
             format: "currency_inr",
             color: "blue",
             icon: "chart",
             mode: "builder"
           };
    modalTitle.textContent = `Customize Metric: ${spec.title || 'Metric'}`;
    const isCustom = state.customConfig.custom_cards?.some(c => c.id === metricId);
    btnDelete.style.display = isCustom ? "inline-flex" : "none";
  } else {
    // Brand new custom metric
    spec = {
      id: `custom_${Date.now()}`,
      title: "New Custom Metric",
      section: defaultSection,
      format: "currency_inr",
      color: "blue",
      icon: "chart",
      mode: "builder",
      builder: {
        table: state.schemaMeta.table_list[0] || state.data?.primary_table || "",
        column: "*",
        aggregation: "COUNT",
        filters: []
      }
    };
    modalTitle.textContent = "Create Custom Metric";
    btnDelete.style.display = "none";
  }

  state.editingMetricSpec = spec;

  // Populate general inputs
  document.getElementById("metricInputTitle").value = spec.title || "";
  document.getElementById("metricInputSection").value = spec.section || defaultSection;
  document.getElementById("metricInputFormat").value = spec.format || "currency_inr";
  document.getElementById("metricInputColor").value = spec.color || "blue";
  document.getElementById("metricInputIcon").value = spec.icon || "chart";

  setModalMode(spec.mode || "builder");

  // Populate Builder
  if (spec.builder) {
    const tblSelect = document.getElementById("builderTableSelect");
    if (tblSelect) {
      tblSelect.value = spec.builder.table || tblSelect.options[0]?.value || "";
      updateColumnDropdown(tblSelect.value);
    }
    
    document.getElementById("builderAggSelect").value = spec.builder.aggregation || "SUM";
    document.getElementById("builderColumnSelect").value = spec.builder.column || "*";

    const rulesContainer = document.getElementById("builderFilterRules");
    rulesContainer.innerHTML = "";
    if (spec.builder.filters && spec.builder.filters.length > 0) {
      spec.builder.filters.forEach(f => addFilterRuleRow(f.column, f.operator, f.value));
    }
  }

  document.getElementById("sqlInputTextarea").value = spec.sql || "";
  document.getElementById("manualInputValue").value = spec.manual_value || "";

  backdrop.classList.add("open");
  testCurrentModalMetric();
}

function closeMetricModal() {
  const backdrop = document.getElementById("metricModalBackdrop");
  backdrop.classList.remove("open");
  state.editingMetricId = null;
  state.editingMetricSpec = null;
}

function setModalMode(mode) {
  state.activeModalMode = mode;

  document.querySelectorAll(".modal-tab-btn").forEach(b => {
    b.classList.toggle("active", b.dataset.mode === mode);
  });

  document.getElementById("modePanelBuilder").style.display = mode === "builder" ? "block" : "none";
  document.getElementById("modePanelSql").style.display = mode === "sql" ? "block" : "none";
  document.getElementById("modePanelManual").style.display = mode === "manual" ? "block" : "none";
}

function populateTableDropdown() {
  const tblSelect = document.getElementById("builderTableSelect");
  if (!tblSelect) return;

  tblSelect.innerHTML = state.schemaMeta.table_list.map(t => `<option value="${t}">${t}</option>`).join("");
  if (state.schemaMeta.table_list.length > 0) {
    updateColumnDropdown(state.schemaMeta.table_list[0]);
  }
}

function updateColumnDropdown(tableName) {
  const colSelect = document.getElementById("builderColumnSelect");
  if (!colSelect) return;

  const cols = state.schemaMeta.tables[tableName] || [];
  let opts = `<option value="*">* (All Rows / COUNT)</option>`;
  cols.forEach(c => {
    const hint = c.is_numeric ? " [123]" : (c.is_date ? " [date]" : "");
    opts += `<option value="${c.name}">${c.name}${hint}</option>`;
  });
  colSelect.innerHTML = opts;
}

function addFilterRuleRow(column = "", operator = "=", value = "") {
  const container = document.getElementById("builderFilterRules");
  const tableName = document.getElementById("builderTableSelect").value;
  const cols = state.schemaMeta.tables[tableName] || [];

  const row = document.createElement("div");
  row.className = "filter-rule-row";

  const colOptions = cols.map(c => `<option value="${c.name}" ${c.name === column ? 'selected' : ''}>${c.name}</option>`).join("");

  row.innerHTML = `
    <select class="form-control rule-col">${colOptions}</select>
    <select class="form-control rule-op">
      <option value="=" ${operator === '=' ? 'selected' : ''}>Equals (=)</option>
      <option value="!=" ${operator === '!=' ? 'selected' : ''}>Not Equals (!=)</option>
      <option value="LIKE" ${operator === 'LIKE' ? 'selected' : ''}>Contains (LIKE)</option>
      <option value=">" ${operator === '>' ? 'selected' : ''}>Greater Than (&gt;)</option>
      <option value="<" ${operator === '<' ? 'selected' : ''}>Less Than (&lt;)</option>
      <option value="IS NOT NULL" ${operator === 'IS NOT NULL' ? 'selected' : ''}>Is Not Null</option>
    </select>
    <input type="text" class="form-control rule-val" placeholder="Value..." value="${value || ''}">
    <button type="button" class="btn-remove-rule" title="Remove condition">✕</button>
  `;

  row.querySelector(".btn-remove-rule").onclick = () => row.remove();
  container.appendChild(row);
}

function getModalMetricSpec() {
  const mode = state.activeModalMode;
  const title = document.getElementById("metricInputTitle").value.trim() || "Metric";
  const section = document.getElementById("metricInputSection").value;
  const format = document.getElementById("metricInputFormat").value;
  const color = document.getElementById("metricInputColor").value;
  const icon = document.getElementById("metricInputIcon").value;

  const spec = {
    id: state.editingMetricId || `custom_${Date.now()}`,
    title,
    section,
    format,
    color,
    icon,
    mode
  };

  if (mode === "builder") {
    const table = document.getElementById("builderTableSelect").value;
    const column = document.getElementById("builderColumnSelect").value;
    const agg = document.getElementById("builderAggSelect").value;

    const filters = [];
    document.querySelectorAll(".filter-rule-row").forEach(r => {
      const c = r.querySelector(".rule-col").value;
      const op = r.querySelector(".rule-op").value;
      const v = r.querySelector(".rule-val").value;
      if (c) filters.push({ column: c, operator: op, value: v });
    });

    spec.builder = { table, column, aggregation: agg, filters };
  } else if (mode === "sql") {
    spec.sql = document.getElementById("sqlInputTextarea").value.trim();
  } else if (mode === "manual") {
    spec.manual_value = document.getElementById("manualInputValue").value;
    spec.subtitle = document.getElementById("manualInputNote").value;
  }

  return spec;
}

async function evaluateMetricSpec(spec) {
  const payload = {
    ...spec,
    global_filters: state.filters
  };

  const res = await fetch("/api/v1/dashboard/metric/evaluate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Evaluation failed");
  }

  return await res.json();
}

async function testCurrentModalMetric() {
  const previewVal = document.getElementById("previewMetricValue");
  const previewSub = document.getElementById("previewMetricSub");
  previewVal.textContent = "Calculating...";

  try {
    const spec = getModalMetricSpec();
    const result = await evaluateMetricSpec(spec);

    if (result.error) {
      previewVal.textContent = "Error";
      previewSub.textContent = result.error;
    } else {
      previewVal.textContent = formatValueBySpec(result.value, spec.format);
      previewSub.textContent = `Calculated in ${result.execution_time_ms}ms (${spec.mode.toUpperCase()})`;
    }
  } catch (err) {
    previewVal.textContent = "Error";
    previewSub.textContent = err.message;
  }
}

async function saveMetricFromModal() {
  const spec = getModalMetricSpec();

  try {
    const evalRes = await evaluateMetricSpec(spec);
    spec.evaluatedValue = evalRes.value;

    const isCustom = state.customConfig.custom_cards?.some(c => c.id === spec.id) || !state.editingMetricId;

    if (isCustom) {
      if (!state.customConfig.custom_cards) state.customConfig.custom_cards = [];
      const idx = state.customConfig.custom_cards.findIndex(c => c.id === spec.id);
      if (idx >= 0) {
        state.customConfig.custom_cards[idx] = spec;
      } else {
        state.customConfig.custom_cards.push(spec);
      }
    } else {
      if (!state.customConfig.overrides) state.customConfig.overrides = {};
      state.customConfig.overrides[spec.id] = spec;
    }

    await persistDashboardConfig();
    closeMetricModal();
    showToast(`Metric '${spec.title}' saved successfully!`, "success");
    await renderDashboard();
  } catch (err) {
    showToast(`Failed to save: ${err.message}`, "error");
  }
}

async function deleteCustomMetric() {
  if (!state.editingMetricId) return;

  const id = state.editingMetricId;
  if (state.customConfig.custom_cards) {
    state.customConfig.custom_cards = state.customConfig.custom_cards.filter(c => c.id !== id);
  }
  if (state.customConfig.overrides && state.customConfig.overrides[id]) {
    delete state.customConfig.overrides[id];
  }

  await persistDashboardConfig();
  closeMetricModal();
  showToast("Metric removed", "success");
  await renderDashboard();
}

async function persistDashboardConfig() {
  localStorage.setItem("text2sql_dashboard_config", JSON.stringify(state.customConfig));
  try {
    await fetch("/api/v1/dashboard/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config: state.customConfig })
    });
  } catch (e) {
    console.warn("Could not persist config to backend server:", e);
  }
}

async function resetAllDashboardConfig() {
  if (!confirm("Are you sure you want to reset all modified metrics back to system defaults?")) return;

  state.customConfig = { overrides: {}, custom_cards: [] };
  localStorage.removeItem("text2sql_dashboard_config");

  try {
    await fetch("/api/v1/dashboard/config/reset", { method: "POST" });
  } catch (e) {}

  showToast("Dashboard reset to system defaults", "success");
  await loadDashboardMetrics();
}


// ======================================================================
// Initialization & Event Listeners
// ======================================================================

function initEventListeners() {
  // Tabs (Overview vs Analytics)
  const tabOverviewBtn = document.getElementById("tabOverviewBtn");
  const tabAnalyticsBtn = document.getElementById("tabAnalyticsBtn");
  const viewOverview = document.getElementById("viewOverview");
  const viewAnalytics = document.getElementById("viewAnalytics");

  if (tabOverviewBtn && tabAnalyticsBtn) {
    tabOverviewBtn.onclick = () => {
      tabOverviewBtn.classList.add("active");
      tabAnalyticsBtn.classList.remove("active");
      viewOverview.style.display = "flex";
      viewAnalytics.style.display = "none";
      state.currentTab = "overview";
    };

    tabAnalyticsBtn.onclick = () => {
      tabAnalyticsBtn.classList.add("active");
      tabOverviewBtn.classList.remove("active");
      viewOverview.style.display = "none";
      viewAnalytics.style.display = "flex";
      state.currentTab = "analytics";
    };
  }

  // Edit Mode Switch
  const editToggle = document.getElementById("editModeToggle");
  const wrapper = document.getElementById("dashboardWrapper");
  if (editToggle) {
    editToggle.onclick = () => {
      state.isEditMode = !state.isEditMode;
      editToggle.classList.toggle("active", state.isEditMode);
      wrapper.classList.toggle("edit-mode-active", state.isEditMode);
      renderDashboard();
    };
  }

  // Action Bar Buttons
  document.getElementById("btnAutoGenerateDb")?.addEventListener("click", triggerAutoGenerateDashboard);
  document.getElementById("btnAddMetric")?.addEventListener("click", () => openMetricModal(null, "top"));
  document.getElementById("btnRefreshDashboard")?.addEventListener("click", () => {
    showToast("Refreshing metrics from database...");
    loadDashboardMetrics();
  });
  document.getElementById("btnResetDashboard")?.addEventListener("click", resetAllDashboardConfig);

  // Table Scope Switcher (Unified vs Individual Table Drilldown)
  const scopeSelect = document.getElementById("tableScopeSelect");
  if (scopeSelect) {
    scopeSelect.addEventListener("change", (e) => {
      state.tableScope = e.target.value;
      state.filters = {};
      showToast(`Switched table scope: ${e.target.value === 'all' ? 'All Tables (Unified)' : e.target.value}`);
      loadDashboardMetrics();
    });
  }

  // Clear Filters
  document.getElementById("btnClearFilters")?.addEventListener("click", () => {
    state.filters = {};
    document.querySelectorAll("#dynamicFiltersContainer .filter-select").forEach(sel => sel.value = "all");
    loadDashboardMetrics();
  });

  // Modal Controls
  document.getElementById("modalCloseBtn")?.addEventListener("click", closeMetricModal);
  document.getElementById("modalCancelBtn")?.addEventListener("click", closeMetricModal);
  document.getElementById("btnSaveMetricConfig")?.addEventListener("click", saveMetricFromModal);
  document.getElementById("btnDeleteCustomMetric")?.addEventListener("click", deleteCustomMetric);
  document.getElementById("btnTestMetricQuery")?.addEventListener("click", testCurrentModalMetric);

  // Modal Mode Tabs
  document.getElementById("modalTabBuilder")?.addEventListener("click", () => setModalMode("builder"));
  document.getElementById("modalTabSql")?.addEventListener("click", () => setModalMode("sql"));
  document.getElementById("modalTabManual")?.addEventListener("click", () => setModalMode("manual"));

  // Builder Table Select change -> update column select
  document.getElementById("builderTableSelect")?.addEventListener("change", (e) => {
    updateColumnDropdown(e.target.value);
  });

  // Add Filter Rule button
  document.getElementById("btnAddFilterRule")?.addEventListener("click", () => addFilterRuleRow());

  // Hub View Tabs (Matrix vs Geography vs Payment Modes)
  const hubTabs = [
    { btn: document.getElementById("hubTabMatrix"), view: document.getElementById("hubViewMatrix") },
    { btn: document.getElementById("hubTabGeo"), view: document.getElementById("hubViewGeo") },
    { btn: document.getElementById("hubTabMode"), view: document.getElementById("hubViewMode") }
  ];

  hubTabs.forEach(({ btn, view }) => {
    if (btn && view) {
      btn.addEventListener("click", () => {
        hubTabs.forEach(h => {
          if (h.btn) h.btn.classList.toggle("active", h.btn === btn);
          if (h.view) h.view.style.display = h.btn === btn ? "block" : "none";
        });
      });
    }
  });
}

// Database Connection Switcher
async function loadDatabaseProfiles() {
  const select = document.getElementById("dbProfileSelect");
  if (!select) return;

  try {
    const res = await fetch("/api/v1/connections");
    if (res.ok) {
      const connections = await res.json();
      if (connections.length > 0) {
        select.innerHTML = connections.map(c => `
          <option value="${c.id}" ${c.is_active ? "selected" : ""}>
            ${c.reference_name} (${c.db_type.toUpperCase()})
          </option>
        `).join("");
      } else {
        select.innerHTML = `<option value="default">Default SQLite (app.db)</option>`;
      }
    }
  } catch (e) {
    select.innerHTML = `<option value="default">Default SQLite (app.db)</option>`;
  }

  select.addEventListener("change", async (e) => {
    const connId = e.target.value;
    if (connId && connId !== "default") {
      try {
        const actRes = await fetch(`/api/v1/connections/${connId}/activate`, { method: "POST" });
        if (actRes.ok) {
          showToast("Switched active database connection");
          state.filters = {};
          await loadSchemaMetadata();
          await loadDashboardConfig();
          await loadDashboardMetrics();
        }
      } catch (err) {
        console.error("Failed to activate DB:", err);
      }
    }
  });
}

// Boot
document.addEventListener("DOMContentLoaded", async () => {
  initEventListeners();
  await loadDatabaseProfiles();
  await loadSchemaMetadata();
  await loadDashboardConfig();
  await loadDashboardMetrics();
});
