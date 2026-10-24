document.querySelectorAll('form').forEach(form => {
  form.addEventListener('submit', event => {
    if (form.classList.contains('busy')) { event.preventDefault(); return; }
    if (!form.checkValidity()) return;
    form.classList.add('busy');
    form.setAttribute('aria-busy', 'true');
    form.querySelectorAll('button[type="submit"]').forEach(button => { button.disabled = true; });
  });
});
window.addEventListener('pageshow', () => {
  document.querySelectorAll('form.busy').forEach(form => {
    form.classList.remove('busy'); form.removeAttribute('aria-busy');
    form.querySelectorAll('button').forEach(button => { button.disabled = false; });
  });
});
