// dashboard.js — fleet cards + host KPI + Chart.js (WEBUI_DESIGN.md §5-7)
(function () {
  const { api, toast } = window.Monitor;
  // 7.6: จำ range ที่ผู้ใช้เลือกไว้ใน localStorage
  const savedRange = localStorage.getItem('monitor.range');
  let currentRange = ['1h','6h','1d','7d','30d','45d'].includes(savedRange) ? savedRange : '1h';
  let selectedMetrics = ['cpu_percent', 'memory.percent'];  // ค่า default: หน่วย % อ่านง่ายสุด
  let currentHost = null;  // host ที่กำลังดูอยู่ (สำหรับ realtime poll)
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

  // palette สีของแต่ละ series (หลายเส้นต้องต่างกัน)
  const PALETTE = ['var(--accent)', '#2563eb', '#d97706', '#7c3aed', '#db2777', '#0891b2', '#65a30d'];
  function seriesColor(index) { return PALETTE[index % PALETTE.length]; }

  function metricOf(key) { return METRICS.find((x) => x.key === key); }
  function unitOf(key) {
    const m = metricOf(key);
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
      grid.innerHTML = '<div class="empty-state"><div class="empty-icon">📊</div>' +
        '<p>' + I18N.noHost + '</p>' +
        '<button class="btn" id="emptyInstallBtn">ดูวิธีติดตั้ง agent</button></div>';
      const b = document.getElementById('emptyInstallBtn');
      if (b) b.onclick = () => { openInstallModal(); };
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
      const trend = (s.trend || []).length > 1 ? s.trend : null;
      // 7.7: เตือน service ที่หยุด (จาก summary.services_down)
      const downSvc = (s.services_down || []);
      const downBadge = downSvc.length
        ? '<div class="svc-warn">⚠ service หยุด: ' + downSvc.map((x) => escapeHtml(x)).join(', ') + '</div>'
        : '';
      return '<div class="card' + (online ? '' : ' offline') + '" data-host="' + escapeHtml(h.host_id) + '">' +
        '<h3>' + osIcon(h.platform) + '<span class="host-name">' + escapeHtml(h.hostname || h.host_id) + '</span> ' + badge + '</h3>' + tags +
        row('CPU', s.cpu_percent) + row('RAM', s.mem_percent) + row('Disk', s.disk_percent) +
        net +
        '<div class="netline"><span>uptime ' + formatUptime(online ? s.uptime : null) + '</span></div>' +
        downBadge +
        (trend ? '<div class="spark-wrap"><canvas class="spark" data-host="' + escapeHtml(h.host_id) + '"></canvas></div>' : '') +
        '</div>';
    }).join('');
    drawSparklines(list);
    grid.querySelectorAll('.card').forEach((card) => {
      card.onclick = () => {
        window.Monitor.setHostId(card.dataset.host);   // เลือก host + scroll to host section
        scrollToSection('host');
      };
    });
  }

  // ── sparkline ใน Fleet card (mini Chart.js; destroy เก่ากัน leak ตอน poll) ──
  const sparkCharts = [];
  function clearSparklines() {
    while (sparkCharts.length) { (sparkCharts.pop()).destroy(); }
  }
  function drawSparklines(hosts) {
    clearSparklines();  // re-render ใหม่ทุกครั้ง
    const trend = new Map(hosts.map((h) => [h.host_id, (h.summary || {}).trend || []]));
    document.querySelectorAll('#hostGrid canvas.spark').forEach((canvas) => {
      const pts = trend.get(canvas.dataset.host) || [];
      if (pts.length < 2) return;
      const last = pts[pts.length - 1];
      const color = fillColor(last);
      sparkCharts.push(new Chart(canvas, {
        type: 'line',
        data: { datasets: [{ data: pts, borderColor: color, borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false }] },
        options: {
          responsive: false, maintainAspectRatio: false, animation: false,
          plugins: { legend: { display: false }, tooltip: { enabled: false } },
          scales: { x: { display: false }, y: { display: false, beginAtZero: true } },
        },
      }));
    });
  }

  function renderKpi(summary) {
    const s = summary || {};
    const cells = [
      ['CPU', formatPercent(s.cpu_percent), '', s.cpu_percent],
      ['RAM', formatPercent(s.mem_percent), formatBytes(s.mem_total), s.mem_percent],
      ['Disk', formatPercent(s.disk_percent), formatBytes(s.disk_total || 0), s.disk_percent],
      ['Uptime', formatUptime(s.uptime), '', null],
    ];
    document.getElementById('kpiRow').innerHTML = cells.map((c) => {
      // 7.4: ตัวเลข KPI สีตาม threshold (เฉพาะ % ถ้ามีค่า)
      const kpiColor = (c[3] == null) ? '' : ' style="color:' + fillColor(c[3]) + '"';
      return '<div class="kpi"><div class="num"' + kpiColor + '>' + c[1] + '</div><div class="lbl">' + c[0] + (c[2] ? ' · ' + c[2] : '') + '</div></div>';
    }).join('');
  }

  function renderServices(services) {
    const el = document.getElementById('servicesRow');
    if (!services || !services.length) { el.innerHTML = ''; return; }
    el.innerHTML = services.map((s) =>
      '<span class="badge ' + (s.up ? 'online' : 'offline') + '">' + (s.up ? '●' : '○') + ' ' + escapeHtml(s.name) + (s.up ? ' ทำงาน' : ' หยุด') + '</span>'
    ).join('');
  }

  // ตาราง port ที่เปิด/ปิดของ host — จาก host.ports (ฝั่ง server query ล่าสุด)
  function renderPorts(ports) {
    const body = document.getElementById('portsBody');
    const section = document.getElementById('portsSection');
    if (!body) return;
    if (!ports || !ports.length) { if (section) section.style.display = 'none'; if (body) body.innerHTML = ''; return; }
    if (section) section.style.display = 'block';
    body.innerHTML = ports.map((p) =>
      '<tr><td>: ' + escapeHtml(p.port) + '</td><td>' + escapeHtml(p.name || '—') + '</td>' +
      '<td>' + (p.up ? '<span class="badge online">● เปิด</span>' : '<span class="badge offline">○ ปิด</span>') + '</td></tr>'
    ).join('');
  }

  // alert ที่เพิ่งเกิดขึ้นของ host นี้ (บริบทปัญหา) — ใช้ /api/v1/alerts/history?host_id=<id>
  async function renderHostAlertHistory(hostId) {
    const el = document.getElementById('hostAlerts');
    if (!el) return;
    try {
      const history = await api('/api/v1/alerts/history?host_id=' + hostId);
      const recent = history.slice(0, 5);
      if (!recent.length) {
        el.innerHTML = '<div class="host-alert-empty">ไม่มี alert ล่าสุดของ host นี้</div>';
        return;
      }
      el.innerHTML = '<div class="host-alert-title">Alert ล่าสุด</div>' +
        recent.map((h) =>
          '<div class="host-alert-row ' + (h.ack ? 'acked' : '') + '">' +
          '<span class="ha-time">' + new Date(h.created_at * 1000).toLocaleString('th-TH') + '</span>' +
          '<span class="ha-metric">' + escapeHtml(h.metric) + '</span>' +
          '<span class="ha-val">' + escapeHtml(h.value) + ' (เกิน ' + escapeHtml(h.threshold) + ')</span>' +
          (h.ack ? '<span class="badge online">ack ✓</span>' : '<span class="badge warn">รอ ack</span>') +
          '</div>'
        ).join('');
    } catch (e) { /* เงียบ — ส่วนนี้เป็นเสริม */ }
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
    const keys = (selectedMetrics.length ? selectedMetrics : ['cpu_percent'])
      .filter((k) => series[k] && series[k].points && series[k].points.length);
    if (!keys.length) {
      wrap.innerHTML = '<div class="empty-note">' + I18N.noData + '</div>';
      return;
    }
    // ทุก metric ที่เลือกต้องเป็นหน่วยเดียวกัน (กันสเกลเพี้ยน — uptime วินาทีปน cpu %)
    const baseUnit = unitOf(keys[0]);
    if (!keys.every((k) => unitOf(k) === baseUnit)) {
      wrap.innerHTML = '<div class="empty-note">' + I18N.noData + '</div>';
      return;
    }
    wrap.innerHTML = '<canvas id="metricChart"></canvas>';
    const ctx = document.getElementById('metricChart');
    const datasets = keys.map((k, i) => {
      const m = metricOf(k);
      return {
        label: m ? m.label : k,
        unit: baseUnit,
        data: series[k].points.map((p) => ({ x: p[0] * 1000, y: p[1] })),
        borderColor: seriesColor(i),
        backgroundColor: seriesColor(i),
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.3,
        fill: false,
      };
    });
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
            ticks: { maxTicksLimit: 8, callback: (v) => formatAxisTime(v) },
          },
          y: {
            beginAtZero: true,
            ticks: { callback: (v) => fmtByUnit(v, baseUnit) },
            title: { display: true, text: unitLabel(baseUnit), color: 'var(--text-2)' },
          },
        },
        plugins: {
          legend: { display: true, labels: { color: 'var(--text-2)', usePointStyle: true, boxWidth: 8 } },
          tooltip: {
            callbacks: {
              title: (items) => formatAxisTime(items[0].parsed.x),
              label: (c) => c.dataset.label + ': ' + fmtByUnit(c.raw.y, baseUnit),
            },
          },
        },
      },
    });
  }

  function unitLabel(unit) {
    if (unit === 'percent') return '%';
    if (unit === 'bytes') return 'bytes';
    if (unit === 'sec') return 'seconds';
    return 'count';
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

  const MINUTE_MS = 60000;
  const HOUR_MS = 3600000;
  let chartTimer = null;
  function startHostRefresh(id) {
    // poll host detail + metrics ทุก 5s (realtime) — ใช้เฉพาะ range เล็ก (1h/6h)
    if (chartTimer) clearInterval(chartTimer);
    const refresh = async () => {
      try {
        const host = await api('/api/v1/hosts/' + id);
        if (host.host_id !== id) return;  // host เปลี่ยนไปแล้ว → หยุด
        const keys = selectedMetrics.length ? selectedMetrics : ['cpu_percent'];
        const baseUnit = unitOf(keys[0]);
        const unitKeys = keys.filter((k) => unitOf(k) === baseUnit);
        const metrics = await api('/api/v1/hosts/' + id + '/metrics?range=' + currentRange + '&metrics=' + unitKeys.join(','));
        renderKpi(host.summary);
        renderServices(host.services);
        renderPorts(host.ports);
        renderHostAlertHistory(id);
        renderChart(metrics.series);
      } catch (e) { /* เงียบ — poll ถัดไปจะลองใหม่ */ }
    };
    // range กว้าง (7d/30d/45d) ไม่ต้อง poll ถี่ — ตัดเป็น 1 นาที กันยิง DB บ่อย
    const period = (currentRange === '1h' || currentRange === '6h') ? 5000 : MINUTE_MS;
    chartTimer = setInterval(refresh, period);
  }
  function stopHostRefresh() { if (chartTimer) { clearInterval(chartTimer); chartTimer = null; } }

  async function renderHostView(id) {
    // ถ้าไม่ได้ระบุ id → ใช้ค่า dropdown ปัจจุบัน หรือ host แรกจาก fleet
    const sel = document.getElementById('hostSelect');
    if (!id && sel && sel.value) id = sel.value;
    if (!id) return;
    stopHostRefresh();  // หยุด poll ของ host ก่อนหน้า (กันเรียกซ้ำ/หาย)
    try {
      const host = await api('/api/v1/hosts/' + id);
      // metric ที่เลือก (ต้องหน่วยเดียวกัน) — ส่งหลายตัวคั่น comma
      const keys = selectedMetrics.length ? selectedMetrics : ['cpu_percent'];
      const baseUnit = unitOf(keys[0]);
      const unitKeys = keys.filter((k) => unitOf(k) === baseUnit);
      const metrics = await api('/api/v1/hosts/' + id + '/metrics?range=' + currentRange + '&metrics=' + unitKeys.join(','));
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
      renderPorts(host.ports);
      renderHostAlertHistory(id);
      renderMetricChips();
      renderChart(metrics.series);
      currentHost = id;
      startHostRefresh(id);   // realtime: poll ทุก 5s (range เล็ก) / 1 นาที (range กว้าง)
    } catch (e) { toast('error', e.message); }
  }

  // metric selector chips — toggle หลายตัว (ต้องหน่วยเดียวกัน ถึงวาดรวม)
  function renderMetricChips() {
    const wrap = document.getElementById('metricChips');
    if (!wrap) return;
    wrap.innerHTML = METRICS.map((m) =>
      '<button class="pill' + (selectedMetrics.includes(m.key) ? ' active' : '') + '" data-metric="' + m.key + '">' + m.label + '</button>'
    ).join('');
    wrap.querySelectorAll('[data-metric]').forEach((b) => {
      b.onclick = () => {
        toggleMetric(b.dataset.metric);
      };
    });
  }

  // toggle metric เข้า/ออกจาก selectedMetrics; อย่างน้อย 1 ตัว
  function toggleMetric(key) {
    const idx = selectedMetrics.indexOf(key);
    if (idx >= 0) {
      if (selectedMetrics.length > 1) selectedMetrics.splice(idx, 1);
      else { toast('info', 'ต้องเลือกอย่างน้อย 1 metric'); return; }
    } else {
      // เพิ่ม — ถ้าหน่วยต่างจากที่เลือกอยู่ ให้เปลี่ยนเป็นตัวที่เพิ่งคลิก (กันสเกลเพี้ยน)
      if (selectedMetrics.length && unitOf(selectedMetrics[0]) !== unitOf(key)) {
        selectedMetrics = [key];
      } else {
        selectedMetrics.push(key);
      }
    }
    const id = currentRouteId();
    if (id) renderHostView(id);
  }

  // range buttons (event delegation กัน re-render)
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-range]');
    if (!btn) return;
    currentRange = btn.dataset.range;
    localStorage.setItem('monitor.range', currentRange);  // 7.6
    document.querySelectorAll('[data-range]').forEach((b) => b.classList.toggle('active', b === btn));
    const id = currentRouteId();
    if (id) renderHostView(id);
  });

  function currentRouteId() {
    const sel = document.getElementById('hostSelect');
    return sel && sel.value ? sel.value : null;
  }

  // ── modal "วิธีติดตั้ง agent" (แสดงจากหน้าเว็บ ไม่พึ่งไฟล์ .md) ──
  function openInstallModal() {
    const modal = document.getElementById('installModal');
    if (!modal) return;
    const cmd = document.getElementById('installCmd');
    const host = document.getElementById('installHost');
    host.value = '';
    const result = document.getElementById('installTokenResult');
    result.textContent = '';
    // base URL ที่ใช้สร้างคำสั่ง (ขึ้นกับที่ access หน้าปัจจุบัน)
    cmd.textContent = buildInstallCmd('');
    modal.classList.add('show');

    host.oninput = () => { cmd.textContent = buildInstallCmd(host.value.trim()); };
    document.getElementById('installGenToken').onclick = async () => {
      const hid = host.value.trim();
      if (!hid) { result.textContent = 'ระบุ host_id ก่อน'; return; }
      try {
        const res = await api('/api/v1/auth/tokens', { method: 'POST', body: JSON.stringify({ host_id: hid }) });
        result.textContent = 'token: ' + res.token;
        cmd.textContent = buildInstallCmd(res.token);
      } catch (e) { result.textContent = e.message; }
    };
    document.getElementById('copyInstallCmd').onclick = () => {
      navigator.clipboard.writeText(cmd.textContent).then(() => toast('success', 'คัดลอกคำสั่งแล้ว'));
    };
    document.getElementById('installClose').onclick = () => modal.classList.remove('show');
    modal.onclick = (e) => { if (e.target === modal) modal.classList.remove('show'); };
  }

  function buildInstallCmd(token) {
    const url = location.origin;   // http://host:port ปัจจุบัน (ขึ้นกับวิธีเข้าถึง)
    return 'monitor-agent.exe --install --server ' + url + ' --token ' + (token || '<TOKEN>') +
      ' --interval 15 [--ports 80:web,443:https] [--watch nginx]';
  }

  // ── วิซาร์ด "เพิ่มเครื่องใหม่" — ระบุ option ครบ (interval/watch/ports/max-batch) ──
  function openAddHostModal() {
    const modal = document.getElementById('addHostModal');
    if (!modal) return;
    modal.classList.add('show');
    document.getElementById('addCmd').textContent = 'monitor-agent.exe --install --server ' + location.origin + ' --token <TOKEN> --interval 15 ...';
    document.getElementById('addHostMsg').textContent = 'ยังไม่สร้าง token';
    const any = ['addHostId', 'addInterval', 'addWatch', 'addPorts', 'addMaxBatch'];
    any.forEach((id) => { const el = document.getElementById(id); if (el) el.oninput = () => updateAddCmd(); });
    document.getElementById('addBuildCmd').onclick = async () => {
      const hid = document.getElementById('addHostId').value.trim();
      const msg = document.getElementById('addHostMsg');
      const cmd = document.getElementById('addCmd');
      if (!hid) { msg.textContent = 'ต้องระบุ host_id'; return; }
      try {
        const res = await api('/api/v1/auth/tokens', { method: 'POST', body: JSON.stringify({ host_id: hid }) });
        msg.textContent = 'token ถูกสร้าง (แสดงครั้งเดียว)';
        cmd.textContent = buildAddCmd(res.token);
      } catch (e) { msg.textContent = e.message; }
    };
    document.getElementById('copyAddCmd').onclick = () => {
      navigator.clipboard.writeText(document.getElementById('addCmd').textContent).then(() => toast('success', 'คัดลอกคำสั่งแล้ว'));
    };
    document.getElementById('addHostClose').onclick = () => modal.classList.remove('show');
    modal.onclick = (e) => { if (e.target === modal) modal.classList.remove('show'); };
    updateAddCmd();
  }

  function updateAddCmd() {
    const el = document.getElementById('addCmd');
    if (el) el.textContent = buildAddCmd(document.getElementById('addHostMsg').textContent && document.getElementById('addBuildCmd').dataset.token ? document.getElementById('addBuildCmd').dataset.token : '');
  }

  function buildAddCmd(token) {
    const hid = document.getElementById('addHostId').value.trim() || '<host_id>';
    const interval = document.getElementById('addInterval').value || 15;
    const watch = document.getElementById('addWatch').value.trim();
    const ports = document.getElementById('addPorts').value.trim();
    const maxBatch = document.getElementById('addMaxBatch').value || 100;
    let c = 'monitor-agent.exe --install --server ' + location.origin + ' --token ' + (token || '<TOKEN>') +
      ' --interval ' + interval + ' --watch ' + (watch || '<service>') + ' --ports ' + (ports || '<port:name>') +
      ' --max-batch ' + maxBatch;
    // บันทึก token ไว้ (updateAddCmd เรียกซ้ำได้โดยไม่ต้อง gen ใหม่)
    document.getElementById('addBuildCmd').dataset.token = token;
    return c;
  }

  function bindAddHost() {
    const btn = document.getElementById('addHostBtn');
    if (btn) btn.onclick = () => openAddHostModal();
  }

  window.Dashboard = { renderFleetCards, renderHostView, renderKpi, renderChart, fillHostSelect, renderFleetStats, openAddHostModal };
})();
