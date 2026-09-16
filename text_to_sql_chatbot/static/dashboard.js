/**
 * Dashboard JavaScript - Loan & Collections Analytics
 */

// State
let dashboardData = null;
let currentTab = "overview";
let isMatrixVisible = false;

// Currency Formatter
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

  // Standard Indian formatting
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

// Fetch Metrics
async function loadDashboardMetrics() {
  try {
    const res = await fetch("/api/v1/dashboard/metrics");
    if (!res.ok) {
      // Fallback route
      const fallback = await fetch("/dashboard/metrics");
      dashboardData = await fallback.json();
    } else {
      dashboardData = await res.json();
    }
    renderDashboard(dashboardData);
  } catch (err) {
    console.error("Failed to load dashboard metrics:", err);
  }
}

// Render All Elements
function renderDashboard(data) {
  if (!data) return;

  // Active DB Badge
  const activeDbBadge = document.getElementById("activeDbBadge");
  if (activeDbBadge && data.active_database) {
    activeDbBadge.textContent = `${data.active_database} (${(data.db_type || "sqlite").toUpperCase()})`;
  }

  // 1. Sidebar Metrics
  const side = data.sidebar || {};
  document.getElementById("sideTotalDues").textContent = formatINR(side.total_dues);
  document.getElementById("sideEmiDues").textContent = formatINR(side.emi_dues);
  document.getElementById("sideOtherCharges").textContent = formatINR(side.other_charges);
  document.getElementById("sideUserActivity").textContent = `${formatNumber(side.active_users)} / ${formatNumber(side.total_users)}`;

  // 2. Top Metric Cards
  const top = data.top_metrics || {};
  document.getElementById("metricTotalCases").textContent = formatNumber(top.total_cases);
  document.getElementById("metricUnallocatedCases").textContent = formatNumber(top.unallocated_cases);
  document.getElementById("metricPtpPlanned").textContent = formatINR(top.ptp_planned);
  document.getElementById("metricCollections").textContent = formatINR(top.collections);
  document.getElementById("metricResolution").textContent = `${top.resolution || 0}%`;

  // 3. Middle Ribbon Cards
  const ribbon = data.ribbon || {};
  document.getElementById("ribbonPlanned").textContent = formatINR(ribbon.planned_collections);
  document.getElementById("ribbonUnplanned").textContent = formatINR(ribbon.unplanned_collections);
  document.getElementById("ribbonTotal").textContent = formatINR(ribbon.total_collections);

  // 4. Collection Analytics
  const coll = data.collection_analytics || {};
  document.getElementById("collectionAnalyticsSub").textContent = 
    `Total ${formatINR(coll.total_amount)} | ${formatNumber(coll.total_collections)} Collections`;

  // Summary Pills
  document.getElementById("pillTotalAmount").textContent = formatINR(coll.total_amount);
  document.getElementById("pillUniqueCases").textContent = formatNumber(coll.total_unique_cases);
  document.getElementById("pillAvgPerCase").textContent = formatINR(coll.avg_per_case);

  // Breakdown items
  const breakdown = coll.breakdown || [];
  let primaryPct = "0%";

  breakdown.forEach(item => {
    const key = item.key;
    const countEl = document.getElementById(`count${capitalize(key)}`);
    const amountEl = document.getElementById(`amount${capitalize(key)}`);
    const pctEl = document.getElementById(`pct${capitalize(key)}`);

    if (countEl) countEl.textContent = `${formatNumber(item.count)} Collections`;
    if (amountEl) amountEl.textContent = formatINR(item.amount);
    if (pctEl) pctEl.textContent = `${item.percentage || 0}%`;

    if (item.percentage > 0 && primaryPct === "0%") {
      primaryPct = `${item.percentage}%`;
    }
  });

  const donutPrimaryPct = document.getElementById("donutPrimaryPct");
  if (donutPrimaryPct) {
    donutPrimaryPct.textContent = primaryPct !== "0%" ? primaryPct : "100%";
  }

  // Draw Canvas Donut Chart
  drawDonutChart("donutChartCanvas", breakdown);

  // 5. Bucket Movement Data
  renderBucketMovement(data.bucket_movement);

  // 6. Analytics Tab Data
  renderAnalyticsTab(data.analytics);
}

function capitalize(s) {
  if (!s) return "";
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// Canvas Donut Chart Renderer
function drawDonutChart(canvasId, breakdown) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.min(centerX, centerY) - 10;
  const innerRadius = radius * 0.68;

  ctx.clearRect(0, 0, width, height);

  const validItems = breakdown.filter(i => (i.amount || 0) > 0);
  const total = validItems.reduce((sum, i) => sum + i.amount, 0);

  if (total === 0) {
    // Draw default empty ring
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, 2 * Math.PI);
    ctx.arc(centerX, centerY, innerRadius, 2 * Math.PI, 0, true);
    ctx.fillStyle = "#e2e8f0";
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
    ctx.fillStyle = item.color || "#3b82f6";
    ctx.fill();

    // Subtle white separator border between segments
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 2;
    ctx.stroke();

    startAngle = endAngle;
  });
}

// Bucket Movement
function renderBucketMovement(bucketData) {
  const emptyBox = document.getElementById("bucketEmptyBox");
  const matrixBox = document.getElementById("bucketMatrixBox");
  const tableBody = document.getElementById("bucketTableBody");

  if (!bucketData || !bucketData.has_data || !bucketData.items || bucketData.items.length === 0) {
    if (emptyBox) emptyBox.style.display = "flex";
    if (matrixBox) matrixBox.style.display = "none";
    return;
  }

  if (tableBody) {
    tableBody.innerHTML = bucketData.items.map(item => {
      return `
        <tr>
          <td><span class="badge badge-bucket">${item.bucket}</span></td>
          <td><strong>${formatNumber(item.cases)}</strong></td>
          <td>${formatINR(item.dues)}</td>
          <td>
            <div class="table-bar-wrap">
              <div class="table-progress-bar" style="width: ${Math.min(100, Math.max(8, (item.cases / (dashboardData?.top_metrics?.total_cases || 100)) * 100))}%;"></div>
            </div>
          </td>
        </tr>
      `;
    }).join("");
  }
}

// Analytics Tab Charts & Bars
function renderAnalyticsTab(analytics) {
  if (!analytics) return;

  // 1. State Performance
  const stateContainer = document.getElementById("stateBarsContainer");
  if (stateContainer && analytics.by_state) {
    if (analytics.by_state.length === 0) {
      stateContainer.innerHTML = `<div class="empty-state-text">No state performance data available</div>`;
    } else {
      const maxAmt = Math.max(...analytics.by_state.map(s => s.amount), 1);
      stateContainer.innerHTML = analytics.by_state.map(s => `
        <div class="analytics-bar-row">
          <div class="bar-label-group">
            <span class="bar-name">${s.state}</span>
            <span class="bar-val">${formatINR(s.amount)} (${formatNumber(s.count)} cases)</span>
          </div>
          <div class="bar-track">
            <div class="bar-fill fill-blue" style="width: ${(s.amount / maxAmt) * 100}%;"></div>
          </div>
        </div>
      `).join("");
    }
  }

  // 2. Mode Distribution
  const modeContainer = document.getElementById("modeBarsContainer");
  if (modeContainer && analytics.by_mode) {
    if (analytics.by_mode.length === 0) {
      modeContainer.innerHTML = `<div class="empty-state-text">No payment mode data available</div>`;
    } else {
      const maxAmt = Math.max(...analytics.by_mode.map(m => m.amount), 1);
      modeContainer.innerHTML = analytics.by_mode.map(m => `
        <div class="analytics-bar-row">
          <div class="bar-label-group">
            <span class="bar-name">${m.mode}</span>
            <span class="bar-val">${formatINR(m.amount)} (${formatNumber(m.count)} trans)</span>
          </div>
          <div class="bar-track">
            <div class="bar-fill fill-green" style="width: ${(m.amount / maxAmt) * 100}%;"></div>
          </div>
        </div>
      `).join("");
    }
  }
}

// Database Selector Integration
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
          loadDashboardMetrics();
        }
      } catch (err) {
        console.error("Failed to activate DB:", err);
      }
    }
  });
}

// Tab Switching Setup
function initTabs() {
  const tabOverviewBtn = document.getElementById("tabOverviewBtn");
  const tabAnalyticsBtn = document.getElementById("tabAnalyticsBtn");
  const viewOverview = document.getElementById("viewOverview");
  const viewAnalytics = document.getElementById("viewAnalytics");

  if (tabOverviewBtn && tabAnalyticsBtn) {
    tabOverviewBtn.addEventListener("click", () => {
      tabOverviewBtn.classList.add("active");
      tabAnalyticsBtn.classList.remove("active");
      viewOverview.style.display = "block";
      viewAnalytics.style.display = "none";
      currentTab = "overview";
    });

    tabAnalyticsBtn.addEventListener("click", () => {
      tabAnalyticsBtn.classList.add("active");
      tabOverviewBtn.classList.remove("active");
      viewOverview.style.display = "none";
      viewAnalytics.style.display = "block";
      currentTab = "analytics";
    });
  }

  // Toggle Matrix View Button
  const toggleBtn = document.getElementById("toggleBucketViewBtn");
  const emptyBox = document.getElementById("bucketEmptyBox");
  const matrixBox = document.getElementById("bucketMatrixBox");

  if (toggleBtn && emptyBox && matrixBox) {
    toggleBtn.addEventListener("click", () => {
      isMatrixVisible = !isMatrixVisible;
      if (isMatrixVisible) {
        emptyBox.style.display = "none";
        matrixBox.style.display = "block";
        toggleBtn.textContent = "✖️ Hide Matrix";
      } else {
        emptyBox.style.display = "flex";
        matrixBox.style.display = "none";
        toggleBtn.textContent = "📊 View Matrix";
      }
    });
  }
}

// Initial Boot
document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  loadDatabaseProfiles();
  loadDashboardMetrics();
});
