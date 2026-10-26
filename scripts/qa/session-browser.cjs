/* Focused session persistence regression: intercepted JSON, no production/Telegram traffic. */
const {chromium}=require('playwright');
const fs=require('node:fs'),http=require('node:http'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..'),API='https://myteam-backend-eu.onrender.com';
const server=http.createServer((req,res)=>{
 const file=path.resolve(root,'.'+(req.url.split('?')[0]==='/'?'/index.html':req.url.split('?')[0]));
 if(!file.startsWith(root+path.sep))return res.writeHead(403).end();
 try{res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.png':'image/png'})[path.extname(file)]||'application/octet-stream');res.end(fs.readFileSync(file));}catch{res.writeHead(404).end();}
});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 const errors=[],contexts=[];let confirmed=false,expired=false;
 const account='a'.repeat(32),anonymous='b'.repeat(32),rotated='c'.repeat(32);
 async function context(storageState){
  const c=await browser.newContext({storageState});contexts.push(c);
  c.on('page',p=>{p.setDefaultTimeout(7000);p.on('pageerror',e=>errors.push(e.message));});
  await c.route('**/*',async route=>{
   const req=route.request(),u=new URL(req.url());if(u.origin===base)return route.continue();
   if(u.origin!==API){errors.push('Unexpected external request');return route.abort();}
   let body={state:'authenticated',csrf_token:'isolated'};const headers={'Access-Control-Allow-Origin':base,'Access-Control-Expose-Headers':'X-Myteam-Session'};
   if(u.pathname==='/bridge/bootstrap/')body={session:anonymous,csrf_token:'isolated'};
   else if(u.pathname==='/api/login/')body={code:'123456',bot_url:'https://t.me/isolated_bot',csrf_token:'isolated'};
   else if(u.pathname==='/api/login/status/'){
    if(!confirmed)body={state:'waiting',expired:false};else headers['X-Myteam-Session']=account;
   }else if(u.pathname==='/api/activities/'){
    if(![account,rotated].some(t=>req.headers().authorization==='Bearer '+t)){errors.push('Activity request without confirmed bearer');return route.fulfill({status:401,contentType:'application/json',body:'{"error":"invalid_session"}'});}
    if(expired)return route.fulfill({status:401,contentType:'application/json',body:'{"error":"expired_session"}'});
    body.current={kind:'new',activity_title:'Random Coffee',starts_at:'2026-10-21T06:00:00Z',ends_at:'2026-10-28T06:00:00Z'};
    body.next={id:'11111111-1111-4111-8111-111111111111',activity_title:'Random Coffee',starts_at:'2026-10-28T06:00:00Z',ends_at:'2026-11-04T06:00:00Z',closes_at:'2026-10-27T18:00:00Z',available:true,registration_open:true,reachable:true,enrolled:false,enrollment_count:0};
   }else if(u.pathname==='/api/profile/')body={...body,profile:{full_name:'Анна',team:'Команда',city:'Москва'},achievements:[]};
   else if(u.pathname==='/api/logout/')body={status:'logged_out'};
   else {errors.push('Unexpected endpoint '+u.pathname);return route.abort();}
   return route.fulfill({contentType:'application/json',headers,body:JSON.stringify(body)});
  });return c;
 }
 async function activities(p){try{await p.getByRole('heading',{name:'Добро пожаловать!',exact:true}).waitFor();}catch(e){console.error(errors,await p.locator('#main').innerText());throw e;}}
 async function intro(p){await p.getByRole('heading',{name:'Знакомься с коллегами',exact:true}).waitFor();}
 try{
  const c=await context(),p=await c.newPage();await p.goto(base);await intro(p);
  // Migrate a real existing tab: no forced re-login after the frontend update.
  await p.evaluate(token=>{sessionStorage.setItem('myteam.session',token);sessionStorage.setItem('myteam.authenticated','true');sessionStorage.setItem('myteam.stage','authenticated');},account);
  await p.reload();await activities(p);
  assert.equal(await p.evaluate(()=>JSON.parse(localStorage.getItem('myteam.account')).token),account);
  const second=await c.newPage();await second.goto(base);await activities(second);
  assert.equal(await second.evaluate(()=>sessionStorage.getItem('myteam.session')),account);
  // Simulate closing all tabs/browser and reopening with its persistent origin storage.
  const state=await c.storageState(),reopened=await context(state),third=await reopened.newPage();await third.goto(base);await activities(third);
  await reopened.close();
  await second.getByRole('button',{name:'Профиль',exact:true}).click();await second.getByRole('button',{name:'Выйти',exact:true}).click();
  await intro(second);await intro(p);await second.reload();await intro(second);
  assert.equal(await p.evaluate(()=>sessionStorage.getItem('myteam.session')),null);
  const guest=await c.newPage();await guest.goto(base);await intro(guest);
  await guest.getByRole('button',{name:'Дальше',exact:true}).click();await guest.getByRole('button',{name:'Дальше',exact:true}).click();await guest.getByRole('button',{name:'Войти через Telegram',exact:true}).click();
  await guest.locator('[data-code]').waitFor();assert.equal(await guest.evaluate(()=>JSON.parse(localStorage.getItem('myteam.account'))),null);
  const duringLogin=await c.newPage();await duringLogin.goto(base);await intro(duringLogin);
  confirmed=true;await guest.evaluate(()=>window.dispatchEvent(new Event('focus')));await activities(guest);await activities(duringLogin);await activities(p);
  assert.equal(await guest.evaluate(()=>JSON.parse(localStorage.getItem('myteam.account')).token),account);
  // A newer confirmed session invalidates in-flight auth work in other tabs.
  await guest.evaluate(token=>localStorage.setItem('myteam.account',JSON.stringify({token,stage:'authenticated'})),rotated);
  await p.waitForFunction(t=>sessionStorage.getItem('myteam.session')===t,rotated);await activities(p);
  expired=true;await p.reload();await intro(p);await intro(duringLogin);
  assert.deepEqual(errors,[]);console.log('PASS: legacy migration, new tab, browser reopen, cross-tab logout/login/rotation, anonymous isolation, server expiry; no screenshots or real API requests.');
 }finally{for(const c of contexts)await c.close().catch(()=>{});await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
