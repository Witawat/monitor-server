// format.js — format ตัวเลข/หน่วย รวมกันที่เดียว (WEBUI_DESIGN.md §4.2)
// ห้ามแต่ละหน้าเขียน format เอง — ใช้ helper เหล่านี้ร่วมกัน.

function isEmpty(v) { return v === undefined || v === null || v === '' || Number.isNaN(v); }

function formatPercent(v) {
  if (isEmpty(v)) return '—';
  return v.toFixed(1) + '%';
}

function formatBytes(v) {
  if (isEmpty(v)) return '—';
  if (v === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  let u = 0;
  let n = v;
  while (n >= 1024 && u < units.length - 1) { n /= 1024; u++; }
  const digits = u === 0 ? 0 : 2;
  return n.toFixed(digits) + ' ' + units[u];
}

function formatRate(v) {
  if (isEmpty(v)) return '—';
  return formatBytes(v) + '/s';
}

function formatInt(v) {
  if (isEmpty(v)) return '—';
  return Math.round(v).toLocaleString('en-US');
}

function formatUptime(sec) {
  if (isEmpty(sec)) return '—';
  sec = Math.floor(sec);
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (d > 0) return d + 'd ' + h + 'h';
  if (h > 0) return h + 'h ' + m + 'm';
  if (m > 0) return m + 'm';
  return sec + 's';
}
