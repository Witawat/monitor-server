// dashboard.js — fleet cards + host KPI + Chart.js (WEBUI_DESIGN.md §5-7)
(function () {
  const { api, toast } = window.Monitor;
  let currentRange = '1h';
  let currentMetric = 'cpu_percent';
  let chart = null;

  // metric ที่ plot ได้ (ตรงกับ METRIC_COLUMNS มิติที่ไม่มี disk/net time-series)
  const METRICS = [
    { key: 'cpu_percent', label: 'CPU %', unit: 'percent' },
    { key: 'memory.percent', label: 'RAM %', unit: 'percent' },
    { key: 'memory.used', label: 'RAM used', unit: 'bytes' },
    { key: 'memory.total', label: 'RAM total', unit: 'bytes' },
    { key: 'load1', label: 'Load 1m', unit: 'num' },
    { key: 'load5', label: 'Load 5m', unit: 'num' },
    { key: 'load15', label: 'Load 15m', unit: 'num' },
    { key: 'swap.used', label: 'Swap used', unit: 'bytes' },
    { key: 'swap.total', label: 'Swap total', unit: 'bytes' },
    { key: 'procs', label: 'Processes', unit: 'num' },
    { key: 'uptime', label: 'Uptime', unit: 'sec' },
  ];

  function unitOf(key) {
    const m = METRICS.find((x) => x.key === key);
    return m ? m.unit : 'num';
  }

  function fillColor(p) {
    if (p >= 90) return 'var(--danger)';
    if (p >= 80) return 'var(--warn)';
    return 'var(--accent)';
  }

  // icon OS (SVG กัน emoji render ต่างกัน) — linux/windows/mac หลัก ๆ
  function osIcon(platform) {
    const p = (platform || '').toLowerCase();
    if (p.includes('win')) {
      return '<span class="os-icon" title="Windows"><svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><rect x="1" y="1" width="6.5" height="6.5" fill="#5cb0f7"/><rect x="8.5" y="1" width="6.5" height="6.5" fill="#5cb0f7"/><rect x="1" y="8.5" width="6.5" height="6.5" fill="#5cb0f7"/><rect x="8.5" y="8.5" width="6.5" height="6.5" fill="#5cb0f7"/></svg></span>';
    }
    if (p.includes('mac') || p.includes('darwin')) {
      return '<span class="os-icon" title="macOS"><svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><circle cx="8" cy="8" r="6.5" fill="#8e8e93"/><path d="M8 2.5v11M2.5 8h11" stroke="#fff" stroke-width="1"/></svg></span>';
    }
    // default linux / อื่น
    return '<span class="os-icon" title="Linux"><svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M5.5 2.5c-.6 1.5.2 2.6-1 4.5S3 12 5 13.5c1.4 1 3.6.7 4.6-.6 1-1.4.3-3 .3-3.3 0-.4-.5-1.2.1-2.2S11 4 10.2 2.7C9.3 1.4 7.6 1.6 6.9 2c-.6.3-.9.5-1.4.5z" fill="#22a06b"/><circle cx="7.8" cy="4" r="1.1" fill="#fff" opacity=".7"/><path d="M6.8 9.5c.6.5 1.5.5 2 0" stroke="#fff" stroke-width=".7" fill="none" stroke-linecap="round"/></svg></span>';
  }

  // 统计 Fleet 顶部 — 总数/在线/离线/OS 分布 (看全局一目了然)
  function renderFleetStats(hosts) {
    const wrap = document.getElementById('fleetStats');
    if (!wrap) return;
    const online = hosts.filter((h) => h.online).length;
    const offline = hosts.length - online;
    const countOs = (pred) => hosts.filter(pred).length;
    const linux = countOs((h) => !(h.platform || '').toLowerCase().includes('win'));
    const windows = countOs((h) => (h.platform || '').toLowerCase().includes('win'));
    wrap.innerHTML =
      '<span class="fleet-stat"><b>' + hosts.length + '</b> เครื่อง</span>' +
      '<span class="fleet-stat online"><b>' + online + '</b> ออนไลน์</span>' +
      '<span class="fleet-stat offline"><b>' + offline + '</b> ออฟไลน์</span>' +
      '<span class="fleet-stat"><b>' + linux + '</b> Linux</span>' +
      '<span class="fleet-stat"><b>' + windows + '</b> Windows</span>';
  }

  function renderFleetCards(hosts, search = '', tag = '') {
    const grid = document.getElementById('hostGrid');
    let list = hosts.filter((h) => {
      const text = (h.hostname + ' ' + h.host_id).toLowerCase();
      const okSearch = !search || text.includes(search.toLowerCase());
      const okTag = !tag || (h.tags || []).includes(tag);
      return okSearch && okTag;
    });
    if (!list.length) {
      grid.innerHTML = '<p class="empty-note">' + I18N.noHost + '</p>';
      return;
    }
    grid.innerHTML = list.map((h) => {
      const s = h.summary || {};
      const online = h.online;
      const badge = online
        ? '<span class="badge online">● ออนไลน์</span>'
        : '<span class="badge offline">○ ออฟไลน์</span>';
      const tags = (h.tags || []).map((t) => '<span class="badge online" style="background:var(--accent-soft);color:var(--accent)">#' + escapeHtml(t) + '</span>').join('');
      const net = online
        ? '<div class="netline"><span>↑ ' + formatRate(s.net_tx || 0) + '</span><span>↓ ' + formatRate(s.net_rx || 0) + '</span></div>'
        : '<div class="netline"><span>—</span><span>—</span></div>';
      const row = (label, pct) =>
        '<div class="metric-row"><div class="label"><span>' + label + '</span><span>' + formatPercent(pct) + '</span></div>' +
        '<div class="progress"><span style="width:' + (pct || 0) + '%;background:' + fillColor(pct || 0) + '"></span></div></div>';
      return '<div class="card' + (online ? '' : ' offline') + '" data-host="' + escapeHtml(h.host_id) + '">' +
        '<h3>' + osIcon(h.platform) + '<span class="host-name">' + escapeHtml(h.hostname || h.host_id) + '</span> ' + badge + '</h3>' + tags +
        row('CPU', s.cpu_percent) + row('RAM', s.mem_percent) + row('Disk', s.disk_percent) +
        net +
        '<div class="netline"><span>uptime ' + formatUptime(online ? s.uptime : null) + '</span></div>' +
        '</div>';
    }).join('');
    grid.querySelectorAll('.card').forEach((card) => {
      card.onclick = () => {
        window.Monitor.setHostId(card.dataset.host);   // เลือก host + scroll to host section
        scrollToSection('host');
      };
    });
  }

  function renderKpi(summary) {
    const s = summary || {};
    const cells = [
      ['CPU', formatPercent(s.cpu_percent), ''],
      ['RAM', formatPercent(s.mem_percent), formatBytes(s.mem_total)],
      ['Disk', formatPercent(s.disk_percent), formatBytes(s.disk_total || 0)],
      ['Uptime', formatUptime(s.uptime), ''],
    ];
    document.getElementById('kpiRow').innerHTML = cells.map((c) =>
      '<div class="kpi"><div class="num">' + c[1] + '</div><div class="lbl">' + c[0] + (c[2] ? ' · ' + c[2] : '') + '</div></div>'
    ).join('');
  }

  function renderServices(services) {
    const el = document.getElementById('servicesRow');
    if (!services || !services.length) { el.innerHTML = ''; return; }
    el.innerHTML = services.map((s) =>
      '<span class="badge ' + (s.up ? 'online' : 'offline') + '">' + (s.up ? '●' : '○') + ' ' + escapeHtml(s.name) + (s.up ? ' ทำงาน' : ' หยุด') + '</span>'
    ).join('');
  }

  function formatAxisTime(ms) {
    if (currentRange === '1h' || currentRange === '6h') {
      return new Date(ms).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
    }
    return new Date(ms).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
  }

  // format ค่า metric ตามหน่วย — ใช้ format.js ร่วมกัน (กันตัวเลขเพี้ยนข้ามหน้า)
  function fmtByUnit(v, unit) {
    if (unit === 'percent') return formatPercent(v);
    if (unit === 'bytes') return formatBytes(v);
    if (unit === 'sec') return formatUptime(v);
    return formatInt(v);
  }

  function renderChart(series) {
    if (chart) { chart.destroy(); chart = null; }
    const wrap = document.querySelector('.chart-wrap');
    const s = series[currentMetric];
    const points = s && s.points ? s.points : [];
    if (!points.length) {
      wrap.innerHTML = '<div class="empty-note">' + I18N.noData + '</div>';
      return;
    }
    wrap.innerHTML = '<canvas id="metricChart"></canvas>';
    const ctx = document.getElementById('metricChart');
    const unit = unitOf(currentMetric);
    chart = new Chart(ctx, {
      type: 'line',
      data: {
        datasets: [{
          label: METRICS.find((m) => m.key === currentMetric).label,
          data: points.map((p) => ({ x: p[0] * 1000, y: p[1] })),
          borderColor: 'var(--accent)',
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.3,
          fill: false,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: 'nearest', intersect: false },
        scales: {
          x: {
            type: 'linear',
            ticks: { maxTicksLimit: 8, callback: (v) => formatAxisTime(v) },
          },
          y: {
            beginAtZero: true,
            ticks: {
              callback: (v) => fmtByUnit(v, unit),
            },
            title: { display: true, text: METRICS.find((m) => m.key === currentMetric).label, color: 'var(--text-2)' },
          },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: (items) => formatAxisTime(items[0].parsed.x),
              label: (c) => METRICS.find((m) => m.key === currentMetric).label + ': ' + fmtByUnit(c.raw.y, unit),
            },
          },
        },
      },
    });
  }

  // เติมตัวเลือก host ใน host dashboard (จาก fleet data ที่ app.js มี)
  function fillHostSelect(hosts) {
    const sel = document.getElementById('hostSelect');
    if (!sel) return;
    const prev = sel.value;  // จำ host ที่เลือกอยู่
    sel.innerHTML = hosts.map((h) =>
      '<option value="' + escapeHtml(h.host_id) + '">' + escapeHtml(h.hostname || h.host_id) + '</option>'
    ).join('');
    if (prev && hosts.some((h) => h.host_id === prev)) sel.value = prev;
    sel.onchange = () => window.Monitor.setHostId(sel.value);
  }

  async function renderHostView(id) {
    // ถ้าไม่ได้ระบุ id → ใช้ค่า dropdown ปัจจุบัน หรือ host แรกจาก fleet
    const sel = document.getElementById('hostSelect');
    if (!id && sel && sel.value) id = sel.value;
    if (!id) return;
    try {
      const host = await api('/api/v1/hosts/' + id);
      const metrics = await api('/api/v1/hosts/' + id + '/metrics?range=' + currentRange + '&metrics=' + currentMetric);
      document.getElementById('hostSelect').value = id;
      document.getElementById('hostIdLabel').textContent = host.hostname || host.host_id;
      const badge = document.getElementById('hostBadge');
      badge.className = 'badge ' + (host.online ? 'online' : 'offline');
      badge.textContent = host.online ? '● ออนไลน์' : '○ ออฟไลน์';
      document.getElementById('exportBtn').href = '/api/v1/hosts/' + id + '/export?range=' + currentRange;
      document.getElementById('tagInput').value = (host.tags || []).join(', ');
      document.getElementById('saveTagsBtn').onclick = async () => {
        const tags = document.getElementById('tagInput').value.split(',').map((t) => t.trim()).filter(Boolean);
        try {
          await api('/api/v1/hosts/' + id + '/tags', { method: 'PUT', body: JSON.stringify({ tags }) });
          toast('success', I18N.saved);
        } catch (e) { toast('error', e.message); }
      };
      renderKpi(host.summary);
      renderServices(host.services);
      renderMetricChips();
      renderChart(metrics.series);
    } catch (e) { toast('error', e.message); }
  }

  // metric selector chips — แสดง metric ที่เลือก (plot ทีละตัว กันสเกลเพี้ยน)
  function renderMetricChips() {
    const wrap = document.getElementById('metricChips');
    if (!wrap) return;
    wrap.innerHTML = METRICS.map((m) =>
      '<button class="pill' + (m.key === currentMetric ? ' active' : '') + '" data-metric="' + m.key + '">' + m.label + '</button>'
    ).join('');
    wrap.querySelectorAll('[data-metric]').forEach((b) => {
      b.onclick = () => {
        currentMetric = b.dataset.metric;
        wrap.querySelectorAll('[data-metric]').forEach((x) => x.classList.toggle('active', x === b));
        const id = currentRouteId();
        if (id) renderHostView(id);
      };
    });
  }

  // range buttons (event delegation กัน re-render)
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-range]');
    if (!btn) return;
    currentRange = btn.dataset.range;
    document.querySelectorAll('[data-range]').forEach((b) => b.classList.toggle('active', b === btn));
    const id = currentRouteId();
    if (id) renderHostView(id);
  });

  function currentRouteId() {
    const sel = document.getElementById('hostSelect');
    return sel && sel.value ? sel.value : null;
  }

  window.Dashboard = { renderFleetCards, renderHostView, renderKpi, renderChart, fillHostSelect, renderFleetStats };
})();
