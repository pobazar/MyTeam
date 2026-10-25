/* Pages owns the complete UI. The backend supplies JSON and enforces all permissions. */
(() => {
  const api=document.querySelector('meta[name="myteam-api"]').content.replace(/\/$/,'');
  const root=document.querySelector('#app'),main=document.querySelector('#main'),nav=document.querySelector('#account-nav');
  const panel=document.querySelector('#panel'),panelBody=document.querySelector('#panel-content'),panelTitle=document.querySelector('#panel-title');
  const storage='myteam.session',hint='myteam.authenticated',stageHint='myteam.stage';
  let token=sessionStorage.getItem(storage),csrf=null,phase='intro',authenticated=Boolean(token&&sessionStorage.getItem(hint)!=='false');
  let authVersion=0,mainVersion=0,panelVersion=0,loginVersion=0,introStep=0,mainReady=false;
  let mainAbort,panelAbort,loginAbort,pollTimer,polling=false,closeTarget='/',introAuthenticated=false;
  let intendedRoute=/^\/(profile|history)\/$|^\/meetings\/[a-f0-9-]{36}\/feedback\/(?:\?from=history)?$/i.test(location.hash.slice(1))?location.hash.slice(1):'/';
  if(window.top!==window.self){main.textContent='Откройте МАЙТИМ в отдельной вкладке.';return;}
  const steps=[
    ['Знакомься с коллегами','МАЙТИМ помогает узнавать людей за пределами своей команды — через разговоры, игры и встречи по интересам.'],
    ['Участвуй, когда хочется','Каждую неделю — возможность пообщаться с коллегами. Участие добровольное: на каждую неделю ты записываешься сам, мы не продлеваем запись автоматически.'],
    ['Выбери ближайшую активность','Посмотри, что запланировано, и запишись, если хочешь участвовать. Мы пришлём в Telegram участников и всё необходимое для активности.'],
  ];
  const $=(node,selector)=>node.querySelector(selector);
  function clone(id){return document.querySelector('#tpl-'+id).content.cloneNode(true);}
  function put(node,selector,value){$(node,selector).textContent=value??'';}
  function element(tag,text,className){const node=document.createElement(tag);node.textContent=text;if(className)node.className=className;return node;}
  const day=value=>new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',timeZone:'Europe/Moscow'}).format(new Date(value));
  const dates=(a,b)=>day(a)+' — '+day(b);
  const stars=value=>'★'.repeat(value)+'☆'.repeat(5-value);
  function telegramLink(link,value){try{const url=new URL(value);if(url.protocol!=='https:'||url.hostname!=='t.me')throw Error();link.href=url.href;return true;}catch{link.hidden=true;return false;}}
  class ApiError extends Error{constructor(code,status=0,data={}){super(code);this.code=code;this.status=status;this.data=data;}}
  async function request(path,{method='GET',data,signal}={}){
    const version=authVersion,controller=new AbortController();let timedOut=false;
    const abort=()=>controller.abort();if(signal?.aborted)abort();else signal?.addEventListener('abort',abort,{once:true});
    const timeout=setTimeout(()=>{timedOut=true;controller.abort();},20000);
    const headers={Accept:'application/json'};
    if(token)headers.Authorization='Bearer '+token;
    if(method!=='GET'){headers['Content-Type']='application/json';if(csrf)headers['X-CSRFToken']=csrf;}
    try{
      const response=await fetch(api+path,{method,headers,body:method==='GET'?undefined:JSON.stringify(data||{}),credentials:'omit',cache:'no-store',redirect:'error',signal:controller.signal});
      if(version!==authVersion)throw new ApiError('cancelled');
      if(!response.headers.get('Content-Type')?.includes('application/json'))throw new ApiError('invalid_response',response.status);
      const body=await response.json();
      if(version!==authVersion)throw new ApiError('cancelled');
      const next=response.headers.get('X-Myteam-Session');
      if(next){token=next;sessionStorage.setItem(storage,next);}
      if(body.csrf_token)csrf=body.csrf_token;
      if(!response.ok&&!body.state)throw new ApiError(body.error||'server_error',response.status,body);
      return body;
    }catch(error){
      if(signal?.aborted||version!==authVersion)throw new ApiError('cancelled');
      if(error instanceof ApiError)throw error;
      throw new ApiError(timedOut?'timeout':'network');
    }finally{clearTimeout(timeout);signal?.removeEventListener('abort',abort);}
  }
  function resetCredentials(){authVersion++;token=null;csrf=null;authenticated=false;sessionStorage.removeItem(storage);sessionStorage.removeItem(hint);sessionStorage.removeItem(stageHint);}
  function hash(path){history.replaceState(null,'',location.pathname+location.search+'#'+path);}
  function route(){const path=location.hash.slice(1)||'/';return path.startsWith('/')&&!path.startsWith('//')?path:'/';}
  function go(path){if(route()===path)routeChanged();else location.hash=path;}
  function closePanel(){panelVersion++;panelAbort?.abort();if(panel.open)panel.close();panelBody.replaceChildren();}
  function stopLogin(){loginVersion++;clearTimeout(pollTimer);loginAbort?.abort();polling=false;}
  function clearViews(){mainVersion++;mainAbort?.abort();stopLogin();closePanel();mainReady=false;}
  function showIntro(step=0,alreadyAuthenticated=false){
    clearViews();phase='intro';introStep=step;introAuthenticated=alreadyAuthenticated;nav.hidden=true;hash('/');
    const fragment=clone('intro');put(fragment,'[data-step]',`Знакомство · ${step+1} из 3`);put(fragment,'[data-heading]',steps[step][0]);put(fragment,'[data-body]',steps[step][1]);
    const button=$(fragment,'[data-intro-next]');button.textContent=step===2?(alreadyAuthenticated?'Продолжить':'Войти через Telegram'):'Дальше';
    button.onclick=()=>step<2?showIntro(step+1,alreadyAuthenticated):startLogin(alreadyAuthenticated);
    main.replaceChildren(fragment);
  }
  function fail(target,retry,message){const fragment=clone('error');if(message)put(fragment,'[role="alert"]',message);$(fragment,'[data-retry]').onclick=retry;target.replaceChildren(fragment);}
  function loading(target){target.replaceChildren(clone('loading'));}
  function sessionLost(){resetCredentials();showIntro(0);}
  function acceptAccount(body){
    if(body.state==='needs_onboarding'){sessionStorage.setItem(stageHint,'needs_onboarding');authenticated=true;sessionStorage.setItem(hint,'true');showIntro(0,true);return false;}
    if(body.state==='needs_profile'){
      sessionStorage.setItem(stageHint,'needs_profile');authenticated=true;sessionStorage.setItem(hint,'true');
      if(phase!=='setup')showSetup(body);
      return false;
    }
    sessionStorage.setItem(stageHint,'authenticated');return true;
  }
  function catchLoad(error,target,retry){if(error.code==='cancelled')return;if(error.status===401){sessionLost();return;}fail(target,retry);}
  async function bootstrap(signal){
    const body=await request('/bridge/bootstrap/',{signal});token=body.session;sessionStorage.setItem(storage,token);sessionStorage.setItem(hint,'false');
  }
  async function startLogin(alreadyAuthenticated=false){
    stopLogin();phase='login';nav.hidden=true;closePanel();const fragment=clone('login');$(fragment,'[data-back-intro]').onclick=()=>showIntro(0,alreadyAuthenticated);main.replaceChildren(fragment);
    const target=$(main,'[data-login-content]');loading(target);const version=loginVersion;
    loginAbort=new AbortController();
    try{
      if(alreadyAuthenticated){if(!csrf)await request('/api/activities/',{signal:loginAbort.signal});const body=await request('/api/onboarding/',{method:'POST',signal:loginAbort.signal});if(version===loginVersion)enterAccount(body);return;}
      if(!token)await bootstrap(loginAbort.signal);
      let body;
      try{body=await request('/api/login/',{method:'POST',signal:loginAbort.signal});}
      catch(error){if(error.status!==401)throw error;resetCredentials();await bootstrap(loginAbort.signal);body=await request('/api/login/',{method:'POST',signal:loginAbort.signal});}
      if(version!==loginVersion)return;
      if(body.state){enterAccount(body);return;}
      const card=clone('code');put(card,'[data-code]',body.code);
      if(!telegramLink($(card,'[data-bot]'),body.bot_url))put(card,'[data-login-status]','Вход пока недоступен. Попробуй ещё раз позже.');
      $(card,'[data-new-code]').onclick=()=>startLogin();target.replaceChildren(card);pollLogin(version);
    }catch(error){if(version===loginVersion)catchLoad(error,target,()=>startLogin(alreadyAuthenticated));}
  }
  async function pollLogin(version=loginVersion){
    clearTimeout(pollTimer);if(phase!=='login'||polling||!main.querySelector('[data-code]'))return;
    polling=true;
    try{
      const body=await request('/api/login/status/',{method:'POST',signal:loginAbort.signal});
      if(version!==loginVersion)return;
      if(body.state!=='waiting'){enterAccount(body);return;}
      if(body.expired){put(main,'[data-login-status]','Срок кода закончился. Получи новый код.');$(main,'[data-new-code]').hidden=false;return;}
    }catch(error){if(version!==loginVersion||error.code==='cancelled')return;if(error.status===401){sessionLost();return;}put(main,'[data-login-status]','Не удалось проверить вход. Повторяем попытку…');}
    finally{polling=false;}
    if(version===loginVersion&&phase==='login')pollTimer=setTimeout(()=>pollLogin(version),2000);
  }
  function enterAccount(body){authenticated=true;sessionStorage.setItem(hint,'true');stopLogin();if(!acceptAccount(body))return;showApp();hash(intendedRoute);intendedRoute='/';loadActivities();routeChanged();}
  function showApp(){phase='app';nav.hidden=false;main.replaceChildren(clone('activities'));mainReady=false;}
  function showSetup(body){clearViews();phase='setup';nav.hidden=true;hash('/');main.replaceChildren(element('h1','Давайте познакомимся'),element('p','Заполни три поля, чтобы перейти к активностям.','muted'));const target=element('div','', 'setup');main.append(target);renderProfile(target,body,true);}
  async function loadSetup(){
    clearViews();phase='setup-loading';nav.hidden=true;hash('/');main.replaceChildren(element('h1','Давайте познакомимся'));
    const target=element('div','', 'setup');main.append(target);loading(target);const version=++mainVersion;mainAbort=new AbortController();
    try{const body=await request('/api/profile/',{signal:mainAbort.signal});if(version!==mainVersion)return;if(!acceptAccount(body))return;enterAccount(body);}
    catch(error){if(version===mainVersion)catchLoad(error,target,loadSetup);}
  }
  async function loadActivities(){
    if(!authenticated)return;
    if(phase!=='app')showApp();
    const target=$(main,'#activity-content');if(!target)return;
    const version=++mainVersion;mainAbort?.abort();mainAbort=new AbortController();mainReady=false;
    const shell=clone('activities');target.replaceChildren(...$(shell,'#activity-content').childNodes);
    try{const body=await request('/api/activities/',{signal:mainAbort.signal});if(version!==mainVersion)return;if(!acceptAccount(body))return;renderActivities(target,body);mainReady=true;}
    catch(error){if(version===mainVersion)catchLoad(error,target,loadActivities);}
  }
  function renderActivities(target,data){
    const fragment=clone('weeks'),current=data.current,next=data.next,body=$(fragment,'[data-current-body]');
    put(fragment,'[data-current-dates]',dates(current.starts_at,current.ends_at));put(fragment,'[data-next-dates]',dates(next.starts_at,next.ends_at));
    if(current.kind==='active'){
      const active=clone('active');put(active,'[data-title]',current.activity_title);put(active,'[data-instructions]',current.instructions);
      const list=$(active,'[data-participants]');
      current.participants.forEach(person=>{const item=document.createElement('li');item.append(element('strong',person.name),element('span',person.team+' · '+person.city,'muted'));list.append(item);});
      telegramLink($(active,'[data-contacts]'),current.contacts_url);$(active,'[data-feedback]').onclick=()=>go('/meetings/'+current.meeting_id+'/feedback/');body.append(active);
    }else if(current.kind==='completed'){
      const yes=current.answer.outcome==='yes';body.append(element('h2',yes?'Спасибо за участие!':'Спасибо за ответ'),element('p',yes?current.activity_title+' — результат сохранён.':'На этой неделе не получилось провести активность. Мы сохранили твой ответ.'));
      if(yes&&current.answer.rating){const rating=element('p',stars(current.answer.rating),'stars-result');rating.setAttribute('aria-label',`Оценка ${current.answer.rating} из 5`);body.append(rating);}
      body.append(element('p','На следующей неделе будет новая возможность поучаствовать.','muted'));
    }else{
      const messages={new:['Добро пожаловать!','Ты только присоединился. Запись на текущую неделю уже завершена, поэтому активной встречи пока нет.'],skipped:['Эту неделю ты пропускаешь','На текущую неделю ты не записался. Всё в порядке — участие добровольное.'],preparing:['Ты записан на эту неделю','Готовим состав и инструкции. Они появятся здесь после публикации.'],unmatched:['В этот раз без активности','Ты записался, но участников не хватило для формирования группы.'],expired:['Активность не состоялась','На этой неделе не удалось запустить активность. Можно записаться на следующую неделю.']};
      const [title,text]=messages[current.kind]||messages.skipped;body.append(element('h2',title),element('p',text),element('p','Начни со следующей недели — запишись в соседнем блоке.','muted'));
    }
    const upcoming=$(fragment,'[data-next-body]');
    if(next.id){
      upcoming.append(element('p',next.activity_title),element('p',`Запишись до ${day(next.closes_at)}, вторника, 21:00 МСК.`,'muted'));
      if(!next.registration_open){upcoming.append(element('p','Запись закрыта.'),element('p',next.enrolled?`Ты записан. Состав появится ${day(next.starts_at)} в 09:00 МСК.`:'На этот раунд записаться уже нельзя.','muted'));}
      else if(!next.reachable){const button=element('button','Подключить сообщения для участия','secondary');button.type='button';button.onclick=()=>{logout();};upcoming.append(button);}
      else{
        if(next.enrolled)upcoming.append(element('p','Ты записан на следующую неделю.'));
        const button=element('button',next.enrolled?'Отменить запись':'Записаться','secondary');button.type='button';
        button.onclick=async()=>{button.disabled=true;try{await request('/api/rounds/'+next.id+'/enrollment/',{method:'POST',data:{action:next.enrolled?'cancel':'enroll'}});await loadActivities();}catch(error){if(error.status===401){sessionLost();return;}button.disabled=false;const notice=element('p',error.data?.message||'Не удалось сохранить запись. Попробуй ещё раз.','error');notice.setAttribute('role','alert');upcoming.append(notice);}};
        upcoming.append(button);
      }
    }else upcoming.append(element('p','Запись пока не открыта. Загляни позже.','muted'));
    target.replaceChildren(fragment);
  }
  function openPanel(title,back='/'){
    panelVersion++;panelAbort?.abort();panelAbort=new AbortController();closeTarget=back;panelTitle.textContent=title;loading(panelBody);if(!panel.open)panel.showModal();
    document.querySelector('#panel-close').setAttribute('aria-label',back==='/history/'?'Вернуться к истории':'Вернуться к активностям');
    return panelVersion;
  }
  async function loadPanel(kind){
    const version=openPanel(kind==='profile'?'Профиль':'История активностей');
    try{
      const body=await request('/api/'+kind+'/',{signal:panelAbort.signal});if(version!==panelVersion)return;if(!acceptAccount(body))return;
      if(kind==='profile')renderProfile(panelBody,body,false);else renderHistory(body.entries);
    }catch(error){if(version===panelVersion)catchLoad(error,panelBody,()=>loadPanel(kind));}
  }
  function clearErrors(form){form.querySelectorAll('[data-field-error]').forEach(node=>{node.hidden=true;node.textContent='';});form.querySelectorAll('[aria-invalid]').forEach(node=>node.removeAttribute('aria-invalid'));$(form,'[data-form-message]').replaceChildren();}
  function formError(form,error,retry){
    if(error.code==='cancelled')return;if(error.status===401){sessionLost();return;}
    if(error.data?.fields){Object.entries(error.data.fields).forEach(([name,messages])=>{const node=form.querySelector(`[data-field-error="${name}"]`);if(node){node.textContent=messages.join(' ');node.hidden=false;form.querySelector(`[name="${name}"]`)?.setAttribute('aria-invalid','true');}else{const note=element('p',messages.join(' '),'error');note.setAttribute('role','alert');$(form,'[data-form-message]').append(note);}});form.querySelector('[aria-invalid]')?.focus();return;}
    const target=$(form,'[data-form-message]');const text=element('p',error.data?.message||'Не удалось сохранить. Введённое осталось на месте.','error');text.setAttribute('role','alert');const button=element('button','Повторить','secondary');button.type='button';button.onclick=retry;target.replaceChildren(text,button);
  }
  function renderProfile(target,data,setup){
    const fragment=clone('profile');
    if(setup){$(fragment,'[data-achievements]').hidden=true;$(fragment,'.profile-grid').classList.add('setup-profile');put(fragment,'[data-profile-heading]','Немного о тебе');put(fragment,'[data-submit]','Продолжить');}
    const form=$(fragment,'[data-profile-form]');Object.entries(data.profile).forEach(([name,value])=>{if(form.elements[name])form.elements[name].value=value;});
    const awards=$(fragment,'[data-awards]');
    if(!data.achievements?.length)awards.append(element('p','После первой состоявшейся встречи здесь появится «Первый кофе».','muted'));
    else data.achievements.forEach(award=>awards.append(element('p',award.title,'badge'),element('p',award.description)));
    $(fragment,'[data-logout]').onclick=logout;
    form.onsubmit=async event=>{
      event.preventDefault();if(form.dataset.busy||!form.reportValidity())return;clearErrors(form);form.dataset.busy='true';const button=$(form,'[data-submit]'),label=button.textContent;button.disabled=true;button.textContent='Сохраняем…';const version=authVersion,view=panelVersion;
      try{
        const body=await request('/api/profile/',{method:'POST',data:Object.fromEntries(new FormData(form))});
        if(version!==authVersion||!document.contains(form))return;
        if(setup){enterAccount(body);return;}
        if(view!==panelVersion)return;const notice=element('p','Профиль сохранён.','notice');notice.setAttribute('role','status');$(form,'[data-form-message]').append(notice);
      }catch(error){if(document.contains(form))formError(form,error,()=>form.requestSubmit());}
      finally{delete form.dataset.busy;button.disabled=false;button.textContent=label;}
    };
    target.replaceChildren(fragment);
  }
  function renderHistory(entries){
    panelBody.replaceChildren();
    if(!entries.length){const card=element('section','', 'card');card.append(element('p','Здесь появятся недели, в которых ты участвовал. Пропущенные недели в историю не попадают.','muted'));panelBody.append(card);return;}
    entries.forEach(entry=>{
      const item=clone('history-item');put(item,'[data-title]',entry.activity_title);put(item,'[data-dates]',dates(entry.starts_at,entry.ends_at));const result=$(item,'[data-result]');
      if(entry.answer?.final){
        if(entry.answer.outcome==='yes'&&entry.answer.rating){const rating=element('p',stars(entry.answer.rating),'stars-result');rating.setAttribute('aria-label',`Оценка ${entry.answer.rating} из 5`);result.append(rating);}
        else result.append(element('p',entry.answer.outcome==='yes'?'Активность проведена. Ответ сохранён.':'Не получилось провести активность.'));
      }else if(entry.can_rate){const button=element('button','Оценить активность','secondary');button.type='button';button.onclick=()=>go('/meetings/'+entry.meeting_id+'/feedback/?from=history');result.append(button);}
      panelBody.append(item);
    });
  }
  async function loadFeedback(meetingId,fromHistory){
    const version=openPanel('Как прошла активность?',fromHistory?'/history/':'/');
    try{
      const data=await request('/api/meetings/'+meetingId+'/feedback/',{signal:panelAbort.signal});if(version!==panelVersion)return;if(!acceptAccount(data))return;
      const fragment=clone('feedback');put(fragment,'[data-activity]',data.activity_title+' · '+dates(data.starts_at,data.ends_at));const form=$(fragment,'form');
      if(data.readonly){form.hidden=true;const note=$(fragment,'[data-readonly]');note.hidden=false;note.textContent='Срок изменения результата закончился.'+(data.answer?.rating?` Твоя оценка: ${data.answer.rating} из 5.`:'');}
      else{
        if(data.answer){const outcome=form.querySelector(`[name="outcome"][value="${data.answer.outcome==='yes'?'yes':data.answer.outcome==='no'?'no':''}"]`);if(outcome)outcome.checked=true;const rating=form.querySelector(`[name="rating"][value="${Number(data.answer.rating)}"]`);if(rating)rating.checked=true;form.elements.comment.value=data.answer.comment||'';}
        form.onsubmit=async event=>{
          event.preventDefault();if(form.dataset.busy||!form.reportValidity())return;clearErrors(form);form.dataset.busy='true';const button=$(form,'[data-submit]');button.disabled=true;button.textContent='Сохраняем…';
          try{
            await request('/api/meetings/'+meetingId+'/feedback/',{method:'POST',data:Object.fromEntries(new FormData(form))});
            if(version!==panelVersion||!document.contains(form))return;
            loadActivities();go(fromHistory?'/history/':'/');
          }catch(error){if(version===panelVersion)formError(form,error,()=>form.requestSubmit());}
          finally{delete form.dataset.busy;button.disabled=false;button.textContent='Сохранить результат';}
        };
      }
      panelBody.replaceChildren(fragment);window.bindActivityFeedback(panelBody);
    }catch(error){if(version===panelVersion)catchLoad(error,panelBody,()=>loadFeedback(meetingId,fromHistory));}
  }
  function routeChanged(){
    if(phase!=='app'){if(phase==='intro'&&route()!=='/')showIntro(0,introAuthenticated);return;}
    const path=route();
    if(path==='/profile/'||path==='/history/'){loadPanel(path==='/profile/'?'profile':'history');return;}
    const match=path.match(/^\/meetings\/([a-f0-9-]{36})\/feedback\/(?:\?(.*))?$/i);
    if(match){loadFeedback(match[1],new URLSearchParams(match[2]||'').get('from')==='history');return;}
    closePanel();hash('/');if(!mainReady&&!mainAbort)loadActivities();
  }
  function logout(){
    const oldToken=token,oldCsrf=csrf;intendedRoute='/';clearViews();resetCredentials();showIntro(0);
    if(!oldToken)return;
    const revoke=async()=>{
      const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),15000);
      try{
        const response=await fetch(api+'/api/logout/',{method:'POST',credentials:'omit',redirect:'error',keepalive:true,signal:controller.signal,headers:{'Content-Type':'application/json',Authorization:'Bearer '+oldToken,'X-CSRFToken':oldCsrf||''},body:'{}'});
        if(!response.ok)throw Error();
        if(phase==='intro')main.querySelector('[data-auth-message]')?.replaceChildren();
      }catch{
        if(phase!=='intro')return;const target=main.querySelector('[data-auth-message]');if(!target)return;
        const note=element('p','Выход на этом устройстве выполнен. Не удалось завершить сессию на сервере.','error');note.setAttribute('role','alert');const retry=element('button','Повторить завершение выхода','secondary');retry.type='button';retry.onclick=revoke;target.replaceChildren(note,retry);
      }finally{clearTimeout(timeout);}
    };
    revoke();
  }
  nav.querySelectorAll('[data-open]').forEach(button=>button.onclick=()=>go('/'+button.dataset.open+'/'));
  document.querySelector('#panel-close').onclick=()=>go(closeTarget);
  panel.addEventListener('cancel',event=>{event.preventDefault();go(closeTarget);});
  document.querySelector('.brand').onclick=event=>{event.preventDefault();if(phase==='app')go('/');else if(phase!=='setup')showIntro(0,introAuthenticated);};
  window.addEventListener('hashchange',routeChanged);
  window.addEventListener('focus',()=>{if(phase==='login')pollLogin();});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&phase==='login')pollLogin();});
  if(authenticated){if(sessionStorage.getItem(stageHint)==='needs_profile')loadSetup();else if(sessionStorage.getItem(stageHint)==='needs_onboarding')showIntro(0,true);else{showApp();loadActivities();routeChanged();}}else showIntro(0);
})();
