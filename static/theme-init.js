// Pre-hydration theme: apply the remembered choice (else OS preference) BEFORE first paint
// so a dark-mode visitor never gets a white flash before React loads. Kept as a same-origin
// file (not inline) so the Content-Security-Policy can use a strict script-src 'self'.
(function () {
  try {
    var s = localStorage.getItem('paksh-theme');
    var d = s === 'dark' || (s !== 'light' && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
    if (d) {
      document.documentElement.classList.add('dark');
      document.documentElement.style.background = '#1A1917';
      var m = document.querySelector('meta[name=theme-color]');
      if (m) m.setAttribute('content', '#1A1917');
    }
  } catch (e) {}
})();
