/* Desktop state review. All API traffic is intercepted; no production writes/Telegram. */
const {chromium}=require('playwright');
const fs=require('node:fs'),http=require('node:http'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..'),out=process.env.MYTEAM_SCREENSHOTS||'/workspace/myteam-state-review';
const meeting='11111111-1111-4111-8111-111111111111',otherMeeting='22222222-2222-4222-8222-222222222222';
const starts='2026-10-21T06:00:00Z',ends='2026-10-28T06:00:00Z',API='https://myteam-backend-eu.onrender.com';
const award={key:'first_coffee',title:'Первый кофе',description:'Твоя первая подтверждённая встреча.',earned_at:'2026-10-25T10:00:00Z'};
const server=http.createServer((req,res)=>{const name=path.resolve(root,'.'+(req.url.split('?')[0]==='/'?'/index.html':req.url.split('?')[0]));if(!name.startsWith(root+'/'))return res.writeHead(403).end();try{res.setHeader('Content-Type',({'.html':'text/html; charset=utf-8','.js':'text/javascript','.css':'text/css','.png':'image/png','.svg':'image/svg+xml'})[path.extname(name)]||'application/octet-stream');res.end(fs.readFileSync(name));}catch{res.writeHead(404).end();}});
const snapshots=[],issues=[],contexts=[];let browser,base;
const btn=(p,name)=>p.getByRole('button',{name,exact:true});
const wait=selector=>({selector});
function initial(overrides={}){return {guest:false,stage:'authenticated',confirmed:false,expired:false,enrolled:false,count:7,kind:'active',registrationOpen:true,reachable:true,nextAvailable:true,answer:null,readonly:false,awards:[],historyMode:'unrated',historyAnswer:null,profile:{full_name:'Михаил Орлов',team:'Разработка',city:'Москва'},...overrides};}
function historyEntries(state){
 const entry={meeting_id:otherMeeting,activity_title:'Random Coffee',starts_at:'2026-10-14T06:00:00Z',ends_at:starts,answer:state.historyAnswer,can_rate:!state.historyAnswer?.final};
 if(state.historyMode==='empty')return [];
 if(state.historyMode==='mixed')return [{...entry,answer:{outcome:'yes',rating:4,final:true},can_rate:false},{...entry,meeting_id:'33333333-3333-4333-8333-333333333333',starts_at:'2026-10-07T06:00:00Z',ends_at:entry.starts_at,answer:{outcome:'no',rating:null,final:true},can_rate:false},{...entry,meeting_id:'44444444-4444-4444-8444-444444444444',starts_at:'2026-09-30T06:00:00Z',ends_at:'2026-10-07T06:00:00Z',answer:{outcome:'yes',rating:null,final:true},can_rate:false},{...entry,meeting_id:'55555555-5555-4555-8555-555555555555',starts_at:'2026-09-23T06:00:00Z',ends_at:'2026-09-30T06:00:00Z',answer:null,can_rate:true}];
 if(state.historyMode==='many')return Array.from({length:12},(_,i)=>({...entry,meeting_id:i===0?otherMeeting:`66666666-6666-4666-8666-${String(i).padStart(12,'0')}`,starts_at:new Date(Date.parse(entry.starts_at)-i*7*86400000).toISOString(),ends_at:new Date(Date.parse(entry.ends_at)-i*7*86400000).toISOString(),answer:i%3===1?{outcome:'no',rating:null,final:true}:{outcome:'yes',rating:i%5+1,final:true},can_rate:false}));
 return [entry];
}
async function scenario(overrides={},route='/'){
 const state=initial(overrides),calls=[],failures=new Map(),holds=new Map();
 const context=await browser.newContext({viewport:{width:1440,height:1000},locale:'ru-RU',reducedMotion:'reduce'});contexts.push(context);
 if(!state.guest)await context.addInitScript(stage=>{sessionStorage.setItem('myteam.session','isolated-session');sessionStorage.setItem('myteam.authenticated','true');sessionStorage.setItem('myteam.stage',stage);},state.stage);
 const page=await context.newPage();page.setDefaultTimeout(10000);page.on('pageerror',e=>issues.push(e.message));
 await context.route('**/*',async r=>{
  const url=new URL(r.request().url());if(url.origin===base)return r.continue();
  if(url.origin!==API){issues.push('Unexpected external request '+url.origin);return r.abort();}
  const key=r.request().method()+' '+url.pathname;calls.push(key);
  const hold=holds.get(key);if(hold){hold.seen();await hold.pending;}
  const failure=failures.get(key);if(failure?.length){const f=failure.shift();return r.fulfill({status:f.status||503,contentType:'application/json',body:JSON.stringify(f.body||{error:'temporary'})});}
  let body={state:state.stage,csrf_token:'isolated-csrf'};const post=r.request().method()==='POST',data=post?r.request().postDataJSON():{};
  if(url.pathname==='/bridge/bootstrap/')body={session:'isolated-session',csrf_token:'isolated-csrf'};
  else if(url.pathname==='/api/login/')body={code:'475291',bot_url:'https://t.me/isolated_bot',csrf_token:'isolated-csrf'};
  else if(url.pathname==='/api/login/status/')body=state.confirmed?{state:'needs_profile',profile:{full_name:'',team:'',city:''},achievements:[],csrf_token:'isolated-csrf'}:{state:'waiting',expired:state.expired,csrf_token:'isolated-csrf'};
  else if(url.pathname==='/api/profile/'){
   if(post){Object.assign(state.profile,data);state.stage='authenticated';body.state=state.stage;}
   Object.assign(body,{profile:state.profile,achievements:state.awards});
  }else if(url.pathname==='/api/activities/'){
   body.current={kind:state.kind,starts_at:starts,ends_at:ends,activity_title:'Random Coffee',meeting_id:meeting,answer:state.answer,participants:[{name:'Михаил Орлов',team:'Разработка',city:'Москва'},{name:'Елена Волкова',team:'Маркетинг',city:'Казань'}],instructions:'Договоритесь об онлайн-встрече и выберите удобное время. Напишите друг другу в Telegram. Рекомендуем 20–30 минут. Расскажите, чем занимается ваша команда, что недавно вдохновило и какое место в городе стоит посетить.',contacts_url:'https://t.me/isolated_bot'};
   body.next={id:state.nextAvailable?meeting:null,starts_at:ends,ends_at:'2026-11-04T06:00:00Z',closes_at:'2026-10-27T18:00:00Z',activity_title:'Random Coffee',enrolled:state.enrolled,enrollment_count:state.count,registration_open:state.registrationOpen,reachable:state.reachable};
  }else if(url.pathname.includes('/enrollment/')){const yes=data.action==='enroll';if(state.enrolled!==yes)state.count+=yes?1:-1;state.enrolled=yes;body={status:'saved',enrolled:yes};}
  else if(url.pathname==='/api/history/')body.entries=historyEntries(state);
  else if(url.pathname.includes('/feedback/')){
   const id=url.pathname.split('/')[3],historical=id!==meeting,entry=historical?historyEntries(state).find(e=>e.meeting_id===id):null;
   if(post){const answer={outcome:data.outcome,rating:data.outcome==='yes'?Number(data.rating):null,comment:data.comment||'',final:true};if(historical)state.historyAnswer=answer;else{state.answer=answer;state.kind='completed';}if(data.outcome==='yes')state.awards=[award];body={status:'saved',answer};}
   else Object.assign(body,{activity_title:'Random Coffee',starts_at:entry?.starts_at||starts,ends_at:entry?.ends_at||ends,readonly:state.readonly,answer:historical?entry?.answer:state.answer});
  }else if(url.pathname==='/api/logout/')body={status:'logged_out'};
  else {issues.push('Unexpected API '+key);body={error:'not_found'};}
  await r.fulfill({contentType:'application/json',body:JSON.stringify(body)});
 });
 const s={page,state,calls,context,fail:(key,body,status=503)=>{failures.set(key,[...(failures.get(key)||[]),{body,status}]);},hold:key=>{let release,seen;const pending=new Promise(r=>release=r),hit=new Promise(r=>seen=r);holds.set(key,{pending,seen});return {hit,release:()=>{holds.delete(key);release();}};},open:()=>page.goto(base+'/#'+route)};
 return s;
}
async function shot(s,title,group,notes='',options={}){
 const p=s.page;assert.deepEqual(issues,[],'Browser errors');await p.evaluate(()=>document.fonts.ready);
 await p.locator('img:visible').evaluateAll(imgs=>Promise.all(imgs.map(i=>i.decode().catch(()=>{}))));
 await p.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
 assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Horizontal overflow: '+title);
 for(const d of await p.locator('dialog[open]').all())assert.equal(await d.evaluate(n=>n.scrollWidth>n.clientWidth),false,'Dialog overflow: '+title);
 const file=String(snapshots.length+1).padStart(2,'0')+'.png';await p.screenshot({path:path.join(out,file),fullPage:options.fullPage!==false});snapshots.push({file,title,group,notes});fs.writeFileSync(path.join(out,'manifest.json'),JSON.stringify(snapshots,null,2));console.log(file,title);
}
async function settled(s,selector='[data-current-body]'){await s.page.locator(selector).first().waitFor();}
async function fresh(title,group,overrides={},route='/',selector='[data-current-body]',notes='') {const s=await scenario(overrides,route);await s.open();await settled(s,selector);await shot(s,title,group,notes);return s;}
async function clear(s){await s.page.evaluate(()=>window.MyTeamToasts.clear());}
async function choose(s,value){await btn(s.page,value==='yes'?'Да':'Нет').click();}
async function run(){
 await new Promise(r=>server.listen(0,'127.0.0.1',r));base='http://127.0.0.1:'+server.address().port;fs.mkdirSync(out,{recursive:true});browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 try{
  // Public introduction, login and mandatory setup.
  let s=await scenario({guest:true,kind:'new'});await s.open();await settled(s,'[data-intro-next]');assert.equal(s.calls.length,0);await shot(s,'Знакомство · шаг1','Онбординг');
  await btn(s.page,'Дальше').click();await shot(s,'Знакомство · шаг2','Онбординг');await btn(s.page,'Предыдущий шаг').click();await btn(s.page,'Дальше').click();await btn(s.page,'Дальше').click();await shot(s,'Знакомство · шаг3','Онбординг');
  let gate=s.hold('POST /api/login/');await btn(s.page,'Войти через Telegram').click();await gate.hit;await shot(s,'Авторизация · загрузка','Авторизация');gate.release();await settled(s,'[data-code]');await shot(s,'Авторизация · код и ожидание','Авторизация','Подтверждение Telegram эмулируется; реальных сообщений нет.');
  s.fail('POST /api/login/status/');await s.page.evaluate(()=>window.dispatchEvent(new Event('focus')));await s.page.getByText('Не удалось проверить вход. Повторяем попытку…',{exact:true}).waitFor();await shot(s,'Авторизация · временная ошибка проверки','Авторизация');await s.page.evaluate(()=>window.dispatchEvent(new Event('focus')));await s.page.getByText('После подтверждения вернись сюда — вход завершится автоматически.',{exact:true}).waitFor();
  s.state.expired=true;await s.page.evaluate(()=>window.dispatchEvent(new Event('focus')));await btn(s.page,'Получить новый код').waitFor();await shot(s,'Авторизация · истёкший код','Авторизация');
  s.fail('POST /api/login/');await btn(s.page,'Получить новый код').click();await btn(s.page,'Повторить').waitFor();await shot(s,'Авторизация · ошибка и повтор','Авторизация');s.state.expired=false;await btn(s.page,'Повторить').click();await settled(s,'[data-code]');
  s.state.confirmed=true;await s.page.evaluate(()=>window.dispatchEvent(new Event('focus')));await settled(s,'[data-profile-form]');assert.equal(await btn(s.page,'Профиль').count(),0);await shot(s,'Обязательный профиль · пустые поля','Профиль');
  await btn(s.page,'Продолжить').click();await settled(s,'#toast-host .toast');await shot(s,'Обязательный профиль · проверка полей','Профиль');await clear(s);
  await s.page.getByLabel('Как вас зовут',{exact:true}).fill('Анна Соколова');await s.page.getByLabel('Команда',{exact:true}).fill('Дизайн');await s.page.getByLabel('Город, где вы сейчас',{exact:true}).fill('Москва');
  s.fail('POST /api/profile/');await btn(s.page,'Продолжить').click();await settled(s,'#toast-host .toast');await shot(s,'Создание профиля · ошибка','Тосты','Введённые поля сохраняются; повтор — основной кнопкой.');await clear(s);
  gate=s.hold('POST /api/profile/');await btn(s.page,'Продолжить').click();await gate.hit;await shot(s,'Создание профиля · отправка','Профиль');gate.release();await settled(s);await s.page.getByText('Профиль создан',{exact:true}).waitFor();await shot(s,'Профиль создан · новая текущая активность','Тосты');await clear(s);
  // Stable widgets: no GET and no DOM replacement on enrollment/cancellation.
  s=await fresh('Активность · не записан','Активности');const p=s.page;await p.evaluate(()=>{window.reviewCurrent=document.querySelector('.current-week');window.reviewSignup=document.querySelector('[data-next-body] button');});const reads=s.calls.filter(x=>x==='GET /api/activities/').length;
  gate=s.hold('POST /api/rounds/'+meeting+'/enrollment/');await btn(p,'Записаться').click();await gate.hit;await shot(s,'Запись · отправка без перерисовки','Активности');gate.release();await btn(p,'Отменить запись').waitFor();await p.getByText('Ты записан на активность',{exact:true}).waitFor();
  assert.equal(s.calls.filter(x=>x==='GET /api/activities/').length,reads);assert.equal(await p.locator('[data-next-body]').getByText(/Запишись до/).count(),0);assert.equal(await p.locator('.enrollment-count').textContent(),'Уже записались: 8');assert.equal(await p.evaluate(()=>window.reviewCurrent===document.querySelector('.current-week')&&window.reviewSignup===document.querySelector('[data-next-body] button')),true);await shot(s,'Запись подтверждена · тост','Тосты');await clear(s);await shot(s,'Следующая активность · уже записан','Активности','Срок скрыт, серый статус; тот же DOM кнопки и текущего блока.');
  s.fail('POST /api/rounds/'+meeting+'/enrollment/');await btn(p,'Отменить запись').click();await p.getByText('Не удалось отменить запись. Попробуй ещё раз',{exact:true}).waitFor();assert.equal(await p.locator('.enrollment-count').textContent(),'Уже записались: 8');await shot(s,'Отмена записи · ошибка','Тосты');await clear(s);
  gate=s.hold('POST /api/rounds/'+meeting+'/enrollment/');await btn(p,'Отменить запись').click();await gate.hit;await shot(s,'Отмена записи · отправка','Активности');gate.release();await btn(p,'Записаться').waitFor();await p.getByText('Запись отменена',{exact:true}).waitFor();assert.equal(await p.locator('.enrollment-count').textContent(),'Уже записались: 7');assert.equal(s.calls.filter(x=>x==='GET /api/activities/').length,reads);assert.equal(await p.evaluate(()=>window.reviewCurrent===document.querySelector('.current-week')&&window.reviewSignup===document.querySelector('[data-next-body] button')),true);await shot(s,'Запись отменена · тост','Тосты');await clear(s);
  s.fail('POST /api/rounds/'+meeting+'/enrollment/');await btn(p,'Записаться').click();await p.getByText('Не удалось записаться. Попробуй ещё раз',{exact:true}).waitFor();await shot(s,'Запись · ошибка','Тосты');await clear(s);
  s.fail('POST /api/rounds/'+meeting+'/enrollment/',{error:'enrollment_closed'},409);await btn(p,'Записаться').click();await p.getByText('Запись на эту неделю закрыта',{exact:true}).waitFor();await shot(s,'Запись · срок истёк во время действия','Тосты');
  // Current activity and next registration states.
  for(const [kind,title] of [['new','Новый участник'],['skipped','Пропущенная активность'],['preparing','Состав готовится'],['unmatched','Не хватило участников'],['expired','Активность не запущена']])await fresh(title,'Активности',{kind});
  await fresh('Результат · проведено, оценка5','Активности',{kind:'completed',answer:{outcome:'yes',rating:5,final:true}});
  await fresh('Результат · не получилось','Активности',{kind:'completed',answer:{outcome:'no',rating:null,final:true}});
  await fresh('Результат · старый ответ без звёзд','Активности',{kind:'completed',answer:{outcome:'yes',rating:null,final:true}});
  await fresh('Следующая активность · запись ещё не открыта','Активности',{nextAvailable:false});await fresh('Запись закрыта · записан','Активности',{registrationOpen:false,enrolled:true});await fresh('Запись закрыта · не записан','Активности',{registrationOpen:false});await fresh('Сообщения бота недоступны','Активности',{reachable:false});await fresh('Первые участники · счётчик0','Активности',{count:0});
  // Loading/error views.
  s=await scenario();gate=s.hold('GET /api/activities/');await s.open();await gate.hit;await shot(s,'Активности · shimmer','Загрузка и ошибки');gate.release();await settled(s);
  s=await scenario();s.fail('GET /api/activities/');await s.open();await btn(s.page,'Повторить').waitFor();await shot(s,'Активности · ошибка загрузки','Загрузка и ошибки');assert.equal(await s.page.locator('.load-error [role="alert"]').evaluate(n=>getComputedStyle(n).color),await s.page.locator('body').evaluate(n=>getComputedStyle(n).color));await btn(s.page,'Повторить').click();await settled(s);
  // Profile: independent skeletons, empty/earned badges, dialog, mutations.
  s=await scenario();await s.open();await settled(s);gate=s.hold('GET /api/profile/');await btn(s.page,'Профиль').click();await gate.hit;assert.equal(await s.page.locator('#screen .profile-grid > section').count(),2);await shot(s,'Профиль · два отдельных shimmer','Загрузка и ошибки');gate.release();await settled(s,'[data-profile-form]');await shot(s,'Профиль · достижений пока нет','Профиль');
  s=await fresh('Профиль · полученное достижение','Профиль',{awards:[award]},'/profile/','[data-profile-form]');const before=s.calls.filter(x=>x==='GET /api/profile/').length;await s.page.getByLabel('Как вас зовут',{exact:true}).fill('Михаил Орлов — черновик');await btn(s.page,'Первый кофе — подробнее').click();await settled(s,'#achievement-dialog[open]');await shot(s,'Первый кофе · подробности награды','Достижения');await s.page.keyboard.press('Escape');assert.equal(await s.page.getByLabel('Как вас зовут',{exact:true}).inputValue(),'Михаил Орлов — черновик');assert.equal(s.calls.filter(x=>x==='GET /api/profile/').length,before);
  s.fail('POST /api/profile/',{error:'validation',fields:{team:['Проверь название команды.']}},422);await btn(s.page,'Сохранить').click();await s.page.locator('[data-field-error="team"]:visible').waitFor();await shot(s,'Профиль · ошибка поля','Профиль');await clear(s);
  s.fail('POST /api/profile/');await btn(s.page,'Сохранить').click();await s.page.getByText('Не удалось сохранить профиль. Попробуй ещё раз',{exact:true}).waitFor();await shot(s,'Профиль · не удалось сохранить','Тосты');await clear(s);
  gate=s.hold('POST /api/profile/');await btn(s.page,'Сохранить').click();await gate.hit;await shot(s,'Профиль · сохранение','Профиль');gate.release();await s.page.getByText('Профиль обновлён',{exact:true}).waitFor();await shot(s,'Профиль · успешно обновлён','Тосты');await clear(s);
  s=await scenario();s.fail('GET /api/profile/');await s.page.goto(base+'/#/profile/');await btn(s.page,'Повторить').waitFor();await shot(s,'Профиль · ошибка загрузки','Загрузка и ошибки');await btn(s.page,'Повторить').click();await settled(s,'[data-profile-form]');
  // History and entry to feedback.
  await fresh('История · пустое состояние','История',{historyMode:'empty'},'/history/','#screen-content .card');
  await fresh('История · оценки, пропуск проведения, старый ответ','История',{historyMode:'mixed'},'/history/','#screen-content .card');
  s=await fresh('История ·12 прошедших активностей','История',{historyMode:'many'},'/history/','.history-entry');await s.page.evaluate(()=>window.scrollTo(0,640));await shot(s,'История · прокрутка и закреплённый AppBar','История','Тот же размер экрана; снимок viewport при прокрутке.',{fullPage:false});
  s=await scenario();gate=s.hold('GET /api/history/');await s.page.goto(base+'/#/history/');await gate.hit;await shot(s,'История · shimmer','Загрузка и ошибки');gate.release();await settled(s,'.history-entry');
  s=await scenario();s.fail('GET /api/history/');await s.page.goto(base+'/#/history/');await btn(s.page,'Повторить').waitFor();await shot(s,'История · ошибка загрузки','Загрузка и ошибки');await btn(s.page,'Повторить').click();await settled(s,'.history-entry');
  // Feedback choice, success/no without reason, retry and readonly.
  s=await scenario();await s.open();await settled(s);gate=s.hold('GET /api/meetings/'+meeting+'/feedback/');await btn(s.page,'Поделиться результатом').click();await gate.hit;await shot(s,'Оценка · shimmer в диалоге','Загрузка и ошибки');gate.release();await btn(s.page,'Да').waitFor();assert.equal(await btn(s.page,'Отправить').count(),0);await shot(s,'Оценка · только выбор Да/Нет','Оценка');
  await choose(s,'yes');assert.equal(await btn(s.page,'Да').count(),0);await shot(s,'Оценка · Да, звёзды ещё не выбраны','Оценка');await btn(s.page,'Отправить').click();await s.page.getByText('Проверь поля оценки',{exact:true}).waitFor();await shot(s,'Оценка · обязательные звёзды не выбраны','Оценка');await clear(s);await s.page.getByRole('radio',{name:'3 из 5',exact:true}).check();await s.page.getByLabel('Комментарий (необязательно)',{exact:true}).fill('Приятно познакомились, нашли общие темы.');await shot(s,'Оценка ·3 звезды и комментарий','Оценка');await s.page.getByRole('radio',{name:'5 из 5',exact:true}).check();await shot(s,'Оценка ·5 звёзд','Оценка');for(const value of [1,2,4]){await s.page.getByRole('radio',{name:value+' из 5',exact:true}).check();assert.equal(await s.page.locator('.star-option.selected').count(),value);await shot(s,'Оценка ·'+value+' '+(value===1?'звезда':'звезды'),'Оценка');}
  await btn(s.page,'Изменить ответ').click();await choose(s,'no');assert.equal(await s.page.locator('[data-rating-panel]').isVisible(),false);assert.equal(await s.page.locator('textarea').evaluate(n=>n.required),false);await s.page.locator('textarea').fill('');await shot(s,'Оценка · Нет, причина необязательна','Оценка');await s.page.locator('textarea').fill('Не удалось подобрать общее время.');await shot(s,'Оценка · Нет, причина заполнена','Оценка');
  await btn(s.page,'Изменить ответ').click();await choose(s,'yes');await s.page.locator('textarea').fill('Приятно познакомились и нашли общие темы.');s.fail('POST /api/meetings/'+meeting+'/feedback/');await btn(s.page,'Отправить').click();await s.page.getByText('Не удалось отправить оценку. Попробуй ещё раз',{exact:true}).waitFor();await shot(s,'Оценка · ошибка отправки поверх диалога','Тосты');assert.equal(await s.page.locator('#panel #toast-host .toast').count(),1);await clear(s);
  gate=s.hold('POST /api/meetings/'+meeting+'/feedback/');await btn(s.page,'Отправить').click();await gate.hit;await shot(s,'Оценка · отправка','Оценка');gate.release();await s.page.getByText('Оценка отправлена',{exact:true}).waitFor();await s.page.getByRole('heading',{name:'Спасибо за участие!',exact:true}).waitFor();await shot(s,'Оценка отправлена · текущая активность завершена','Тосты');assert.equal(await s.page.locator('body > #toast-host .toast').count(),1);
  s=await scenario();await s.page.goto(base+'/#/history/');await btn(s.page,'Оценить активность').click();await btn(s.page,'Нет').waitFor();await choose(s,'no');await btn(s.page,'Отправить').click();await s.page.getByText('Не получилось провести активность.',{exact:true}).waitFor();await shot(s,'Оценка Нет без причины · возвращение в историю','Оценка');assert.equal(await btn(s.page,'Оценить активность').count(),0);
  s=await fresh('Оценка · срок изменения завершён','Оценка',{readonly:true,answer:{outcome:'yes',rating:4,comment:'Хорошая встреча.',final:true}},'/meetings/'+meeting+'/feedback/','[data-readonly]:visible');
  s=await scenario();s.fail('GET /api/meetings/'+meeting+'/feedback/');await s.page.goto(base+'/#/meetings/'+meeting+'/feedback/');await s.page.locator('#panel [data-retry]').waitFor();await shot(s,'Оценка · ошибка загрузки','Загрузка и ошибки');
  // Notification stack, explicit close, hover pause and timeout.
  s=await scenario();await s.page.clock.install();await s.open();await settled(s);
  await btn(s.page,'Записаться').click();await btn(s.page,'Отменить запись').waitFor();await s.page.locator('.toast').hover();await s.page.clock.fastForward(6000);assert.equal(await s.page.locator('.toast').count(),1);await s.page.mouse.move(0,0);await s.page.clock.fastForward(5100);assert.equal(await s.page.locator('.toast').count(),0);
  await btn(s.page,'Отменить запись').click();await btn(s.page,'Записаться').waitFor();await btn(s.page,'Записаться').click();await btn(s.page,'Отменить запись').waitFor();assert.equal(await s.page.locator('.toast').count(),2);await shot(s,'Два действия подряд · стопка тостов','Тосты');await s.page.locator('.toast-dismiss').first().click();assert.equal(await s.page.locator('.toast').count(),1);await s.page.locator('.toast-dismiss').click();assert.equal(await s.page.locator('.toast').count(),0);
  // Logout is instant even while revocation is pending.
  s=await scenario();await s.page.goto(base+'/#/profile/');await settled(s,'[data-profile-form]');gate=s.hold('POST /api/logout/');await btn(s.page,'Выйти').click();await gate.hit;await s.page.getByRole('heading',{name:'Знакомься с коллегами',exact:true}).waitFor();assert.equal(await s.page.evaluate(()=>sessionStorage.getItem('myteam.session')),null);await shot(s,'Выход · сразу первый шаг знакомства','Авторизация');gate.release();
  assert.deepEqual(issues,[]);fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({status:'passed',viewport:'1440×1000 Chromium',screenshots:snapshots.length,externalRequests:0,productionWrites:0,jsErrors:issues,assertions:['enrollment/cancel: no GET, no current/button DOM replacement, count changes locally, deadline hidden when enrolled','failed action preserves enrollment/count','profile badge preserves unsaved inputs; no GET on detail close','feedback choice → conditional fields; no reason required for no; modal toast and completed state','history no reason final; logout clears session immediately']},null,2));console.log('PASS',snapshots.length,'desktop states');
 }finally{for(const c of contexts)await c.close();await browser.close();await new Promise(r=>server.close(r));}
}
run().catch(e=>{console.error(e);server.close();process.exitCode=1;});
