// scale.js — ขยายทั้งกรอบ UI ด้วย CSS zoom (WEBUI_DESIGN.md §3)
(function () {
  const DESIGN_WIDTH = 1280;
  function setScale() {
    const scale = Math.min(1.4, Math.max(0.6, window.innerWidth / DESIGN_WIDTH));
    document.documentElement.style.setProperty('--ui-scale', scale);
  }
  window.addEventListener('resize', setScale);
  setScale();
})();
