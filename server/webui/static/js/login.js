// login.js — ฝั่ง logic ฟอร์มเข้าสู่ระบบ (แยกจาก inline script ให้ผ่าน CSP script-src 'self')
(function () {
  const username = document.getElementById('username');
  const password = document.getElementById('password');

  // ครั้งแรกที่ exe สร้าง user/pass — auto-fill ให้เห็นเลย (จาก /api/v1/auth/setup)
  async function tryAutoFill() {
    try {
      const res = await fetch('/api/v1/auth/setup');
      if (!res.ok) return;
      const data = await res.json();
      username.value = data.user || '';
      password.value = data.pass || '';
      const hint = document.getElementById('setupHint');
      if (hint) hint.style.display = 'block';
    } catch (e) { /* ไม่เป็นไร — ไม่มีวิธี setup */ }
  }
  tryAutoFill();

  document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('loginBtn');
    const err = document.getElementById('loginError');
    btn.disabled = true;
    err.textContent = '';
    try {
      const res = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: username.value,
          password: password.value,
        }),
      });
      if (res.ok) {
        // ไป hash fleet แล้ว reload ใหม่ — บังคับ server ส่ง base.html (SPA) เพราะ hash เปลี่ยนไม่ทำให้หน้าใหม่
        window.location.hash = '#/fleet';
        window.location.reload();
      }
      else {
        // แสดง message จาก detail (429 / 401) ตรง ๆ
        try {
          const data = await res.json();
          err.textContent = (data && data.detail) ? data.detail : 'username หรือ password ไม่ถูกต้อง';
        } catch (ex) {
          err.textContent = 'username หรือ password ไม่ถูกต้อง';
        }
      }
    } catch (ex) {
      err.textContent = 'เชื่อมต่อ server ไม่ได้';
    } finally { btn.disabled = false; }
  });
})();
