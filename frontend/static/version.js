fetch('/static/version.txt')
  .then(r => r.text())
  .then(v => {
    const sha = v.trim();
    document.querySelectorAll('.version-badge').forEach(el => {
      el.textContent = sha;
      el.title = 'Build: ' + sha;
    });
  })
  .catch(() => {});
