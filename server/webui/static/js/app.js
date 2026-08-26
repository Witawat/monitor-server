// app.js — SPA shell: hash routing + toast + modal + auth + fleet poll
(function () {
  const content = document.getElementById('content');
  const statusbar = document.getElementById('statusbar');
  let fleetTimer = null;
  let fleetData = [];

  // ── helpers ──

  async function api(path, opts = {}) {
    const res = await fetch(path, {
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      ...opts,
    });
    if (res.status === 401 && !path.includes('/auth/login')) {
      toast('error', I18N.sessionExpired);
      setTimeout(() => { location.href = '/'; }, 800);
      throw new Error('unauthorized');
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || ('HTTP ' + res.status));
    }
    return res.json();
  }

  function toast(type, msg) {
    const el = document.createElement('div');
    el.className = 'toast ' + type;
    el.textContent = msg;
    document.getElementById('toastWrap').appendChild(el);
    if (type !== 'error') setTimeout(() => el.remove(), 4000);
  }

  function showBanner(msg) {
    const b = document.getElementById('errorBanner');
    if (b) { b.textContent = msg; b.style.display = 'block'; }
  }
  function hideBanner() {
    const b = document.getElementById('errorBanner');
    if (b) { b.textContent = ''; b.style.display = 'none'; }
  }

  // ── modal confirm ──
  function confirmModal(text) {
    return new Promise((resolve) => {
      const overlay = document.getElementById('modalOverlay');
      document.getElementById('modalText').textContent = text;
      overlay.classList.add('show');
      const done = (val) => {
        overlay.classList.remove('show');
        cancelBtn.onclick = confirmBtn.onclick = null;
        resolve(val);
      };
      const cancelBtn = document.getElementById('modalCancel');
      const confirmBtn = document.getElementById('modalConfirm');
      cancelBtn.onclick = () => done(false);
      confirmBtn.onclick = () => done(true);
    });
  }

  // ── routing (หน้าเดียวเลื่อนยาว: nav ลิงก์ anchor scroll + host dropdown) ──
  const sections = ['fleet', 'alerts', 'settings', 'host'];

  async function initAll() {
    // โหลดข้อมูลทุก section หนึ่งครั้ง (long page — ไม่สลับ view)
    renderFleetView();
    await AlertsView.loadAlerts();
    await AlertsView.loadSettings();
    // เลือก host: จาก hash #/host/<id> หรือตัวแรก
    const parts = location.hash.replace(/^#/, '').split('/').filter(Boolean);
    const hashHost = parts[0] === 'host' && parts[1] ? parts[1] : '';
    const sel = document.getElementById('hostSelect');
    const firstId = fleetData.length ? fleetData[0].host_id : '';
    const target = hashHost || firstId;
    if (target) await Dashboard.renderHostView(target);
    else renderHostEmpty();
  }

  function renderHostEmpty() {
    const wrap = document.querySelector('.chart-wrap');
    if (wrap) wrap.innerHTML = '<div class="empty-note">' + I18N.noHostData + '</div>';
  }

  function scrollToSection(name) {
    const el = document.getElementById('view-' + name);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  window.scrollToSection = scrollToSection;

  // nav click → scroll (ไม่เปลี่ยน hash route แบบเดิม)
  document.querySelectorAll('.sidebar a[data-nav]').forEach((a) => {
    a.addEventListener('click', (e) => {
      e.preventDefault();
      document.querySelectorAll('.sidebar a').forEach((x) => x.classList.remove('active'));
      a.classList.add('active');
      scrollToSection(a.dataset.nav);
    });
  });

  // host id ที่เลือกปัจจุบัน (เปลี่ยนผ่าน hostSelect)
  let currentHostId = '';
  async function setHostId(id) {
    currentHostId = id;
    location.hash = '#/host/' + id;  // เก็บไว้ให้ back/reload กลับตัวเดิม
    await Dashboard.renderHostView(id);
    scrollToSection('host');
  }

  // support back/reload: ถ้า hash เป็น #/host/<id> → เลือก host นั้น (แล้ว scroll)
  window.addEventListener('hashchange', async () => {
    const parts = location.hash.replace(/^#/, '').split('/').filter(Boolean);
    if (parts[0] === 'host' && parts[1]) {
      await Dashboard.renderHostView(parts[1]);
    }
  });

  // ── fleet poll ──
  async function loadFleet(quiet) {
    try {
      fleetData = await api('/api/v1/hosts');
      hideBanner();
      renderFleetView();
    } catch (e) {
      if (!quiet) { toast('error', e.message); }
      if (!fleetData.length) showBanner(I18N.networkErr);
    }
  }

  function renderFleetView() {
    renderFleetFiltered();
    updateStatusbar(fleetData);
    Dashboard.fillHostSelect(fleetData);  // อัปเดต dropdown host ใน dashboard
    if (fleetTimer) clearInterval(fleetTimer);
    fleetTimer = setInterval(() => loadFleet(true), 10000);
  }

  let currentTag = '';
  let currentOnline = null;  // null=ทั้งหมด, true=ออนไลน์, false=ออฟไลน์

  function getSearch() {
    const input = document.getElementById('searchInput');
    return input ? input.value.trim() : '';
  }

  function setOnlineFilter(online) {
    currentOnline = online;
    document.getElementById('filterAll').classList.toggle('active', online === null);
    document.getElementById('filterOnline').classList.toggle('active', online === true);
    document.getElementById('filterOffline').classList.toggle('active', online === false);
    renderFleetFiltered();
  }

  function setTag(tag) {
    currentTag = tag;
    document.querySelectorAll('#tagFilters .pill').forEach((p) =>
      p.classList.toggle('active', p.dataset.tag === tag));
    renderFleetFiltered();
  }

  function renderFleetFiltered() {
    let list = fleetData;
    if (currentOnline === true) list = list.filter((h) => h.online);
    if (currentOnline === false) list = list.filter((h) => !h.online);
    Dashboard.renderFleetCards(list, getSearch(), currentTag);
  }

  async function loadTags() {
    try {
      const tags = await api('/api/v1/hosts/tags');
      const wrap = document.getElementById('tagFilters');
      wrap.innerHTML = tags.map((t) =>
        '<button class="pill' + (t === currentTag ? ' active' : '') + '" data-tag="' + escapeHtml(t) + '">#' + escapeHtml(t) + '</button>').join('');
      wrap.querySelectorAll('.pill').forEach((p) => {
        p.onclick = () => setTag(p.dataset.tag);
      });
    } catch (e) { /* เงียบ — tags เป็น optional */ }
  }

  function filteredHosts(search) {
    if (!search) return fleetData;
    return fleetData.filter((h) =>
      (h.hostname + h.host_id).toLowerCase().includes(search.toLowerCase()));
  }

  // ── statusbar ──
  let versionPrefix = '';
  function updateStatusbar(hosts) {
    const online = hosts.filter((h) => h.online).length;
    const offline = hosts.length - online;
    if (!versionPrefix) {
      const m = statusbar.textContent.match(/Monitor v[0-9.]+/);
      versionPrefix = m ? m[0] : 'Monitor';
    }
    statusbar.textContent = versionPrefix + ' · ' + online + ' host ออนไลน์ · ' + offline + ' ออฟไลน์';
  }

  // ── user + logout ──
  async function initUser() {
    try {
      const me = await api('/api/v1/auth/me');
      document.getElementById('currentUser').textContent = me.username;
    } catch (e) { /* 401 จัดการใน api() */ }
  }

  document.getElementById('logoutBtn').addEventListener('click', async () => {
    await fetch('/api/v1/auth/logout', { method: 'POST' });
    location.href = '/';
  });

  // ── boot ──
  window.addEventListener('DOMContentLoaded', async () => {
    initUser();
    const grid = document.getElementById('hostGrid');
    if (grid) grid.innerHTML = '<p class="empty-note">' + I18N.loading + '</p>';
    // bind ครั้งเดียว (ไม่ทำซ้ำตอน poll)
    const input = document.getElementById('searchInput');
    if (input) input.oninput = () => renderFleetFiltered();
    document.getElementById('filterAll').onclick = () => setOnlineFilter(null);
    document.getElementById('filterOnline').onclick = () => setOnlineFilter(true);
    document.getElementById('filterOffline').onclick = () => setOnlineFilter(false);
    await loadFleet();
    loadTags();
    await initAll();
  });

  // expose สำหรับ dashboard.js / alerts.js
  window.Monitor = { api, toast, confirmModal, loadFleet, setHostId };
})();
