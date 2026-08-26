// alerts.js — alerts view + settings (tokens) (WEBUI_DESIGN.md §5.4-5.5)
(function () {
  const { api, toast, confirmModal } = window.Monitor;

  async function loadAlerts() {
    try {
      const [rules, history] = await Promise.all([
        api('/api/v1/alerts'),
        api('/api/v1/alerts/history'),
      ]);
      const body = document.getElementById('alertsBody');
      const tabRules = document.getElementById('tabRules');
      const tabHistory = document.getElementById('tabHistory');
      const render = () => {
        const showRules = tabRules.classList.contains('active');
        if (showRules) {
          if (!rules.length) {
            body.innerHTML = '<p class="empty-note">ยังไม่มีกฎ alert</p>';
            return;
          }
          body.innerHTML = '<table><thead><tr><th>ชื่อ</th><th>Host</th><th>Metric</th><th>Threshold</th></tr></thead><tbody>' +
            rules.map((r) => '<tr><td>' + escapeHtml(r.name) + '</td><td>' + escapeHtml(r.host_id || 'ทุก host') + '</td><td>' + escapeHtml(r.metric) + '</td><td>' + escapeHtml(r.op) + ' ' + escapeHtml(r.threshold) + '</td></tr>').join('') +
            '</tbody></table>';
        } else {
          if (!history.length) {
            body.innerHTML = '<p class="empty-note">ยังไม่มีประวัติ alert</p>';
            return;
          }
          body.innerHTML = '<table><thead><tr><th>เวลา</th><th>Host</th><th>Metric</th><th>ค่า</th><th></th></tr></thead><tbody>' +
            history.map((h) =>
              '<tr data-id="' + h.id + '" style="' + (h.ack ? 'opacity:.6' : '') + '">' +
              '<td>' + new Date(h.created_at * 1000).toLocaleString('th-TH') + '</td>' +
              '<td>' + escapeHtml(h.host_id) + '</td><td>' + escapeHtml(h.metric) + '</td>' +
              '<td>' + escapeHtml(h.value) + ' (เกิน ' + escapeHtml(h.threshold) + ')</td>' +
              '<td>' + (h.ack ? '<span class="badge online">ack ✓</span>' : '<button class="btn" data-ack="' + h.id + '">ack</button>') + '</td>' +
              '</tr>'
            ).join('') + '</tbody></table>';
          body.querySelectorAll('[data-ack]').forEach((btn) => {
            btn.onclick = async () => {
              try {
                await api('/api/v1/alerts/history/' + btn.dataset.ack + '/ack', { method: 'POST' });
                toast('success', 'ack แล้ว');
                loadAlerts();
              } catch (e) { toast('error', e.message); }
            };
          });
        }
      };
      tabRules.onclick = () => { tabRules.classList.add('active'); tabHistory.classList.remove('active'); render(); };
      tabHistory.onclick = () => { tabHistory.classList.add('active'); tabRules.classList.remove('active'); render(); };
      render();
    } catch (e) { toast('error', e.message); }
  }

  async function loadSettings() {
    try {
      const tokens = await api('/api/v1/auth/tokens');
      const tbody = document.getElementById('tokenTable');
      if (!tokens.length) {
        tbody.innerHTML = '<tr><td colspan="3" style="color:var(--text-2)">ยังไม่มี host/token</td></tr>';
      } else {
        tbody.innerHTML = tokens.map((t) =>
          '<tr><td>' + t.host_id + '</td><td><code>' + (t.token || '—') + '</code></td>' +
          '<td><button class="btn danger" data-revoke="' + t.host_id + '">revoke</button></td></tr>'
        ).join('');
      }
      tbody.querySelectorAll('[data-revoke]').forEach((btn) => {
        btn.onclick = async () => {
          if (!(await confirmModal('เพิกถอน token ของ ' + btn.dataset.revoke + '?'))) return;
          try {
            await api('/api/v1/auth/tokens/' + btn.dataset.revoke, { method: 'DELETE' });
            toast('success', I18N.saved);
            loadSettings();
          } catch (e) { toast('error', e.message); }
        };
      });

      document.getElementById('genTokenBtn').onclick = async () => {
        const hostId = document.getElementById('newTokenHost').value.trim();
        if (!hostId) { toast('error', 'ระบุ host_id'); return; }
        try {
          const res = await api('/api/v1/auth/tokens', {
            method: 'POST',
            body: JSON.stringify({ host_id: hostId }),
          });
          document.getElementById('newTokenResult').innerHTML =
            '<code>Token: ' + res.token + '</code> <small>(แสดงครั้งเดียว)</small>';
          toast('success', 'สร้าง token แล้ว');
          loadSettings();
        } catch (e) { toast('error', e.message); }
      };
    } catch (e) { toast('error', e.message); }
  }

  window.AlertsView = { loadAlerts, loadSettings };
})();
