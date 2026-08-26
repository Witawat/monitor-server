// alerts.js — alerts view + settings (tokens) (WEBUI_DESIGN.md §5.4-5.5)
(function () {
  const { api, toast, confirmModal } = window.Monitor;

  // แสดงข้อมูล server/config (read-only) ที่หน้า ตั้งค่า — จาก /api/status (M5.1)
  function renderServerInfo(st) {
    const wrap = document.getElementById('serverInfo');
    if (!wrap) return;
    const s = st.server || {};
    const ing = st.ingest || {};
    const sto = st.storage || {};
    const items = [
      ['version', st.version],
      ['host:port', (s.host || '') + ':' + (s.port || '')],
      ['data_dir', s.data_dir],
      ['log_dir', s.log_dir],
      ['host_count', st.host_count],
      ['rate_limit/min', ing.rate_limit_per_min],
      ['offline_timeout', ing.offline_timeout_sec + 's'],
      ['retention (raw)', sto.retention_raw_days + ' วัน'],
      ['rollup', (sto.rollup_intervals || []).join(', ')],
    ];
    wrap.innerHTML = items.map(([k, v]) =>
      '<div class="info-item"><span class="info-label">' + escapeHtml(k) + '</span><span class="info-val">' + escapeHtml(v == null ? '—' : v) + '</span></div>'
    ).join('');
  }

  function fillRuleForm(r) {
    document.getElementById('ruleId').value = r && r.id ? r.id : '';
    document.getElementById('ruleName').value = r ? r.name : '';
    document.getElementById('ruleHost').value = r ? (r.host_id || '') : '';
    document.getElementById('ruleMetric').value = r ? r.metric : 'cpu_percent';
    document.getElementById('ruleOp').value = r ? r.op : '>';
    document.getElementById('ruleThreshold').value = r ? r.threshold : '';
    document.getElementById('ruleDuration').value = r ? (r.duration || '5m') : '5m';
    const notify = r ? (r.notify || []) : [];
    document.getElementById('ruleNotifyWebhook').checked = notify.includes('webhook');
    document.getElementById('ruleNotifyTelegram').checked = notify.includes('telegram');
    document.getElementById('ruleForm').style.display = 'block';
  }

  function showRuleForm() {
    fillRuleForm(null);
  }

  async function saveRule() {
    const id = document.getElementById('ruleId').value;
    const threshold = parseFloat(document.getElementById('ruleThreshold').value);
    if (isNaN(threshold)) { toast('error', 'threshold ต้องเป็นตัวเลข'); return; }
    const notify = [];
    if (document.getElementById('ruleNotifyWebhook').checked) notify.push('webhook');
    if (document.getElementById('ruleNotifyTelegram').checked) notify.push('telegram');
    const payload = {
      name: document.getElementById('ruleName').value.trim(),
      host_id: document.getElementById('ruleHost').value.trim(),
      metric: document.getElementById('ruleMetric').value,
      op: document.getElementById('ruleOp').value,
      threshold,
      duration: document.getElementById('ruleDuration').value.trim() || '5m',
      notify,
    };
    if (!payload.name) { toast('error', 'ต้องระบุชื่อ'); return; }
    try {
      if (id) {
        await api('/api/v1/alerts/' + id, { method: 'PUT', body: JSON.stringify(payload) });
      } else {
        await api('/api/v1/alerts', { method: 'POST', body: JSON.stringify(payload) });
      }
      document.getElementById('ruleForm').style.display = 'none';
      toast('success', I18N.saved);
      loadAlerts();
    } catch (e) { toast('error', e.message); }
  }

  async function deleteRule(id) {
    if (!(await confirmModal('ลบกฎนี้?'))) return;
    try {
      await api('/api/v1/alerts/' + id, { method: 'DELETE' });
      toast('success', 'ลบแล้ว');
      loadAlerts();
    } catch (e) { toast('error', e.message); }
  }

  async function loadAlerts() {
    try {
      const [rules, history, hosts] = await Promise.all([
        api('/api/v1/alerts'),
        api('/api/v1/alerts/history'),
        api('/api/v1/hosts'),
      ]);
      // เติมตัวเลือก host ในฟอร์มกฎ + dropdown กรอง
      const hostSel = document.getElementById('ruleHost');
      hostSel.innerHTML = '<option value="">— ทุก host —</option>' +
        hosts.map((h) => '<option value="' + escapeHtml(h.host_id) + '">' + escapeHtml(h.hostname || h.host_id) + '</option>').join('');
      const hostOpt = (h) => h.hostname || h.host_id;
      const hostName = (id) => (id && hosts.find((h) => h.host_id === id)) ? hostOpt(hosts.find((h) => h.host_id === id)) : id;
      const filt = document.getElementById('alertHostFilter');
      filt.innerHTML = '<option value="">ทุก host</option>' +
        hosts.map((h) => '<option value="' + escapeHtml(h.host_id) + '">' + escapeHtml(hostOpt(h)) + '</option>').join('');
      const body = document.getElementById('alertsBody');
      const tabRules = document.getElementById('tabRules');
      const tabHistory = document.getElementById('tabHistory');
      document.getElementById('newRuleBtn').onclick = showRuleForm;
      document.getElementById('saveRuleBtn').onclick = saveRule;
      document.getElementById('cancelRuleBtn').onclick = () => {
        document.getElementById('ruleForm').style.display = 'none';
      };
      const render = () => {
        const showRules = tabRules.classList.contains('active');
        const hostF = filt.value;
        const rulesF = hostF ? rules.filter((r) => !r.host_id || r.host_id === hostF) : rules;
        const historyF = hostF ? history.filter((h) => h.host_id === hostF) : history;
        if (showRules) {
          if (!rulesF.length) {
            body.innerHTML = '<p class="empty-note">ยังไม่มีกฎ alert</p>';
            return;
          }
          body.innerHTML = '<table><thead><tr><th>ชื่อ</th><th>Host</th><th>Metric</th><th>Threshold</th><th class="actions"></th></tr></thead><tbody>' +
            rulesF.map((r) => '<tr><td>' + escapeHtml(r.name) + '</td><td>' + escapeHtml(r.host_id ? hostName(r.host_id) : 'ทุก host') + '</td><td>' + escapeHtml(r.metric) + '</td><td>' + escapeHtml(r.op) + ' ' + escapeHtml(r.threshold) + '</td>' +
              '<td class="actions"><button class="btn" data-edit="' + r.id + '">แก้</button> <button class="btn danger" data-del="' + r.id + '">ลบ</button></td></tr>').join('') +
            '</tbody></table>';
          body.querySelectorAll('[data-edit]').forEach((btn) => {
            btn.onclick = () => {
              const r = rulesF.find((x) => x.id == btn.dataset.edit);
              if (r) fillRuleForm(r);
            };
          });
          body.querySelectorAll('[data-del]').forEach((btn) => {
            btn.onclick = () => deleteRule(btn.dataset.del);
          });
        } else {
          if (!historyF.length) {
            body.innerHTML = '<p class="empty-note">ยังไม่มีประวัติ alert</p>';
            return;
          }
          body.innerHTML = '<table><thead><tr><th>เวลา</th><th>Host</th><th>Metric</th><th>ค่า</th><th class="actions"></th></tr></thead><tbody>' +
            historyF.map((h) =>
              '<tr data-id="' + h.id + '" style="' + (h.ack ? 'opacity:.6' : '') + '">' +
              '<td>' + new Date(h.created_at * 1000).toLocaleString('th-TH') + '</td>' +
              '<td>' + escapeHtml(hostName(h.host_id)) + '</td><td>' + escapeHtml(h.metric) + '</td>' +
              '<td>' + escapeHtml(h.value) + ' (เกิน ' + escapeHtml(h.threshold) + ')</td>' +
              '<td class="actions">' + (h.ack ? '<span class="badge online">ack ✓</span>' : '<button class="btn" data-ack="' + h.id + '">ack</button>') + '</td>' +
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
      tabRules.onclick = () => { tabRules.classList.add('active'); tabHistory.classList.remove('active'); loadAlerts(); };
      tabHistory.onclick = () => { tabHistory.classList.add('active'); tabRules.classList.remove('active'); loadAlerts(); };
      filt.onchange = () => render();   // กรองตาม host ที่เลือก (ไม่ต้อง reload)
      render();
    } catch (e) { toast('error', e.message); }
  }

  async function loadSettings() {
    try {
      const [tokens, status, audit] = await Promise.all([
        api('/api/v1/auth/tokens'),
        api('/api/status'),
        api('/api/v1/auth/audit'),
      ]);
      renderServerInfo(status);
      renderAudit(audit);
      const tbody = document.getElementById('tokenTable');
      if (!tokens.length) {
        tbody.innerHTML = '<tr><td colspan="3" style="color:var(--text-2)">ยังไม่มี host/token</td></tr>';
      } else {
        tbody.innerHTML = tokens.map((t) =>
          '<tr><td>' + t.host_id + '</td><td><code>' + (t.token || '—') + '</code></td>' +
          '<td class="actions"><button class="btn danger" data-revoke="' + t.host_id + '">revoke</button></td></tr>'
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
      await loadNotifiers();
    } catch (e) { toast('error', e.message); }
  }

  // ── การแจ้งเตือน (Webhook / Telegram) — ตั้งค่าผ่าน UI, เก็บใน DB ──

  function renderAudit(list) {
    const tbody = document.getElementById('auditTable');
    if (!tbody) return;
    if (!list || !list.length) {
      tbody.innerHTML = '<tr><td colspan="4" style="color:var(--text-2)">ยังไม่มีประวัติ</td></tr>';
      return;
    }
    const actionLabel = {
      'login.ok': 'เข้าสู่ระบบ',
      'login.fail': 'เข้าสู่ระบบ (ล้มเหลว)',
      'login.blocked': 'ถูกจำกัดอัตรา',
    };
    const rows = list.map((e) => {
      const tr = document.createElement('tr');
      const d = new Date((e.ts || 0) * 1000).toLocaleString('th-TH');
      [d, actionLabel[e.action] || e.action, e.ip || '—', e.ok ? 'สำเร็จ' : 'ล้มเหลว'].forEach((t) => {
        const td = document.createElement('td');
        td.textContent = t;
        tr.appendChild(td);
      });
      return tr;
    });
    tbody.replaceChildren(...rows);
  }

  async function loadNotifiers() {
    try {
      const data = await api('/api/v1/settings/notifiers');
      renderNotifierState(data);
      wireNotifierHandlers(data);
      maybeShowWizard(data);
    } catch (e) { toast('error', e.message); }
  }

  function renderNotifierState(d) {
    const setBadge = (id, text, cls) => {
      const b = document.getElementById(id);
      if (b) { b.textContent = text; b.className = 'badge' + (cls ? ' ' + cls : ''); }
    };
    const wh = d.webhook || {};
    const tg = d.telegram || {};
    if (wh.configured) setBadge('webhookBadge', wh.enabled ? 'พร้อมใช้งาน' : 'ปิดใช้งาน', wh.enabled ? 'online' : 'offline');
    else setBadge('webhookBadge', 'ยังไม่ได้ตั้งค่า', 'warn');
    if (tg.configured) setBadge('telegramBadge', tg.enabled ? 'พร้อมใช้งาน' : 'ปิดใช้งาน', tg.enabled ? 'online' : 'offline');
    else setBadge('telegramBadge', 'ยังไม่ได้ตั้งค่า', 'warn');

    const url = document.getElementById('webhookUrl');
    if (url && url.value !== (wh.url || '')) url.value = wh.url || '';
    const en = document.getElementById('webhookEnabled');
    if (en) en.checked = !!wh.enabled;  // ไม่ติ๊ก = ปิด (ไม่เลือกเอง = ไม่เปิดให้)
    const tok = document.getElementById('telegramToken');
    if (tok && tok.value !== (tg.bot_token || '')) tok.value = tg.bot_token || '';
    const chat = document.getElementById('telegramChat');
    if (chat && chat.value !== (tg.chat_id || '')) chat.value = tg.chat_id || '';
    const te = document.getElementById('telegramEnabled');
    if (te) te.checked = !!tg.enabled;  // ไม่ติ๊ก = ปิด (ไม่เลือกเอง = ไม่เปิดให้)
    updateRuleFormHints(wh.configured, tg.configured);
  }

  function updateRuleFormHints(whOk, tgOk) {
    const hint = (id, ok) => {
      const cb = document.getElementById(id);
      const lab = cb && cb.closest('label');
      if (!lab) return;
      lab.querySelectorAll('small.ch').forEach((s) => s.remove());
      if (!ok) {
        const s = document.createElement('small');
        s.className = 'ch';
        s.textContent = ' (ยังไม่ได้ตั้งค่า)';
        lab.appendChild(s);
      }
    };
    hint('ruleNotifyWebhook', whOk);
    hint('ruleNotifyTelegram', tgOk);
  }

  function wireNotifierHandlers() {
    if (document.getElementById('webhookSaveBtn').onclick) return;  // wire ครั้งเดียว (DOM คงเดิม)
    document.getElementById('webhookSaveBtn').onclick = saveChannel('webhook');
    document.getElementById('webhookTestBtn').onclick = testWebhook;
    document.getElementById('telegramSaveBtn').onclick = saveChannel('telegram');
    document.getElementById('telegramTestBtn').onclick = testTelegram;
    document.getElementById('telegramChatScanBtn').onclick = scanChatId;
    const eye = document.getElementById('telegramTokenEye');
    eye.onclick = () => {
      const inp = document.getElementById('telegramToken');
      const show = inp.type === 'password';
      inp.type = show ? 'text' : 'password';
      eye.textContent = show ? 'ซ่อน' : 'แสดง';
    };
    document.getElementById('tgHelpToggle').onclick = () => {
      const h = document.getElementById('tgHelp');
      h.style.display = h.style.display === 'none' ? 'block' : 'none';
    };
    document.getElementById('changePassBtn').onclick = changePassword;
    document.querySelectorAll('#notifWizard .wiz-opt').forEach((b) => {
      b.onclick = () => focusChannel(b.dataset.wiz);
    });
    document.getElementById('wizClose').onclick = () => hideWizard();
  }

  function collectChannel(ch) {
    if (ch === 'webhook') {
      return {
        url: document.getElementById('webhookUrl').value.trim(),
        enabled: document.getElementById('webhookEnabled').checked,
      };
    }
    return {
      bot_token: document.getElementById('telegramToken').value.trim(),
      chat_id: document.getElementById('telegramChat').value.trim(),
      enabled: document.getElementById('telegramEnabled').checked,
    };
  }

  function saveChannel(ch) {
    return async () => {
      const body = {};
      body[ch] = collectChannel(ch);
      try {
        const data = await api('/api/v1/settings/notifiers', {
          method: 'PUT',
          body: JSON.stringify(body),
        });
        renderNotifierState(data);
        const saved = data[ch] || {};
        if (saved.configured && !saved.enabled) {
          toast('info', 'บันทึกแล้ว — ช่องนี้ปิดใช้งาน (ติ๊ก "เปิดใช้งาน" เพื่อเปิด)');
        } else {
          toast('success', I18N.saved);
        }
      } catch (e) { toast('error', e.message); }
    };
  }

  function showResult(el, ok, text) {
    const r = document.getElementById(el);
    if (r) {
      r.textContent = text;
      r.className = 'notif-result' + (ok === null ? '' : (ok ? ' result-ok' : ' result-err'));
    }
  }

  async function testWebhook() {
    const url = document.getElementById('webhookUrl').value.trim();
    if (!url) { toast('error', 'กรอก Webhook URL ก่อน'); return; }
    showResult('webhookResult', null, 'กำลังทดสอบ…');
    try {
      const r = await api('/api/v1/settings/notifiers/webhook/test', {
        method: 'POST',
        body: JSON.stringify({ url }),
      });
      showResult(
        'webhookResult',
        r.ok,
        r.ok ? ('OK (' + r.status + ') — ' + (r.detail || '')) : ('ล้มเหลว (' + (r.status || '-') + ') ' + (r.detail || ''))
      );
    } catch (e) { showResult('webhookResult', false, e.message); }
  }

  async function testTelegram() {
    const bot_token = document.getElementById('telegramToken').value.trim();
    const chat_id = document.getElementById('telegramChat').value.trim();
    if (!bot_token || !chat_id) { toast('error', 'กรอก Bot Token และ Chat ID ก่อน'); return; }
    showResult('telegramResult', null, 'กำลังส่ง…');
    try {
      const r = await api('/api/v1/settings/notifiers/telegram/test', {
        method: 'POST',
        body: JSON.stringify({ bot_token, chat_id }),
      });
      showResult('telegramResult', r.ok, r.ok ? 'ส่งข้อความทดสอบแล้ว' : (r.detail || 'ล้มเหลว'));
    } catch (e) { showResult('telegramResult', false, e.message); }
  }

  async function scanChatId() {
    const bot_token = document.getElementById('telegramToken').value.trim();
    if (!bot_token) { toast('error', 'กรอก Bot Token ก่อน'); return; }
    showResult('telegramResult', null, 'กำลังดึง Chat ID…');
    try {
      const r = await api('/api/v1/settings/notifiers/telegram/chatid', {
        method: 'POST',
        body: JSON.stringify({ bot_token }),
      });
      if (r.ok && r.chat_id) {
        document.getElementById('telegramChat').value = r.chat_id;
        showResult('telegramResult', true, 'ได้ Chat ID: ' + r.chat_id);
      } else {
        showResult('telegramResult', false, r.detail || 'ยังไม่พบ chat — แชทกับบอท (กด Start) ก่อน แล้วลองอีกครั้ง');
      }
    } catch (e) { showResult('telegramResult', false, e.message); }
  }

  function maybeShowWizard(d) {
    const bothUnset = !(d.webhook || {}).configured && !(d.telegram || {}).configured;
    const done = sessionStorage.getItem('notifWizDone') === '1';
    if (bothUnset && !done) showWizard();
  }

  function showWizard() { document.getElementById('notifWizard').classList.add('show'); }
  function hideWizard() {
    document.getElementById('notifWizard').classList.remove('show');
    sessionStorage.setItem('notifWizDone', '1');
  }

  function focusChannel(ch) {
    hideWizard();
    const card = document.getElementById(ch + 'Card');
    if (!card) return;
    card.scrollIntoView({ behavior: 'smooth', block: 'center' });
    card.classList.remove('flash');
    void card.offsetWidth;  // รีสตาร์ท animation ให้ flash ซ้ำได้
    card.classList.add('flash');
    const first = card.querySelector('input');
    if (first) setTimeout(() => first.focus(), 350);
  }

  async function changePassword() {
    const oldP = document.getElementById('oldPassword').value;
    const newP = document.getElementById('newPassword').value;
    const conf = document.getElementById('confirmPassword').value;
    const res = document.getElementById('changePassResult');
    if (!oldP || !newP) { showResult('changePassResult', false, 'กรอกให้ครบทั้งสองช่อง'); return; }
    if (newP !== conf) { showResult('changePassResult', false, 'รหัสผ่านใหม่กับยืนยันไม่ตรง'); return; }
    try {
      await api('/api/v1/auth/password', {
        method: 'POST',
        body: JSON.stringify({ old_password: oldP, new_password: newP, confirm_password: conf }),
      });
      showResult('changePassResult', true, 'เปลี่ยนรหัสผ่านแล้ว (มีผลทันที)');
      document.getElementById('oldPassword').value = '';
      document.getElementById('newPassword').value = '';
      document.getElementById('confirmPassword').value = '';
      toast('success', I18N.saved);
    } catch (e) { showResult('changePassResult', false, e.message); }
  }

  window.AlertsView = { loadAlerts, loadSettings };
})();
