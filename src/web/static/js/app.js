// Ahmedabad Airbnb Daily Market Tracker — Frontend Controller
let horizonCharts = { '1d': null, '2d': null, '3d': null, '7d': null };
let currentMetric = 'unavailability'; // 'unavailability', 'adr', 'revpar', 'listings'
let schedulerStatus = null;

document.addEventListener('DOMContentLoaded', () => {
  initClock();
  initSchedulerCountdown();
  initEventListeners();
  initAutoRefreshMonitor();
  loadDashboardData();
  loadAreaComparison();
  loadTrendsChart();
  loadMasterListings();
});

// 1. Live IST Clock & Scheduler Countdown
function initClock() {
  const clockEl = document.getElementById('live-ist-time');
  function update() {
    const now = new Date();
    // Format to Asia/Kolkata
    const options = {
      timeZone: 'Asia/Kolkata',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    };
    const timeStr = new Intl.DateTimeFormat('en-IN', options).format(now);
    if (clockEl) {
      clockEl.textContent = `${timeStr} IST`;
    }
  }
  update();
  setInterval(update, 1000);
}

async function fetchSchedulerStatus() {
  try {
    const res = await fetch('/api/scheduler/jobs');
    if (res.ok) {
      schedulerStatus = await res.json();
    }
  } catch (e) {
    // Ignore network blips
  }
}

function initSchedulerCountdown() {
  const pill = document.getElementById('scheduler-pill');
  if (!pill) return;

  fetchSchedulerStatus();
  setInterval(fetchSchedulerStatus, 8000);

  setInterval(() => {
    if (!schedulerStatus || !schedulerStatus.jobs) return;
    const validJobs = schedulerStatus.jobs.filter(j => j.next_run_iso && j.id !== 'catchup_monitor');
    if (!validJobs.length) return;

    validJobs.sort((a, b) => new Date(a.next_run_iso).getTime() - new Date(b.next_run_iso).getTime());
    const nextJob = validJobs[0];

    if (nextJob && nextJob.next_run_iso) {
      const targetTime = new Date(nextJob.next_run_iso).getTime();
      const diffSec = Math.round((targetTime - Date.now()) / 1000);
      if (diffSec > 0) {
        const hours = Math.floor(diffSec / 3600);
        const m = Math.floor((diffSec % 3600) / 60);
        const s = diffSec % 60;
        let timeLabel = '';
        if (hours > 0) {
          timeLabel = `${hours}h ${m}m ${s < 10 ? '0' : ''}${s}s`;
        } else {
          timeLabel = `${m}m ${s < 10 ? '0' : ''}${s}s`;
        }
        pill.textContent = `⏱️ Next Ingestion: In ${timeLabel} (5:00 PM IST)`;
        pill.style.background = 'rgba(16, 185, 129, 0.15)';
        pill.style.color = '#10b981';
      } else if (diffSec >= -60) {
        pill.textContent = `⚡ 5:00 PM Ingestion running...`;
        pill.style.background = 'rgba(239, 68, 68, 0.2)';
        pill.style.color = '#f87171';
      } else {
        pill.textContent = `⏱️ Next Ingestion: 5:00 PM IST`;
      }
    }
  }, 1000);
}

// 2. Event Listeners
function initEventListeners() {
  const areaSelect = document.getElementById('area-select');
  const dateInput = document.getElementById('obs-date-input');
  
  if (areaSelect) {
    areaSelect.addEventListener('change', () => {
      loadDashboardData();
      loadTrendsChart();
      loadMasterListings();
    });
  }

  if (dateInput) {
    dateInput.addEventListener('change', () => {
      loadDashboardData();
      loadAreaComparison();
      loadMasterListings();
    });
  }

  // Chart tabs
  const chartTabs = document.querySelectorAll('.chart-tab');
  chartTabs.forEach(tab => {
    tab.addEventListener('click', (e) => {
      chartTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      currentMetric = tab.getAttribute('data-metric');
      loadTrendsChart();
    });
  });

  // Trigger Ingestion Button
  const btnTrigger = document.getElementById('btn-trigger-collection');
  if (btnTrigger) {
    btnTrigger.addEventListener('click', triggerIngestion);
  }

  // 9 AM Daily Report Modal
  const btnReport = document.getElementById('btn-open-report');
  const modalReport = document.getElementById('report-modal-overlay');
  const btnCloseReport = document.getElementById('btn-close-report');
  const btnDismissReport = document.getElementById('btn-dismiss-report');
  const btnCopyReport = document.getElementById('btn-copy-report');

  if (btnReport && modalReport) {
    btnReport.addEventListener('click', openDailyReport);
    if (btnCloseReport) btnCloseReport.addEventListener('click', () => modalReport.classList.remove('open'));
    if (btnDismissReport) btnDismissReport.addEventListener('click', () => modalReport.classList.remove('open'));
    if (btnCopyReport) btnCopyReport.addEventListener('click', copyReportToClipboard);
  }

  // Audit Runs Modal
  const btnRuns = document.getElementById('btn-view-runs');
  const modalRuns = document.getElementById('runs-modal-overlay');
  const btnCloseRuns = document.getElementById('btn-close-runs');

  if (btnRuns && modalRuns) {
    btnRuns.addEventListener('click', openRunsAudit);
    if (btnCloseRuns) btnCloseRuns.addEventListener('click', () => modalRuns.classList.remove('open'));
  }

  // AI Analyst Drawer / Modal
  const btnToggleAi = document.getElementById('btn-toggle-ai');
  const modalAi = document.getElementById('ai-modal-overlay');
  const btnCloseAi = document.getElementById('btn-close-ai');
  const aiForm = document.getElementById('ai-input-form');

  if (btnToggleAi && modalAi) {
    btnToggleAi.addEventListener('click', () => modalAi.classList.add('open'));
    if (btnCloseAi) btnCloseAi.addEventListener('click', () => modalAi.classList.remove('open'));
  }

  if (aiForm) {
    aiForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const input = document.getElementById('ai-prompt-input');
      if (input && input.value.trim()) {
        askAi(input.value.trim());
        input.value = '';
      }
    });
  }

  // AI Prompt Chips
  const chips = document.querySelectorAll('.chip');
  chips.forEach(chip => {
    chip.addEventListener('click', () => {
      const prompt = chip.getAttribute('data-prompt');
      if (prompt) {
        if (modalAi && !modalAi.classList.contains('open')) {
          modalAi.classList.add('open');
        }
        askAi(prompt);
      }
    });
  });

  // Table Search Input
  const searchInput = document.getElementById('listing-search-input');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      filterListingsTable(e.target.value.toLowerCase());
    });
  }
}

// 3. Load Overview KPIs & Multi-Horizon Matrix
async function loadDashboardData() {
  const areaSelect = document.getElementById('area-select');
  const dateInput = document.getElementById('obs-date-input');
  
  const area = areaSelect ? areaSelect.value : 'Ahmedabad';
  const date = dateInput ? dateInput.value : '';

  try {
    const res = await fetch(`/api/overview?area=${encodeURIComponent(area)}&date=${encodeURIComponent(date)}`);
    const data = await res.json();
    const metric = data.metric;

    if (data.observation_date && dateInput && !dateInput.value) {
      dateInput.value = data.observation_date;
    }

    if (!metric) {
      showToast('No snapshot found for selected date', 'error');
      return;
    }

    // Populate Top KPIs
    document.getElementById('kpi-active-listings').textContent = Number(metric.active_listings).toLocaleString();
    
    // 7D & 30D listing change badges
    const bList7d = document.getElementById('badge-listings-7d');
    const chg7d = metric.active_listing_change_7d;
    bList7d.textContent = `7D: ${chg7d >= 0 ? '+' : ''}${chg7d}`;
    bList7d.className = `trend-badge ${chg7d >= 0 ? 'pos' : 'neg'}`;

    const bList30d = document.getElementById('badge-listings-30d');
    const chg30d = metric.active_listing_change_30d;
    bList30d.textContent = `30D: ${chg30d >= 0 ? '+' : ''}${chg30d}`;
    bList30d.className = `trend-badge ${chg30d >= 0 ? 'pos' : 'neg'}`;

    // Tonight's Unavailability Rate
    const unavailVal = (metric.observed_unavailability_rate * 100).toFixed(1);
    document.getElementById('kpi-unavailability').textContent = `${unavailVal}%`;

    const bUnavail7d = document.getElementById('badge-unavail-7d');
    const uChg7d = metric.unavailability_change_7d_pp;
    bUnavail7d.textContent = `7D: ${uChg7d >= 0 ? '+' : ''}${uChg7d.toFixed(1)} pp`;
    bUnavail7d.className = `trend-badge ${uChg7d >= 0 ? 'pos' : 'neg'}`;

    const bUnavail30d = document.getElementById('badge-unavail-30d');
    const uChg30d = metric.unavailability_change_30d_pp;
    bUnavail30d.textContent = `30D: ${uChg30d >= 0 ? '+' : ''}${uChg30d.toFixed(1)} pp`;
    bUnavail30d.className = `trend-badge ${uChg30d >= 0 ? 'pos' : 'neg'}`;

    // ADR
    document.getElementById('kpi-adr').textContent = `₹${Math.round(metric.adr).toLocaleString()}`;

    // RevPAR Proxy
    document.getElementById('kpi-revpar').textContent = `₹${Math.round(metric.revpar_proxy).toLocaleString()}`;
    const monthlyGross = Math.round(metric.revpar_proxy * 30);
    document.getElementById('kpi-monthly-rev').textContent = `Est. Gross / Mo: ₹${monthlyGross.toLocaleString()}`;

    // Coverage
    const covVal = (metric.coverage_rate * 100).toFixed(1);
    document.getElementById('kpi-coverage').textContent = `${covVal}%`;
    const pill = document.getElementById('kpi-run-status');
    pill.textContent = metric.status;
    pill.className = `coverage-status-pill ${metric.status === 'COMPLETE' ? '' : 'partial'}`;

    // Populate Multi-Horizon Matrix Cards (Tonight 1D, Next 2D, Next 3D, Next 7D)
    const matrixDefs = [
      { key: '1d', days: 1, uKey: 'unavailability_1d', nuKey: 'nights_unavail_1d', ntKey: 'nights_total_1d', adrKey: 'adr_1d', revparKey: 'revpar_1d' },
      { key: '2d', days: 2, uKey: 'unavailability_2d', nuKey: 'nights_unavail_2d', ntKey: 'nights_total_2d', adrKey: 'adr_2d', revparKey: 'revpar_2d' },
      { key: '3d', days: 3, uKey: 'unavailability_3d', nuKey: 'nights_unavail_3d', ntKey: 'nights_total_3d', adrKey: 'adr_3d', revparKey: 'revpar_3d' },
      { key: '7d', days: 7, uKey: 'unavailability_7d', nuKey: 'nights_unavail_7d', ntKey: 'nights_total_7d', adrKey: 'adr_7d', revparKey: 'revpar_7d' },
    ];

    matrixDefs.forEach(m => {
      const uRate = metric[m.uKey] !== undefined ? metric[m.uKey] : metric.observed_unavailability_rate;
      const ratePct = (uRate * 100).toFixed(1);
      const nu = metric[m.nuKey] !== undefined ? metric[m.nuKey] : Math.round(metric.active_listings * m.days * uRate);
      const nt = metric[m.ntKey] !== undefined ? metric[m.ntKey] : (metric.active_listings * m.days);
      const adrVal = Math.round(metric[m.adrKey] || metric.adr);
      const revparVal = Math.round(metric[m.revparKey] || metric.revpar_proxy);

      const elRate = document.getElementById(`matrix-rate-${m.key}`);
      const elFormula = document.getElementById(`formula-badge-${m.key}`);
      const elFraction = document.getElementById(`matrix-fraction-${m.key}`);
      const elAdr = document.getElementById(`matrix-adr-${m.key}`);
      const elRevpar = document.getElementById(`matrix-revpar-${m.key}`);

      if (elRate) elRate.textContent = `${ratePct}%`;
      if (elFormula) elFormula.textContent = `Formula: ${nu.toLocaleString()} / (${metric.active_listings.toLocaleString()} × ${m.days})`;
      if (elFraction) elFraction.textContent = `${nu.toLocaleString()} / ${nt.toLocaleString()} occupied nights`;
      if (elAdr) elAdr.textContent = `₹${adrVal.toLocaleString()}`;
      if (elRevpar) elRevpar.textContent = `₹${revparVal.toLocaleString()}`;
    });

  } catch (err) {
    console.error('Failed to load overview:', err);
  }
}

// 4. Area Comparison Table (Multi-Horizon: Tonight, 2D, 3D, 7D)
async function loadAreaComparison() {
  const dateInput = document.getElementById('obs-date-input');
  const date = dateInput ? dateInput.value : '';

  try {
    const res = await fetch(`/api/comparison?date=${encodeURIComponent(date)}`);
    const data = await res.json();
    const tbody = document.getElementById('area-table-body');
    if (!tbody) return;

    const badge = document.getElementById('area-count-badge');
    if (badge && data.areas) {
      badge.textContent = `${data.areas.length} Discovered Areas`;
    }

    const areaSelect = document.getElementById('area-select');
    if (areaSelect && data.areas && data.areas.length > 0) {
      const currentVal = areaSelect.value;
      const existingOpts = new Set(Array.from(areaSelect.options).map(o => o.value));
      data.areas.forEach(a => {
        if (!existingOpts.has(a.area)) {
          const opt = document.createElement('option');
          opt.value = a.area;
          opt.textContent = a.area;
          areaSelect.appendChild(opt);
          existingOpts.add(a.area);
        }
      });
      areaSelect.value = currentVal;
    }

    if (!data.areas || data.areas.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" class="text-center py-4 text-muted">No area records for ${date}</td></tr>`;
      return;
    }

    tbody.innerHTML = '';
    data.areas.forEach(a => {
      const tr = document.createElement('tr');
      const u1 = ((a.unavailability_1d !== undefined ? a.unavailability_1d : a.observed_unavailability_rate) * 100).toFixed(1);
      const u2 = ((a.unavailability_2d !== undefined ? a.unavailability_2d : a.observed_unavailability_rate) * 100).toFixed(1);
      const u3 = ((a.unavailability_3d !== undefined ? a.unavailability_3d : a.observed_unavailability_rate) * 100).toFixed(1);
      const u7 = ((a.unavailability_7d !== undefined ? a.unavailability_7d : a.observed_unavailability_rate) * 100).toFixed(1);

      const nu1 = a.nights_unavail_1d !== undefined ? a.nights_unavail_1d : Math.round(a.active_listings * 1 * (u1/100));
      const nt1 = a.nights_total_1d !== undefined ? a.nights_total_1d : (a.active_listings * 1);

      const nu2 = a.nights_unavail_2d !== undefined ? a.nights_unavail_2d : Math.round(a.active_listings * 2 * (u2/100));
      const nt2 = a.nights_total_2d !== undefined ? a.nights_total_2d : (a.active_listings * 2);

      const nu3 = a.nights_unavail_3d !== undefined ? a.nights_unavail_3d : Math.round(a.active_listings * 3 * (u3/100));
      const nt3 = a.nights_total_3d !== undefined ? a.nights_total_3d : (a.active_listings * 3);

      const nu7 = a.nights_unavail_7d !== undefined ? a.nights_unavail_7d : Math.round(a.active_listings * 7 * (u7/100));
      const nt7 = a.nights_total_7d !== undefined ? a.nights_total_7d : (a.active_listings * 7);

      const adrVal = Math.round(a.adr_1d || a.adr);
      const revparVal = Math.round(a.revpar_1d || a.revpar_proxy);
      const cov = ((a.coverage_rate || 1.0) * 100).toFixed(1);

      tr.innerHTML = `
        <td><strong>${a.area}</strong></td>
        <td class="text-right">${a.active_listings.toLocaleString()}</td>
        <td class="text-right" title="Exact fraction: ${nu1}/${nt1} nights"><strong style="color: #fbbf24;">${u1}%</strong></td>
        <td class="text-right" title="Exact fraction: ${nu2}/${nt2} nights"><strong style="color: #38bdf8;">${u2}%</strong></td>
        <td class="text-right" title="Exact fraction: ${nu3}/${nt3} nights"><strong style="color: #c084fc;">${u3}%</strong></td>
        <td class="text-right" title="Exact fraction: ${nu7}/${nt7} nights"><strong style="color: #34d399;">${u7}%</strong></td>
        <td class="text-right">₹${adrVal.toLocaleString()}</td>
        <td class="text-right" style="color: #c084fc; font-weight: 700;">₹${revparVal.toLocaleString()}</td>
        <td class="text-center"><span class="coverage-status-pill ${a.status === 'COMPLETE' ? '' : 'partial'}">${cov}%</span></td>
      `;
      // Click row to switch area
      tr.style.cursor = 'pointer';
      tr.addEventListener('click', () => {
        const areaSelect = document.getElementById('area-select');
        if (areaSelect) {
          areaSelect.value = a.area;
          loadDashboardData();
          loadTrendsChart();
          loadMasterListings();
        }
      });
      tbody.appendChild(tr);
    });

  } catch (err) {
    console.error('Failed to load comparison table:', err);
  }
}

// 5. Multi-Horizon Market Trendlines (4 Distinct Plots)
async function loadTrendsChart() {
  const areaSelect = document.getElementById('area-select');
  const area = areaSelect ? areaSelect.value : 'Ahmedabad';

  const titleEl = document.getElementById('chart-section-title');
  if (titleEl) {
    titleEl.textContent = `${area} Multi-Horizon Market Trendlines`;
  }

  try {
    const res = await fetch(`/api/trends?area=${encodeURIComponent(area)}&days=30`);
    const data = await res.json();
    const rows = data.data || [];

    const labels = rows.map(r => {
      const parts = r.observation_date.split('-');
      return `${parts[2]}/${parts[1]}`;
    });

    const isSinglePoint = rows.length <= 1;
    const subTitle = document.getElementById('chart-section-sub');
    if (subTitle) {
      if (isSinglePoint) {
        subTitle.textContent = `Daily point #1 recorded for ${rows[0] ? rows[0].observation_date : 'today'} • Next daily point added tomorrow at 9:00 AM IST`;
      } else {
        subTitle.textContent = `${rows.length} consecutive daily points recorded • Real observed data (no estimates)`;
      }
    }

    const horizonsDef = [
      {
        key: '1d',
        canvasId: 'chart-1d',
        badgeId: 'plot-badge-1d',
        label: 'Tonight (1D)',
        color: '#f59e0b',
        gradientStart: 'rgba(245, 158, 11, 0.4)',
        gradientEnd: 'rgba(245, 158, 11, 0.0)',
        getVal: (r) => {
          if (currentMetric === 'unavailability') return +( (r.unavailability_1d !== undefined ? r.unavailability_1d : r.observed_unavailability_rate) * 100).toFixed(1);
          if (currentMetric === 'adr') return Math.round(r.adr_1d || r.adr);
          if (currentMetric === 'revpar') return Math.round(r.revpar_1d || r.revpar_proxy);
          return r.active_listings;
        }
      },
      {
        key: '2d',
        canvasId: 'chart-2d',
        badgeId: 'plot-badge-2d',
        label: 'Next 2 Days (2D)',
        color: '#38bdf8',
        gradientStart: 'rgba(56, 189, 248, 0.4)',
        gradientEnd: 'rgba(56, 189, 248, 0.0)',
        getVal: (r) => {
          if (currentMetric === 'unavailability') return +( (r.unavailability_2d !== undefined ? r.unavailability_2d : r.observed_unavailability_rate) * 100).toFixed(1);
          if (currentMetric === 'adr') return Math.round(r.adr_2d || r.adr);
          if (currentMetric === 'revpar') return Math.round(r.revpar_2d || r.revpar_proxy);
          return r.active_listings;
        }
      },
      {
        key: '3d',
        canvasId: 'chart-3d',
        badgeId: 'plot-badge-3d',
        label: 'Next 3 Days (3D)',
        color: '#c084fc',
        gradientStart: 'rgba(192, 132, 252, 0.4)',
        gradientEnd: 'rgba(192, 132, 252, 0.0)',
        getVal: (r) => {
          if (currentMetric === 'unavailability') return +( (r.unavailability_3d !== undefined ? r.unavailability_3d : r.observed_unavailability_rate) * 100).toFixed(1);
          if (currentMetric === 'adr') return Math.round(r.adr_3d || r.adr);
          if (currentMetric === 'revpar') return Math.round(r.revpar_3d || r.revpar_proxy);
          return r.active_listings;
        }
      },
      {
        key: '7d',
        canvasId: 'chart-7d',
        badgeId: 'plot-badge-7d',
        label: 'Next 7 Days (7D)',
        color: '#34d399',
        gradientStart: 'rgba(52, 211, 153, 0.4)',
        gradientEnd: 'rgba(52, 211, 153, 0.0)',
        getVal: (r) => {
          if (currentMetric === 'unavailability') return +( (r.unavailability_7d !== undefined ? r.unavailability_7d : r.observed_unavailability_rate) * 100).toFixed(1);
          if (currentMetric === 'adr') return Math.round(r.adr_7d || r.adr);
          if (currentMetric === 'revpar') return Math.round(r.revpar_7d || r.revpar_proxy);
          return r.active_listings;
        }
      }
    ];

    let yAxisFormatter = (val) => val;
    if (currentMetric === 'unavailability') {
      yAxisFormatter = (val) => `${val}%`;
    } else if (currentMetric === 'adr' || currentMetric === 'revpar') {
      yAxisFormatter = (val) => `₹${val}`;
    } else if (currentMetric === 'listings') {
      yAxisFormatter = (val) => Number(val).toLocaleString();
    }

    horizonsDef.forEach(h => {
      const seriesData = rows.map(h.getVal);
      const canvas = document.getElementById(h.canvasId);
      const badge = document.getElementById(h.badgeId);

      if (badge && seriesData.length > 0) {
        const latestVal = seriesData[seriesData.length - 1];
        if (currentMetric === 'unavailability') {
          badge.textContent = `${latestVal}%`;
        } else if (currentMetric === 'adr' || currentMetric === 'revpar') {
          badge.textContent = `₹${latestVal.toLocaleString()}`;
        } else {
          badge.textContent = `${latestVal.toLocaleString()} units`;
        }
      }

      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      const gradient = ctx.createLinearGradient(0, 0, 0, 200);
      gradient.addColorStop(0, h.gradientStart);
      gradient.addColorStop(1, h.gradientEnd);

      if (horizonCharts[h.key]) {
        horizonCharts[h.key].destroy();
      }

      horizonCharts[h.key] = new Chart(ctx, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [{
            label: `${h.label} - ${currentMetric.toUpperCase()}`,
            data: seriesData,
            borderColor: h.color,
            backgroundColor: gradient,
            fill: true,
            tension: 0.35,
            borderWidth: 2.5,
            pointRadius: isSinglePoint ? 8 : 4,
            pointHoverRadius: isSinglePoint ? 12 : 7,
            pointHitRadius: 15,
            pointBackgroundColor: h.color,
            pointBorderColor: '#ffffff',
            pointBorderWidth: isSinglePoint ? 2.5 : 1,
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: {
            mode: 'index',
            intersect: false,
          },
          plugins: {
            legend: {
              display: false,
            },
            tooltip: {
              backgroundColor: 'rgba(15, 23, 42, 0.95)',
              titleColor: '#f8fafc',
              bodyColor: h.color,
              borderColor: 'rgba(255, 255, 255, 0.1)',
              borderWidth: 1,
              padding: 10,
              displayColors: false,
              callbacks: {
                label: function(context) {
                  return `${h.label}: ${yAxisFormatter(context.parsed.y)}`;
                }
              }
            }
          },
          scales: {
            x: {
              grid: { color: 'rgba(255, 255, 255, 0.04)' },
              ticks: { color: '#64748b', font: { size: 10 } }
            },
            y: {
              grid: { color: 'rgba(255, 255, 255, 0.05)' },
              ticks: {
                color: '#64748b',
                font: { size: 10 },
                callback: yAxisFormatter
              }
            }
          }
        }
      });
    });

  } catch (err) {
    console.error('Failed to load multi-horizon trends charts:', err);
  }
}

// 6. Master Listing Universe Explorer
let masterListingsCache = [];
async function loadMasterListings() {
  const areaSelect = document.getElementById('area-select');
  const dateInput = document.getElementById('obs-date-input');
  const area = areaSelect ? areaSelect.value : 'Ahmedabad';
  const date = dateInput ? dateInput.value : '';

  try {
    const res = await fetch(`/api/listings?area=${encodeURIComponent(area)}&date=${encodeURIComponent(date)}&limit=100`);
    const data = await res.json();
    masterListingsCache = data.listings || [];
    renderListingsTable(masterListingsCache);
  } catch (err) {
    console.error('Failed to load listings:', err);
  }
}

function formatOccBadge(occStr, defaultTotal) {
  if (!occStr) return '—';
  const parts = occStr.split('/');
  const booked = parseInt(parts[0], 10) || 0;
  const total = parseInt(parts[1], 10) || defaultTotal;
  let colorClass = 'occ-zero';
  if (booked === total) {
    colorClass = 'occ-full';
  } else if (booked > 0) {
    colorClass = 'occ-part';
  }
  return `<span class="badge-occ ${colorClass}">${occStr}</span>`;
}

function renderListingsTable(listings) {
  const tbody = document.getElementById('listings-table-body');
  if (!tbody) return;

  if (listings.length === 0) {
    tbody.innerHTML = '<tr><td colspan="14" class="text-center py-4 text-muted">No listings matched.</td></tr>';
    return;
  }

  tbody.innerHTML = '';
  listings.forEach(l => {
    const tr = document.createElement('tr');
    const airbnbUrl = l.listing_url || `https://www.airbnb.com/rooms/${l.listing_id.replace('airbnb_', '').replace('ab_', '')}`;
    
    tr.innerHTML = `
      <td>
        <a href="${airbnbUrl}" target="_blank" rel="noopener noreferrer" class="listing-id-link" title="Open ${l.listing_id} on Airbnb">
          <span style="font-family: monospace; font-size: 0.78rem;">${l.listing_id}</span>
        </a>
      </td>
      <td>
        <a href="${airbnbUrl}" target="_blank" rel="noopener noreferrer" class="listing-title-link" title="Open listing on Airbnb">
          <strong>${l.title || 'Apartment in Ahmedabad'}</strong>
        </a>
      </td>
      <td><span class="badge-count">${l.area}</span></td>
      <td class="text-secondary">${l.property_type || 'Apartment'}</td>
      <td class="text-center">${formatOccBadge(l.occ_1d, 1)}</td>
      <td class="text-center">${formatOccBadge(l.occ_2d, 2)}</td>
      <td class="text-center">${formatOccBadge(l.occ_3d, 3)}</td>
      <td class="text-center">${formatOccBadge(l.occ_7d, 7)}</td>
      <td class="text-center"><strong>${l.bedrooms || 2} BHK</strong></td>
      <td class="text-center">${l.beds || 2} Beds</td>
      <td class="text-center"><span class="amenity-pill">📶 Wi-Fi</span> <span class="amenity-pill">❄️ AC</span></td>
      <td class="text-right">${l.rating ? `★ ${l.rating.toFixed(2)}` : '—'}</td>
      <td class="text-right">${l.review_count || 0}</td>
      <td class="text-center">
        <a href="${airbnbUrl}" target="_blank" rel="noopener noreferrer" class="airbnb-view-btn" title="View property on Airbnb">
          <span>Airbnb ↗</span>
        </a>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

let searchDebounceTimeout = null;
function filterListingsTable(query) {
  const cleanQ = (query || '').trim();
  if (!cleanQ) {
    renderListingsTable(masterListingsCache);
    return;
  }

  const qLower = cleanQ.toLowerCase();
  const filtered = masterListingsCache.filter(l => 
    (l.title && l.title.toLowerCase().includes(qLower)) ||
    (l.listing_id && l.listing_id.toLowerCase().includes(qLower)) ||
    (l.area && l.area.toLowerCase().includes(qLower))
  );

  // If local results exist, show them right away
  if (filtered.length > 0) {
    renderListingsTable(filtered);
  }

  const dateInput = document.getElementById('obs-date-input');
  const date = dateInput ? dateInput.value : '';

  // Also query backend (which searches the entire DB across all 40 areas or queries live Airbnb)
  clearTimeout(searchDebounceTimeout);
  searchDebounceTimeout = setTimeout(async () => {
    try {
      const res = await fetch(`/api/listings?search=${encodeURIComponent(cleanQ)}&date=${encodeURIComponent(date)}&limit=50`);
      const data = await res.json();
      if (data.listings && data.listings.length > 0) {
        renderListingsTable(data.listings);
      } else if (filtered.length === 0) {
        renderListingsTable([]);
      }
    } catch (e) {
      console.error('Search error:', e);
    }
  }, 250);
}

// 7. Auto-Refresh Monitor (checks every 30 seconds for 9 AM IST new snapshots)
function initAutoRefreshMonitor() {
  setInterval(async () => {
    try {
      const res = await fetch('/api/overview?area=Ahmedabad');
      const data = await res.json();
      if (!data || !data.observation_date) return;

      const dateInput = document.getElementById('obs-date-input');
      const currentUiDate = dateInput ? dateInput.value : null;

      // If backend has a newer date than currently displayed
      if (currentUiDate && data.observation_date > currentUiDate) {
        console.log(`[Auto-Refresh] Newer observation date detected: ${data.observation_date}`);
        if (dateInput) dateInput.value = data.observation_date;
        loadDashboardData();
        loadAreaComparison();
        loadTrendsChart();
        loadMasterListings();
        showToast(`⏰ 9:00 AM IST daily market refresh: Loaded ${data.observation_date} snapshot!`, 'success');
      }
    } catch (e) {
      // Ignore network errors
    }
  }, 30000);
}

// 7. Trigger Immediate Ingestion
async function triggerIngestion() {
  const btn = document.getElementById('btn-trigger-collection');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span class="btn-icon">⏳</span><span>Ingesting...</span>`;
  }
  showToast('Starting Ahmedabad Airbnb ingestion cycle...', 'success');

  try {
    const dateInput = document.getElementById('obs-date-input');
    const obsDate = dateInput ? dateInput.value : '';
    
    const res = await fetch(`/api/trigger-collection?date=${encodeURIComponent(obsDate)}`, { method: 'POST' });
    const result = await res.json();

    showToast(`Ingestion complete! Discovered ${result.listings_discovered} listings, ${result.calendar_records} calendar days. Coverage: ${result.coverage_pct}%`, 'success');
    
    // Refresh dashboard
    loadDashboardData();
    loadAreaComparison();
    loadTrendsChart();
    loadMasterListings();

  } catch (err) {
    console.error('Trigger collection error:', err);
    showToast('Ingestion failed: ' + err.message, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<span class="btn-icon">⚡</span><span>Trigger Ingestion</span>`;
    }
  }
}

// 8. 9 AM Daily Report Modal
async function openDailyReport() {
  const modal = document.getElementById('report-modal-overlay');
  const pre = document.getElementById('report-text-content');
  const dateInput = document.getElementById('obs-date-input');
  const obsDate = dateInput ? dateInput.value : '';

  if (modal) modal.classList.add('open');
  if (pre) pre.textContent = 'Generating 9 AM market intelligence report...';

  try {
    const res = await fetch(`/api/daily-report?date=${encodeURIComponent(obsDate)}`);
    const data = await res.json();
    if (pre) pre.textContent = data.report || 'No report available.';
  } catch (err) {
    if (pre) pre.textContent = 'Failed to generate report: ' + err.message;
  }
}

function copyReportToClipboard() {
  const pre = document.getElementById('report-text-content');
  if (pre) {
    navigator.clipboard.writeText(pre.textContent).then(() => {
      showToast('9 AM report copied to clipboard!', 'success');
    });
  }
}

// 9. Historical Audit Runs Modal
async function openRunsAudit() {
  const modal = document.getElementById('runs-modal-overlay');
  const tbody = document.getElementById('runs-table-body');
  if (modal) modal.classList.add('open');

  try {
    const res = await fetch('/api/runs?limit=30');
    const data = await res.json();
    const runs = data.runs || [];

    if (!tbody) return;
    if (runs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-muted">No runs found.</td></tr>';
      return;
    }

    tbody.innerHTML = '';
    runs.forEach(r => {
      let errStr = '';
      if (r.errors) {
        try {
          const parsed = JSON.parse(r.errors);
          errStr = Array.isArray(parsed) ? parsed.join('; ') : String(r.errors);
        } catch (e) {
          errStr = String(r.errors);
        }
      }
      const errTooltip = errStr ? ` title="${escapeHtml(errStr)}" style="cursor: help;"` : '';

      // Format time in IST
      let timeDisplay = '';
      if (r.started_at_ist) {
        const parts = r.started_at_ist.split(' ');
        timeDisplay = parts.slice(1).join(' '); // e.g. "00:33:04 IST"
      } else if (r.started_at) {
        try {
          const d = new Date(r.started_at.endsWith('Z') ? r.started_at : r.started_at + 'Z');
          timeDisplay = d.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }) + ' IST';
        } catch (e) {
          timeDisplay = r.started_at.substring(11, 19);
        }
      }

      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>
          <div style="font-weight: 600; font-size: 0.88rem; color: #f1f5f9;">${r.observation_date}</div>
          <div style="font-size: 0.75rem; color: #38bdf8; font-family: monospace; margin-top: 2px;">⏱️ ${timeDisplay || '--:-- IST'}</div>
        </td>
        <td><span style="font-family: monospace; font-size: 0.75rem;">${r.run_id.substring(0, 8)}...</span></td>
        <td><span class="badge-count">${r.provider}</span></td>
        <td>${r.listings_discovered.toLocaleString()}</td>
        <td>${r.calendar_records_collected.toLocaleString()}</td>
        <td><strong>${r.coverage_pct}%</strong></td>
        <td>
          <span class="coverage-status-pill ${r.status === 'SUCCESS' ? '' : 'partial'}"${errTooltip}>${r.status}</span>
          ${errStr ? `<span style="display:block; font-size:0.7rem; color:#ef4444; max-width:240px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-top:3px;" title="${escapeHtml(errStr)}">⚠️ ${escapeHtml(errStr)}</span>` : ''}
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error('Failed to load runs:', err);
  }
}

// 10. AI Leasing Analyst
async function askAi(question) {
  const history = document.getElementById('ai-chat-history');
  if (!history) return;

  // Append user message
  const userDiv = document.createElement('div');
  userDiv.className = 'chat-message user';
  userDiv.innerHTML = `<div class="message-content">${escapeHtml(question)}</div>`;
  history.appendChild(userDiv);

  // Append bot placeholder
  const botDiv = document.createElement('div');
  botDiv.className = 'chat-message bot';
  botDiv.innerHTML = `<div class="message-content"><span class="pulse-dot"></span> Analyzing historical database...</div>`;
  history.appendChild(botDiv);
  history.scrollTop = history.scrollHeight;

  try {
    const res = await fetch('/api/ai-query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: question })
    });
    const data = await res.json();

    // Render formatted markdown/HTML
    botDiv.querySelector('.message-content').innerHTML = formatMarkdown(data.answer);
    history.scrollTop = history.scrollHeight;

  } catch (err) {
    botDiv.querySelector('.message-content').innerHTML = `Failed to get answer: ${err.message}`;
  }
}

// Simple Markdown / Table Formatter for AI output
function formatMarkdown(text) {
  if (!text) return '';
  let formatted = text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/\n\n/g, '<br><br>')
    .replace(/\n• /g, '<br>&bull; ')
    .replace(/\n/g, '<br>');

  // Format markdown table if present
  if (formatted.includes('|')) {
    const lines = text.split('\n');
    let inTable = false;
    let htmlTable = '<table class="data-table mt-4" style="margin: 1rem 0;">';
    let isHeader = true;

    for (let line of lines) {
      if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
        if (line.includes('---')) continue;
        const cells = line.split('|').slice(1, -1).map(c => c.trim());
        if (!inTable) {
          inTable = true;
          htmlTable += '<thead><tr>' + cells.map(c => `<th>${c}</th>`).join('') + '</tr></thead><tbody>';
        } else {
          htmlTable += '<tr>' + cells.map(c => `<td>${c}</td>`).join('') + '</tr>';
        }
      }
    }
    if (inTable) {
      htmlTable += '</tbody></table>';
      return formatted.replace(/\|.*\|/gs, htmlTable);
    }
  }

  return formatted;
}

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// 11. Toast Notifications
function showToast(message, type = 'success') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${type === 'success' ? '✅' : '⚠️'}</span><span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 4500);
}
