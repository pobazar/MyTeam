/* Static GitHub Pages client. Only a browser session token is stored here, never server keys. */
(() => {
  const root=document.querySelector('#app');
  if(window.top!==window.self){root.textContent='Откройте МАЙТИМ в отдельной вкладке.';return;}
  const api=document.querySelector('meta[name="myteam-api"]').content.replace(/\/$/,'');
  const storage='myteam.session';
  let token=sessionStorage.getItem(storage), timer, polling=false, navigation=0;
  function message(text){
    let box=root.querySelector('[data-network-error]');
    if(!box){box=document.createElement('p');box.className='notice error';box.dataset.networkError='';box.setAttribute('role','alert');(root.querySelector('main')||root).prepend(box);}
    box.textContent=text;
  }
  async function bootstrap(){
    const response=await fetch(api+'/bridge/bootstrap/',{credentials:'omit',cache:'no-store'});
    if(!response.ok)throw new Error('bootstrap');
    token=(await response.json()).session;sessionStorage.setItem(storage,token);
  }
  async function request(path,options={}){
    if(!token)await bootstrap();
    const headers=new Headers(options.headers||{});headers.set('Authorization','Bearer '+token);
    const response=await fetch(api+path,{...options,headers,credentials:'omit',cache:'no-store'});
    const next=response.headers.get('X-Myteam-Session');
    if(next){token=next;sessionStorage.setItem(storage,token);}
    if(response.status===401){token=null;sessionStorage.removeItem(storage);throw new Error('session');}
    return response;
  }
  function route(){const value=location.hash.slice(1)||'/';return value.startsWith('/')&&!value.startsWith('//')?value:'/';}
  function go(path){if(route()===path)load(path);else location.hash=path;}
  function render(html,url){
    const doc=new DOMParser().parseFromString(html,'text/html');
    document.title=doc.title||'МАЙТИМ';root.replaceChildren(...doc.body.childNodes);
    const path=new URL(url).pathname;
    history.replaceState(null,'',location.pathname+location.search+'#'+path);
    bind();poll();
    const status=root.querySelector('[role="status"],.errorlist');
    if(status&&!root.querySelector('[data-login-poll]')){status.tabIndex=-1;status.focus();}
  }
  async function load(path){
    clearTimeout(timer);const own=++navigation;
    try{
      const response=await request(path);
      if(!response.ok)throw new Error('server');
      const html=await response.text();if(own===navigation)render(html,response.url);
    }catch(error){
      if(own!==navigation)return;
      if(error.message==='session'){go('/login/');return;}
      message('Не удалось загрузить страницу. Попробуйте ещё раз чуть позже.');
      let retry=root.querySelector('[data-retry]');
      if(!retry){retry=document.createElement('button');retry.type='button';retry.dataset.retry='';retry.textContent='Попробовать снова';retry.onclick=()=>load(route());(root.querySelector('main')||root).append(retry);}
    }
  }
  function bind(){
    window.bindActivityFeedback(root);
    root.querySelectorAll('a[href]').forEach(link=>{
      const url=new URL(link.getAttribute('href'),api+'/');
      if(url.origin!==new URL(api).origin)return;
      link.href='#'+url.pathname+url.search;
      link.addEventListener('click',event=>{if(event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey)return;event.preventDefault();go(url.pathname+url.search);});
    });
    root.querySelectorAll('form').forEach(form=>{
      if(form.hasAttribute('data-login-poll'))return;
      form.addEventListener('submit',async event=>{
        event.preventDefault();if(form.classList.contains('busy')||!form.checkValidity())return;
        const data=new FormData(form), action=new URL(form.getAttribute('action')||route(),api+'/');
        if(action.origin!==new URL(api).origin)return;
        form.classList.add('busy');form.setAttribute('aria-busy','true');
        form.querySelectorAll('button').forEach(button=>button.disabled=true);
        try{
          const response=await request(action.pathname+action.search,{method:'POST',body:data});
          if(!response.ok)throw new Error('server');
          render(await response.text(),response.url);
        }catch(error){
          if(error.message==='session'){go('/login/');return;}
          message('Не удалось сохранить. Введённое осталось на месте — попробуйте ещё раз.');
          form.classList.remove('busy');form.removeAttribute('aria-busy');form.querySelectorAll('button').forEach(button=>button.disabled=false);
        }
      });
    });
  }
  async function poll(){
    clearTimeout(timer);const form=root.querySelector('[data-login-poll]');
    if(!form||polling)return;
    polling=true;
    try{
      const response=await request(form.dataset.loginPoll,{method:'POST',body:new FormData(form)});
      if(response.ok){
        const result=await response.json();
        if(result.authenticated){go('/');return;}
        if(result.expired){root.querySelector('[data-login-status]').textContent='Срок кода закончился. Получи новый код.';root.querySelector('[data-login-expired]').hidden=false;return;}
      }
    }catch(error){if(error.message==='session'){go('/login/');return;}}
    finally{polling=false;}
    if(root.contains(form))timer=setTimeout(poll,2000);
  }
  window.addEventListener('hashchange',()=>load(route()));
  window.addEventListener('focus',poll);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll();});
  load(route());
})();
