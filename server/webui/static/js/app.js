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

  // ── routing ──
  const routes = {
    fleet: () => { renderFleetView(); },
    alerts: () => { AlertsView.loadAlerts(); },
    settings: () => { AlertsView.loadSettings(); },
    host: (id) => { Dashboard.renderHostView(id); },
  };

  function currentRoute() {
    const h = location.hash.replace(/^#/, '') || '/fleet';
    const parts = h.split('/').filter(Boolean);
    if (parts[0] === 'host' && parts[1]) return { name: 'host', id: parts[1] };
    return { name: parts[0] || 'fleet' };
  }

  function showView(name) {
    document.querySelectorAll('.view').forEach((v) => v.classList.remove('active'));
    const target = document.getElementById('view-' + (name === 'host' ? 'host' : name));
    if (target) target.classList.add('active');
    document.querySelectorAll('.sidebar a').forEach((a) => {
      a.classList.toggle('active', a.dataset.nav === (name === 'host' ? 'fleet' : name));
    });
  }

  async function route() {
    const r = currentRoute();
    showView(r.name);
    if (routes[r.name]) await routes[r.name](r.id);
  }

  window.addEventListener('hashchange', route);

  // ── fleet poll ──
  async function loadFleet(quiet) {
    try {
      fleetData = await api('/api/v1/hosts');
      renderFleetView();
    } catch (e) { if (!quiet) toast('error', e.message); }
  }

  function renderFleetView() {
    Dashboard.renderFleetCards(fleetData);
    updateStatusbar(fleetData);
    if (fleetTimer) clearInterval(fleetTimer);
    fleetTimer = setInterval(() => loadFleet(true), 10000);
    // search filter
    const input = document.getElementById('searchInput');
    input.oninput = () => Dashboard.renderFleetCards(fleetData, input.value.trim());
  }

  function filteredHosts(search) {
    if (!search) return fleetData;
    return fleetData.filter((h) =>
      (h.hostname + h.host_id).toLowerCase().includes(search.toLowerCase()));
  }

  // ── statusbar ──
  function updateStatusbar(hosts) {
    const online = hosts.filter((h) => h.online).length;
    const offline = hosts.length - online;
    statusbar.textContent = 'Monitor v0.1.0 · ' + online + ' host ออนไลน์ · ' + offline + ' ออฟไลน์';
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
    await route();
    await loadFleet();
  });

  // expose สำหรับ dashboard.js / alerts.js
  window.Monitor = { api, toast, confirmModal, loadFleet };
})();
