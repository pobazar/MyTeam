/* Pages owns the complete UI. The backend supplies JSON and enforces all permissions. */
(() => {
  const api=document.querySelector('meta[name="myteam-api"]').content.replace(/\/$/,'');
  const root=document.querySelector('#app'),main=document.querySelector('#main'),nav=document.querySelector('#account-nav');
  const panel=document.querySelector('#panel'),panelBody=document.querySelector('#panel-content'),panelTitle=document.querySelector('#panel-title');
  const screen=document.querySelector('#screen'),screenBody=document.querySelector('#screen-content'),screenTitle=document.querySelector('#screen-title'),back=document.querySelector('#screen-back'),barTitle=document.querySelector('#appbar-title');
  const mobileOS=/Android/i.test(navigator.userAgent)?'android':(/iPhone|iPad|iPod/i.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1))?'ios':'generic';
  document.documentElement.dataset.platform=mobileOS;
  const toast=window.MyTeamToasts;
  const achievementDialog=document.querySelector('#achievement-dialog');
  const storage='myteam.session',hint='myteam.authenticated',stageHint='myteam.stage';
  let token=sessionStorage.getItem(storage),csrf=null,phase='intro',authenticated=Boolean(token&&sessionStorage.getItem(hint)!=='false');
  let authVersion=0,mainVersion=0,panelVersion=0,loginVersion=0,introStep=0,mainReady=false;
  let mainAbort,panelAbort,loginAbort,pollTimer,polling=false,closeTarget='/',introAuthenticated=false;
  let screenVersion=0,screenAbort,screenKind=null,activityScroll=0;
  let intendedRoute=/^\/(profile|history)\/$|^\/meetings\/[a-f0-9-]{36}\/feedback\/(?:\?from=history)?$/i.test(location.hash.slice(1))?location.hash.slice(1):'/';
  if(window.top!==window.self){main.textContent='Откройте МАЙТИМ в отдельной вкладке.';return;}
  const steps=[
    ['Знакомься с коллегами','МАЙТИМ помогает узнавать людей за пределами своей команды — через разговоры, игры и встречи по интересам.'],
    ['Участвуй, когда хочется','Каждую неделю — разнообразные активности, чтобы пообщаться с коллегами. Участие добровольное: ты записываешься сам, без автоматического продления.'],
    ['Всё важное — в Telegram','Мы пришлём в Telegram участников, инструкции и уведомления о ходе активности. Так ты будешь знать, что делать дальше.'],
  ];
  const $=(node,selector)=>node.querySelector(selector);
  function clone(id){return document.querySelector('#tpl-'+id).content.cloneNode(true);}
  function put(node,selector,value){$(node,selector).textContent=value??'';}
  function element(tag,text,className){const node=document.createElement(tag);node.textContent=text;if(className)node.className=className;return node;}
  const day=value=>new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',timeZone:'Europe/Moscow'}).format(new Date(value));
  const dates=(a,b)=>day(a)+' — '+day(b);
  function ratingResult(value){const fragment=clone('rating-result'),node=$(fragment,'.stars-result');node.setAttribute('aria-label',`Оценка ${value} из 5`);node.querySelectorAll('[data-rating-star]').forEach((star,index)=>star.classList.toggle('selected',index<value));return node;}
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
  function resetCredentials(){toast.clear();authVersion++;token=null;csrf=null;authenticated=false;sessionStorage.removeItem(storage);sessionStorage.removeItem(hint);sessionStorage.removeItem(stageHint);}
  function hash(path){history.replaceState(null,'',location.pathname+location.search+'#'+path);}
  function route(){const path=location.hash.slice(1)||'/';return path.startsWith('/')&&!path.startsWith('//')?path:'/';}
  function go(path){if(route()===path)routeChanged();else location.hash=path;}
  function closePanel(){closeAchievement();panelVersion++;panelAbort?.abort();if(panel.open)panel.close();toast.syncHost();panelBody.replaceChildren();}
  function stopLogin(){loginVersion++;clearTimeout(pollTimer);loginAbort?.abort();polling=false;}
  function clearViews(){hideScreen();main.hidden=false;chrome('');mainVersion++;mainAbort?.abort();stopLogin();closePanel();mainReady=false;}
  function chrome(title){
    root.dataset.view=phase;document.querySelector('#intro-progress').hidden=true;back.setAttribute('aria-label','Вернуться к активностям');
    const secondary=Boolean(title);document.querySelector('.appbar').classList.toggle('appbar-detail',secondary);back.hidden=!secondary;barTitle.hidden=!secondary&&phase!=='app';barTitle.textContent=title||'Активности';document.querySelector('.appbar').dataset.secondary=String(secondary);
    document.querySelector('.brand').hidden=secondary;nav.hidden=phase!=='app'||secondary;
    document.title=title?title+' · МАЙТИМ':'МАЙТИМ';requestAnimationFrame(fitAppbarTitles);
  }
  function hideScreen(){screenVersion++;screenAbort?.abort();screenAbort=null;screen.hidden=true;screenKind=null;screenBody.replaceChildren();}
  function returnActivities(){
    const wasScreen=!screen.hidden;hideScreen();main.hidden=false;chrome('');
    if(wasScreen){window.scrollTo(0,activityScroll);main.querySelector('h1')?.focus({preventScroll:true});}
  }
  function showIntro(step=0,alreadyAuthenticated=false){
    clearViews();phase='intro';root.dataset.view='intro';introStep=step;introAuthenticated=alreadyAuthenticated;nav.hidden=true;hash('/');
    const progress=document.querySelector('#intro-progress');progress.hidden=false;progress.value=step+1;progress.setAttribute('aria-valuetext',`Шаг ${step+1} из 3`);
    back.hidden=step===0;back.setAttribute('aria-label','Предыдущий шаг');barTitle.hidden=true;document.querySelector('.brand').hidden=true;
    const fragment=clone('intro');fragment.querySelector('.intro-flow').dataset.introStep=step+1;put(fragment,'[data-step]',`Знакомство · ${step+1} из 3`);put(fragment,'[data-heading]',steps[step][0]);put(fragment,'[data-body]',steps[step][1]);
    const button=$(fragment,'[data-intro-next]');button.textContent=step===2?(alreadyAuthenticated?'Продолжить':'Войти через Telegram'):'Дальше';
    button.onclick=()=>step<2?showIntro(step+1,alreadyAuthenticated):startLogin(alreadyAuthenticated);
    main.replaceChildren(fragment);window.scrollTo(0,0);$(main,'h1').focus({preventScroll:true});
  }
  function fail(target,retry,message){const fragment=clone('error');if(message)put(fragment,'[role="alert"]',message);$(fragment,'[data-retry]').onclick=retry;target.replaceChildren(fragment);}
  function loading(target,kind='loading'){target.replaceChildren(clone(kind));}
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
    stopLogin();phase='login';introAuthenticated=alreadyAuthenticated;chrome('Авторизация');back.setAttribute('aria-label','Вернуться к знакомству');nav.hidden=true;closePanel();const fragment=clone('login');main.replaceChildren(fragment);main.querySelector('h1').focus({preventScroll:true});window.scrollTo(0,0);
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
      put(main,'[data-login-status]','После подтверждения вернись сюда — вход завершится автоматически.');
    }catch(error){if(version!==loginVersion||error.code==='cancelled')return;if(error.status===401){sessionLost();return;}put(main,'[data-login-status]','Не удалось проверить вход. Повторяем попытку…');}
    finally{polling=false;}
    if(version===loginVersion&&phase==='login')pollTimer=setTimeout(()=>pollLogin(version),2000);
  }
  function enterAccount(body){authenticated=true;sessionStorage.setItem(hint,'true');stopLogin();if(!acceptAccount(body))return;showApp();hash(intendedRoute);intendedRoute='/';loadActivities();routeChanged();}
  function showApp(){phase='app';hideScreen();main.hidden=false;chrome('');main.replaceChildren(clone('activities'));mainReady=false;}
  function showSetup(body){clearViews();phase='setup';chrome('');nav.hidden=true;hash('/');main.replaceChildren(element('h1','Давайте познакомимся'),element('p','Заполни три поля, чтобы перейти к активностям.','muted'));const target=element('div','', 'setup');main.append(target);renderProfile(target,body,true);}
  async function loadSetup(){
    clearViews();phase='setup-loading';chrome('');nav.hidden=true;hash('/');main.replaceChildren(element('h1','Давайте познакомимся'));
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
      if(yes&&current.answer.rating){body.append(ratingResult(current.answer.rating));}
      body.append(element('p','На следующей неделе будет новая возможность поучаствовать.','muted'));
    }else{
      const messages={new:['Добро пожаловать!','Ты только присоединился. Запись на текущую неделю уже завершена, поэтому активной встречи пока нет.'],skipped:['Эту неделю ты пропускаешь','На текущую неделю ты не записался. Всё в порядке — участие добровольное.'],preparing:['Ты записан на эту неделю','Готовим состав и инструкции. Они появятся здесь после публикации.'],unmatched:['В этот раз без активности','Ты записался, но участников не хватило для формирования группы.'],expired:['Активность не состоялась','На этой неделе не удалось запустить активность. Можно записаться на следующую неделю.']};
      const [title,text]=messages[current.kind]||messages.skipped;body.append(element('h2',title),element('p',text),element('p','Начни со следующей недели — запишись в соседнем блоке.','muted'));
    }
    renderNextActivity($(fragment,'[data-next-body]'),next);
    target.replaceChildren(fragment);
  }
  function renderNextActivity(target,next){
    if(!next.id){target.append(element('p','Запись пока не открыта. Загляни позже.','muted'));return;}
    target.append(element('p',next.activity_title));
    const hasCount=Number.isInteger(next.enrollment_count)&&next.enrollment_count>=0;
    const count=element('p','', 'enrollment-count');if(hasCount)target.append(count);
    const status=element('p','','muted');target.append(status);
    let button;
    const sync=()=>{
      if(hasCount)count.textContent=`Уже записались: ${next.enrollment_count}`;
      status.textContent=next.enrolled?'Ты уже записан':next.registration_open?`Запишись до ${day(next.closes_at)}, вторника, 21:00 МСК.`:'Запись закрыта.';
      if(button)button.textContent=next.enrolled?'Отменить запись':'Записаться';
    };
    if(!next.registration_open){
      if(next.enrolled)target.append(element('p',`Состав появится ${day(next.starts_at)} в 09:00 МСК.`,'muted'));
    }else if(!next.reachable){
      const reconnect=element('button','Подключить сообщения для участия','secondary');reconnect.type='button';reconnect.onclick=logout;target.append(reconnect);
    }else{
      button=element('button','','secondary');button.type='button';
      button.onclick=async()=>{
        if(button.disabled)return;
        const wasEnrolled=next.enrolled;button.disabled=true;button.setAttribute('aria-busy','true');
        try{
          const result=await request('/api/rounds/'+next.id+'/enrollment/',{method:'POST',data:{action:wasEnrolled?'cancel':'enroll'}});
          if(result.status!=='saved'||typeof result.enrolled!=='boolean'){if(result.state)acceptAccount(result);throw new ApiError('invalid_response');}
          next.enrolled=result.enrolled;
          if(hasCount&&wasEnrolled!==next.enrolled)next.enrollment_count=Math.max(0,next.enrollment_count+(next.enrolled?1:-1));
          sync();toast.success(next.enrolled?'Ты записан на активность':'Запись отменена');
        }catch(error){
          if(error.code==='cancelled')return;
          if(error.status===401)sessionLost();
          toast.error(error.code==='enrollment_closed'?'Запись на эту неделю закрыта':wasEnrolled?'Не удалось отменить запись. Попробуй ещё раз':'Не удалось записаться. Попробуй ещё раз');
        }finally{button.disabled=false;button.removeAttribute('aria-busy');}
      };
      target.append(button);
    }
    sync();
  }
  function openPanel(title,back='/'){
    closeAchievement();
    panelVersion++;panelAbort?.abort();panelAbort=new AbortController();closeTarget=back;panelTitle.textContent=title;loading(panelBody);if(!panel.open)panel.showModal();toast.syncHost();requestAnimationFrame(fitAppbarTitles);
    document.querySelector('#panel-close').setAttribute('aria-label','Закрыть оценку');
    return panelVersion;
  }
  async function loadScreen(kind){
    const previousScroll=!screen.hidden&&screenKind===kind?window.scrollY:0;
    closePanel();
    if(screen.hidden)activityScroll=window.scrollY;
    screenVersion++;screenAbort?.abort();screenAbort=new AbortController();const version=screenVersion;
    screenKind=kind;main.hidden=true;screen.hidden=false;screenTitle.textContent=kind==='profile'?'Профиль':'История активностей';chrome(screenTitle.textContent);loading(screenBody,kind==='profile'?'profile-loading':'loading');window.scrollTo(0,previousScroll);screenTitle.focus({preventScroll:true});
    try{
      const body=await request('/api/'+kind+'/',{signal:screenAbort.signal});if(version!==screenVersion)return;if(!acceptAccount(body))return;
      if(kind==='profile')renderProfile(screenBody,body,false);else renderHistory(body.entries);window.scrollTo(0,previousScroll);
    }catch(error){if(version===screenVersion)catchLoad(error,screenBody,()=>loadScreen(kind));}
  }
  function bindValidation(form,message){
    form.addEventListener('invalid',event=>{
      event.preventDefault();const field=event.target;field.setAttribute('aria-invalid','true');
      const note=form.querySelector(`[data-field-error="${field.name}"]`);
      if(note){note.textContent=field.name==='rating'?'Оцени активность от 1 до 5.':field.validity.valueMissing?'Заполни это поле.':'Проверь значение.';note.hidden=false;}
      toast.error(message);requestAnimationFrame(()=>form.querySelector('[aria-invalid]')?.focus({preventScroll:true}));
    },true);
    form.addEventListener('input',event=>{
      const field=event.target;if(!field.name||!field.validity?.valid)return;
      form.querySelectorAll(`[name="${field.name}"]`).forEach(node=>node.removeAttribute('aria-invalid'));
      const note=form.querySelector(`[data-field-error="${field.name}"]`);if(note){note.hidden=true;note.textContent='';}
    });
  }
  function clearErrors(form){form.querySelectorAll('[data-field-error]').forEach(node=>{node.hidden=true;node.textContent='';});form.querySelectorAll('[aria-invalid]').forEach(node=>node.removeAttribute('aria-invalid'));$(form,'[data-form-message]').replaceChildren();}
  function formError(form,error,message){
    if(error.code==='cancelled')return;
    if(error.status===401){sessionLost();toast.error('Сессия завершена. Войди снова');return;}
    toast.error(error.data?.fields?'Проверь заполненные поля':message);
    if(!document.contains(form))return;
    if(error.data?.fields){
      Object.entries(error.data.fields).forEach(([name,messages])=>{
        const node=form.querySelector(`[data-field-error="${name}"]`);
        if(node){node.textContent=messages.join(' ');node.hidden=false;form.querySelector(`[name="${name}"]`)?.setAttribute('aria-invalid','true');}
      });
      form.querySelector('[aria-invalid]')?.focus();
    }
  }
  function renderProfile(target,data,setup){
    const fragment=clone('profile');
    if(setup){$(fragment,'[data-achievements]').hidden=true;$(fragment,'[data-profile-actions]').hidden=true;$(fragment,'.profile-grid').classList.add('setup-profile');put(fragment,'[data-profile-heading]','Немного о тебе');put(fragment,'[data-submit]','Продолжить');}
    const form=$(fragment,'[data-profile-form]');bindValidation(form,'Проверь поля профиля');Object.entries(data.profile).forEach(([name,value])=>{if(form.elements[name])form.elements[name].value=value;});
    const awards=$(fragment,'[data-awards]');put(fragment,'[data-awards-count]',data.achievements?.length||0);
    if(!data.achievements?.length)awards.append(element('p','Здесь будут появляться ваши достижения.','muted'));
    else data.achievements.forEach(award=>{const card=clone('achievement'),button=$(card,'button');button.setAttribute('aria-label',award.title+' — подробнее');button.title=award.title;if(award.key!=='first_coffee')$(card,'img').src='web/icons/star-active.svg';button.onclick=()=>openAchievement(award);awards.append(card);});
    $(fragment,'[data-logout]').onclick=logout;
    form.onsubmit=async event=>{
      event.preventDefault();if(form.dataset.busy||!form.reportValidity())return;clearErrors(form);form.dataset.busy='true';const button=$(form,'[data-submit]'),label=button.textContent;button.disabled=true;button.textContent='Сохраняем…';const version=authVersion;
      try{
        const body=await request('/api/profile/',{method:'POST',data:Object.fromEntries(new FormData(form))});
        if(version!==authVersion)return;
        if(body.state!=='authenticated'){acceptAccount(body);toast.error('Не удалось сохранить профиль');return;}
        toast.success(setup?'Профиль создан':'Профиль обновлён');
        if(!document.contains(form))return;
        if(setup){enterAccount(body);return;}
      }catch(error){formError(form,error,'Не удалось сохранить профиль. Попробуй ещё раз');}
      finally{delete form.dataset.busy;button.disabled=false;button.textContent=label;}
    };
    target.replaceChildren(fragment);
  }
  function closeAchievement(){if(achievementDialog.open){achievementDialog.close();toast.syncHost();}}
  function openAchievement(award){
    document.querySelector('#achievement-title').textContent=award.title;
    document.querySelector('#achievement-description').textContent=award.description;
    document.querySelector('#achievement-image').src=award.key==='first_coffee'?'web/images/achievements/first-coffee.png':'web/icons/star-active.svg';
    const date=document.querySelector('#achievement-date'),earned=award.earned_at?new Date(award.earned_at):null;
    date.hidden=!earned||!Number.isFinite(earned.getTime());
    date.textContent=date.hidden?'':'Получено '+new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',year:'numeric',timeZone:'Europe/Moscow'}).format(earned);
    achievementDialog.showModal();toast.syncHost();
  }
  document.querySelector('.achievement-close').onclick=closeAchievement;
  achievementDialog.addEventListener('cancel',event=>{event.preventDefault();closeAchievement();});
  function renderHistory(entries){
    screenBody.replaceChildren();
    if(!entries.length){const card=element('section','', 'card');card.append(element('p','Здесь появятся недели, в которых ты участвовал. Пропущенные недели в историю не попадают.','muted'));screenBody.append(card);return;}
    entries.forEach(entry=>{
      const item=clone('history-item');put(item,'[data-title]',entry.activity_title);put(item,'[data-dates]',dates(entry.starts_at,entry.ends_at));const result=$(item,'[data-result]');
      if(entry.answer?.final){
        if(entry.answer.outcome==='yes'&&entry.answer.rating){result.append(ratingResult(entry.answer.rating));}
        else result.append(element('p',entry.answer.outcome==='yes'?'Активность проведена. Ответ сохранён.':'Не получилось провести активность.'));
      }else if(entry.can_rate){const button=element('button','Оценить активность','secondary');button.type='button';button.onclick=()=>go('/meetings/'+entry.meeting_id+'/feedback/?from=history');result.append(button);}
      screenBody.append(item);
    });
  }
  async function loadFeedback(meetingId,fromHistory){
    const version=openPanel('Оценка активности',fromHistory?'/history/':'/');
    try{
      const data=await request('/api/meetings/'+meetingId+'/feedback/',{signal:panelAbort.signal});if(version!==panelVersion)return;if(!acceptAccount(data))return;
      const fragment=clone('feedback');put(fragment,'[data-activity]',data.activity_title+' · '+dates(data.starts_at,data.ends_at));const form=$(fragment,'form');
      if(data.readonly){form.hidden=true;const note=$(fragment,'[data-readonly]');note.hidden=false;note.textContent='Срок изменения результата закончился.'+(data.answer?.rating?` Твоя оценка: ${data.answer.rating} из 5.`:'');}
      else{
        bindValidation(form,'Проверь поля оценки');
        if(data.answer){form.elements.outcome.value=['yes','no'].includes(data.answer.outcome)?data.answer.outcome:'';const rating=form.querySelector(`[name="rating"][value="${Number(data.answer.rating)}"]`);if(rating)rating.checked=true;form.elements.comment.value=data.answer.comment||'';}
        form.onsubmit=async event=>{
          event.preventDefault();if(form.dataset.busy||!form.reportValidity())return;clearErrors(form);form.dataset.busy='true';const button=$(form,'[data-submit]');button.disabled=true;button.textContent='Сохраняем…';
          try{
            const result=await request('/api/meetings/'+meetingId+'/feedback/',{method:'POST',data:Object.fromEntries(new FormData(form))});
            if(result.status!=='saved'){acceptAccount(result);throw new ApiError('invalid_response');}
            toast.success('Оценка отправлена');
            if(version!==panelVersion||!document.contains(form))return;
            loadActivities();go(fromHistory?'/history/':'/');
          }catch(error){formError(form,error,'Не удалось отправить оценку. Попробуй ещё раз');}
          finally{delete form.dataset.busy;button.disabled=false;button.textContent='Отправить';}
        };
      }
      panelBody.replaceChildren(fragment);window.bindActivityFeedback(panelBody);
    }catch(error){if(version===panelVersion)catchLoad(error,panelBody,()=>loadFeedback(meetingId,fromHistory));}
  }
  function routeChanged(){
    closeAchievement();
    if(phase!=='app'){if(phase==='intro'&&route()!=='/')showIntro(0,introAuthenticated);return;}
    const path=route();
    if(path==='/profile/'||path==='/history/'){loadScreen(path==='/profile/'?'profile':'history');return;}
    const match=path.match(/^\/meetings\/([a-f0-9-]{36})\/feedback\/(?:\?(.*))?$/i);
    if(match){
      const fromHistory=new URLSearchParams(match[2]||'').get('from')==='history';
      if(!fromHistory)returnActivities();
      else if(screen.hidden||screenKind!=='history')loadScreen('history');
      loadFeedback(match[1],new URLSearchParams(match[2]||'').get('from')==='history');return;}
    closePanel();returnActivities();hash('/');if(!mainReady&&!mainAbort)loadActivities();
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
  function fitAppbarTitles(){
    const mobile=matchMedia('(max-width: 720px)').matches;
    const header=panel.querySelector('.panel-header'),close=document.querySelector('#panel-close');
    if(mobile&&header.firstElementChild!==close)header.prepend(close);
    else if(!mobile&&header.lastElementChild!==close)header.append(close);
    for(const container of [document.querySelector('.appbar-inner'),header]){
      const title=container===header?panelTitle:barTitle;
      if(!container.getBoundingClientRect().width||title.hidden)continue;
      const button=container===header?close:back;
      const side=button.hidden?0:button.getBoundingClientRect().width;
      const guard=mobile?(mobileOS==='ios'?Math.max(60,side):side+16):Math.max(100,side+20);
      container.style.setProperty('--appbar-side',guard+'px');
      const available=container.clientWidth-2*guard;
      const range=document.createRange();range.selectNodeContents(title);
      container.classList.toggle('title-overflow',range.getBoundingClientRect().width>Math.max(0,available));
    }
  }
  const appbarResize=new ResizeObserver(()=>fitAppbarTitles());
  appbarResize.observe(document.querySelector('.appbar-inner'));appbarResize.observe(panel.querySelector('.panel-header'));
  window.addEventListener('resize',fitAppbarTitles,{passive:true});
  back.onclick=()=>phase==='intro'?showIntro(Math.max(0,introStep-1),introAuthenticated):phase==='login'?showIntro(2,introAuthenticated):go('/');
  let scrollPending=false;window.addEventListener('scroll',()=>{if(scrollPending)return;scrollPending=true;requestAnimationFrame(()=>{root.classList.toggle('scrolled',window.scrollY>48);root.style.setProperty('--appbar-scroll',Math.min(1,window.scrollY/32));scrollPending=false;});},{passive:true});
  nav.querySelectorAll('[data-open]').forEach(button=>button.onclick=()=>go('/'+button.dataset.open+'/'));
  document.querySelector('#panel-close').onclick=()=>go(closeTarget);
  panel.addEventListener('cancel',event=>{event.preventDefault();go(closeTarget);});
  document.querySelector('.brand').onclick=event=>{event.preventDefault();if(phase==='app')go('/');else if(phase!=='setup')showIntro(0,introAuthenticated);};
  window.addEventListener('hashchange',routeChanged);
  window.addEventListener('focus',()=>{if(phase==='login')pollLogin();});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&phase==='login')pollLogin();});
  if(authenticated){if(sessionStorage.getItem(stageHint)==='needs_profile')loadSetup();else if(sessionStorage.getItem(stageHint)==='needs_onboarding')showIntro(0,true);else{showApp();loadActivities();routeChanged();}}else showIntro(0);
})();
