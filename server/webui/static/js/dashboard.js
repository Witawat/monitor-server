// dashboard.js — fleet cards + host KPI + Chart.js (WEBUI_DESIGN.md §5-7)
(function () {
  const { api, toast } = window.Monitor;
  let currentRange = '1h';
  let chart = null;

  function fillColor(p) {
    if (p >= 90) return 'var(--danger)';
    if (p >= 80) return 'var(--warn)';
    return 'var(--accent)';
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
        ? '<div class="netline"><span>↑ ' + formatRate(s.net_rx || 0) + '</span><span>↓ ' + formatRate(s.net_tx || 0) + '</span></div>'
        : '<div class="netline"><span>—</span><span>—</span></div>';
      const row = (label, pct) =>
        '<div class="metric-row"><div class="label"><span>' + label + '</span><span>' + formatPercent(pct) + '</span></div>' +
        '<div class="progress"><span style="width:' + (pct || 0) + '%;background:' + fillColor(pct || 0) + '"></span></div></div>';
      return '<div class="card' + (online ? '' : ' offline') + '" data-host="' + escapeHtml(h.host_id) + '">' +
        '<h3>' + escapeHtml(h.hostname) + ' ' + badge + '</h3>' + tags +
        row('CPU', s.cpu_percent) + row('RAM', s.mem_percent) + row('Disk', s.disk_percent) +
        net +
        '<div class="netline"><span>uptime ' + formatUptime(online ? s.uptime : null) + '</span></div>' +
        '</div>';
    }).join('');
    grid.querySelectorAll('.card').forEach((card) => {
      card.onclick = () => { location.hash = '#/host/' + card.dataset.host; };
    });
  }

  function renderKpi(summary) {
    const s = summary || {};
    const cells = [
      ['CPU', formatPercent(s.cpu_percent), ''],
      ['RAM', formatPercent(s.mem_percent), formatBytes(s.mem_total)],
      ['Disk', formatPercent(s.disk_percent), formatBytes(s.disk_total || s.mem_total)],
      ['Uptime', formatUptime(s.uptime), ''],
    ];    document.getElementById('kpiRow').innerHTML = cells.map((c) =>
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

  function renderChart(series) {
    if (chart) { chart.destroy(); chart = null; }  // กัน instance leak (M8)
    const wrap = document.querySelector('.chart-wrap');
    const any = Object.values(series).some((s) => s.points && s.points.length);
    if (!any) {
      wrap.innerHTML = '<div class="empty-note">' + I18N.noData + '</div>';
      return;
    }
    wrap.innerHTML = '<canvas id="metricChart"></canvas>';
    const ctx = document.getElementById('metricChart');
    const datasets = Object.entries(series).map(([name, s]) => ({
      label: name,
      data: s.points.map((p) => ({ x: p[0] * 1000, y: p[1] })),
      borderColor: 'var(--accent)',
      borderWidth: 2,
      pointRadius: 0,
      tension: 0.3,
      fill: false,
      unit: s.unit,
    }));
    chart = new Chart(ctx, {
      type: 'line',
      data: { datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: 'nearest', intersect: false },
        scales: {
          x: {
            type: 'linear',
            ticks: {
              maxTicksLimit: 8,
              callback: (v) => formatAxisTime(v),
            },
          },
          y: { beginAtZero: true },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: (items) => formatAxisTime(items[0].parsed.x),
              label: (c) => {
                const ds = datasets[c.datasetIndex];
                const unit = ds.unit === '%' ? '%' : (ds.unit === 'bytes' ? 'bytes' : '');
                const val = unit === '%' ? formatPercent(c.raw.y) : (unit === 'bytes' ? formatBytes(c.raw.y) : formatInt(c.raw.y));
                return ds.label + ': ' + val;
              },
            },
          },
        },
      },
    });
  }

  async function renderHostView(id) {
    try {
      const host = await api('/api/v1/hosts/' + id);
      const metrics = await api('/api/v1/hosts/' + id + '/metrics?range=' + currentRange);
      document.getElementById('hostTitle').textContent = host.hostname || host.host_id;
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
      renderChart(metrics.series);
    } catch (e) { toast('error', e.message); }
  }

  // range buttons (bind ครั้งเดียว — ใช้ event delegation กัน re-render)
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-range]');
    if (!btn) return;
    currentRange = btn.dataset.range;
    document.querySelectorAll('[data-range]').forEach((b) => b.classList.toggle('active', b === btn));
    const id = currentRouteId();
    if (id) renderHostView(id);
  });

  function currentRouteId() {
    const parts = location.hash.replace(/^#/, '').split('/').filter(Boolean);
    return parts[0] === 'host' && parts[1] ? parts[1] : null;
  }

  window.Dashboard = { renderFleetCards, renderHostView, renderKpi, renderChart };
})();
