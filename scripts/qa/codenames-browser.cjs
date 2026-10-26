/* Focused game review. API bodies come from codenames-fixtures.py, never from production. */
const {chromium}=require('playwright');
const fs=require('node:fs'),http=require('node:http'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..'),out=path.join(root,'docs/qa/code-names');
const fixtures=JSON.parse(fs.readFileSync('/tmp/myteam-codenames-preview.json','utf8'));
const API='https://myteam-backend-eu.onrender.com',errors=[],shots=[];
const server=http.createServer((req,res)=>{const file=path.resolve(root,'.'+(req.url.split('?')[0]==='/'?'/index.html':req.url.split('?')[0]));if(!file.startsWith(root+'/'))return res.writeHead(403).end();try{res.setHeader('Content-Type',({'.html':'text/html; charset=utf-8','.js':'text/javascript','.css':'text/css','.png':'image/png','.svg':'image/svg+xml'})[path.extname(file)]||'application/octet-stream');res.end(fs.readFileSync(file));}catch{res.writeHead(404).end();}});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000},locale:'ru-RU',reducedMotion:'reduce'});
  await context.addInitScript(()=>{sessionStorage.setItem('myteam.session','isolated-qa');sessionStorage.setItem('myteam.authenticated','true');sessionStorage.setItem('myteam.stage','authenticated');});
  const page=await context.newPage();page.setDefaultTimeout(10000);page.on('pageerror',e=>errors.push(e.message));
  let group='group4',saved=false;
  await context.route('**/*',async r=>{
   const u=new URL(r.request().url());if(u.origin===base)return r.continue();
   if(u.origin!==API){errors.push('Unexpected external request '+u.origin);return r.abort();}
   let data;
   if(u.pathname==='/api/activities/')data=saved?fixtures.completed:fixtures[group];
   else if(u.pathname==='/api/profile/')data=fixtures.profile;
   else if(u.pathname==='/api/history/')data=fixtures.history;
   else if(u.pathname.includes('/feedback/')){
    if(r.request().method()==='POST'){saved=true;data={status:'saved',answer:fixtures.saved_answer};}
    else data=fixtures.feedback;
   }else{errors.push('Unexpected endpoint '+u.pathname);return r.abort();}
   await r.fulfill({contentType:'application/json',body:JSON.stringify({...data,csrf_token:'isolated'})});
  });
  async function shot(file,title){
   await page.evaluate(()=>document.fonts.ready);await page.locator('img:visible').evaluateAll(xs=>Promise.all(xs.map(x=>x.decode().catch(()=>{}))));
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'overflow');assert.deepEqual(errors,[]);
   await page.screenshot({path:path.join(out,file),fullPage:true});shots.push({file,title});console.log(file,title);
  }
  for(const [key,file,title] of [['group4','01-organizer-four.png','Четыре участника · вид организатора'],['group5','02-participant-five.png','Пять участников · вид участника'],['group7','03-seven.png','Семь участников · допустимый остаток']]){
   group=key;await page.goto(base+'/?cohort='+key+'#/');await page.getByRole('heading',{name:'Code Names',exact:true}).waitFor();
   assert.equal(await page.getByRole('link',{name:'Открыть Code Names',exact:true}).getAttribute('href'),'https://codenames.game/');
   assert.equal(await page.getByRole('link',{name:'Связаться через Telegram',exact:true}).count(),fixtures[key].current.participants.length-1);
   await shot(file,title);
  }
  group='group4';await page.goto(base+'/?cohort=feedback#/');await page.getByRole('button',{name:'Поделиться результатом',exact:true}).click();await page.getByRole('button',{name:'Да',exact:true}).click();await page.getByRole('radio',{name:'5 из 5',exact:true}).check();await page.getByLabel('Комментарий (необязательно)',{exact:true}).fill('Было интересно услышать, какие разные ассоциации возникают у коллег.');
  await shot('04-feedback.png','Оценка Code Names');await page.getByRole('button',{name:'Отправить',exact:true}).click();await page.getByRole('heading',{name:'Спасибо за участие!',exact:true}).waitFor();
  await page.evaluate(()=>window.MyTeamToasts.clear());await page.getByRole('button',{name:'Профиль',exact:true}).click();await page.getByRole('button',{name:'Мастер ассоциаций — подробнее',exact:true}).click();await page.locator('#achievement-dialog[open]').waitFor();
  assert.match(await page.locator('#achievement-image').getAttribute('src'),/first-code-names.png$/);await shot('05-achievement.png','Мастер ассоциаций · награда за первую игру');
  fs.writeFileSync(path.join(out,'manifest.json'),JSON.stringify(shots,null,2));fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({status:'passed',viewport:'1440×1000 Chromium',screenshots:shots.length,jsErrors:errors,productionWrites:0,telegramSends:0,fixtures:'real Django API responses from disposable local PostgreSQL'},null,2));
  await context.close();console.log('PASS: focused Code Names states, contacts, game link, feedback and badge.');
 }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
