// login.js — ฝั่ง logic ฟอร์มเข้าสู่ระบบ (แยกจาก inline script ให้ผ่าน CSP script-src 'self')
(function () {
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
          username: document.getElementById('username').value,
          password: document.getElementById('password').value,
        }),
      });
      if (res.ok) { location.href = '/#/fleet'; }
      else { err.textContent = 'username หรือ password ไม่ถูกต้อง'; }
    } catch (ex) {
      err.textContent = 'เชื่อมต่อ server ไม่ได้';
    } finally { btn.disabled = false; }
  });
})();
