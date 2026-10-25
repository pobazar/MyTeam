function bindForms() {
  window.bindActivityFeedback(document);
  document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', async event => {
      if (form.method.toLowerCase() !== 'post') return;
      event.preventDefault();
      if (form.classList.contains('busy') || !form.checkValidity()) return;
      const data = new FormData(form);
      form.classList.add('busy'); form.setAttribute('aria-busy', 'true');
      form.querySelectorAll('button[type="submit"]').forEach(button => { button.disabled = true; });
      try {
        const response = await fetch(form.action || location.href, {method: 'POST', body: data, credentials: 'same-origin'});
        if (!response.ok) throw new Error('request failed');
        const html = await response.text();
        const page = new DOMParser().parseFromString(html, 'text/html');
        document.title = page.title;
        document.body.replaceWith(page.body);
        history.replaceState(null, '', response.url);
        bindForms();
        pollLogin();
        const status = document.querySelector('[role="status"], .errorlist');
        if (status) { status.setAttribute('tabindex', '-1'); status.focus(); }
      } catch (error) {
        let notice = form.querySelector('[data-network-error]');
        if (!notice) {
          notice = document.createElement('p'); notice.dataset.networkError = '';
          notice.className = 'notice error'; notice.setAttribute('role', 'alert'); form.prepend(notice);
        }
        notice.textContent = 'Не удалось сохранить. Введённое осталось на месте — попробуйте ещё раз.';
        form.classList.remove('busy'); form.removeAttribute('aria-busy');
        form.querySelectorAll('button').forEach(button => { button.disabled = false; });
      }
    });
  });
}
bindForms();

let loginTimer;
let loginPending=false;
async function pollLogin() {
  clearTimeout(loginTimer);
  const form=document.querySelector('[data-login-poll]');
  if (!form || loginPending) return;
  loginPending=true;
  try {
    const response=await fetch(form.dataset.loginPoll,{method:'POST',body:new FormData(form),credentials:'same-origin'});
    if(response.ok){
      const result=await response.json();
      if(result.authenticated){location.assign('/');return;}
      if(result.expired){document.querySelector('[data-login-status]').textContent='Срок кода закончился. Получи новый код.';document.querySelector('[data-login-expired]').hidden=false;return;}
    }
  } catch (_) { /* Retain the code and retry without replacing the page. */ }
  finally { loginPending=false; }
  loginTimer=setTimeout(pollLogin,2000);
}
pollLogin();
window.addEventListener('focus',pollLogin);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)pollLogin();});
