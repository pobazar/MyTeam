/* Isolated UI regression: JSON fixtures only; every external request is intercepted.
   Needs Playwright + Chromium; see docs/technical/design.md. No production credentials. */
const { chromium } = require('playwright');
const { readFileSync, mkdirSync } = require('node:fs');
const { createServer } = require('node:http');
const { resolve, extname } = require('node:path');
const assert = require('node:assert/strict');
const root = resolve(__dirname, '../..');
const out = process.env.MYTEAM_SCREENSHOTS;
const id = '11111111-1111-4111-8111-111111111111';
const start = '2026-10-21T06:00:00Z', end = '2026-10-28T06:00:00Z';
const server = createServer((req,res) => {
  const path = resolve(root, '.' + (req.url.split('?')[0] === '/' ? '/index.html' : req.url.split('?')[0]));
  if (!path.startsWith(root+'/')) {res.writeHead(403).end();return;}
  try { res.setHeader('Content-Type', ({'.html':'text/html; charset=utf-8','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml'})[extname(path)] || 'application/octet-stream');res.end(readFileSync(path)); }
  catch {res.writeHead(404).end();}
});
(async () => {
  await new Promise(r => server.listen(0,'127.0.0.1',r));
  const base = 'http://127.0.0.1:'+server.address().port;
  const browser = await chromium.launch({executablePath:process.env.CHROMIUM_PATH || '/usr/bin/chromium',headless:true,args:['--no-sandbox']});
  const errors=[];let snapshots=0;
  const shot = async (page,name) => {
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Page overflow: '+name);
    if(out){mkdirSync(out,{recursive:true});await page.screenshot({path:resolve(out,name+'.png'),fullPage:!name.endsWith('-scrolled')});snapshots++;}
  };
  try {
    for (const [platform,width,ua] of [
      ['desktop',1440,'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130 Safari/537.36'],
      ['android',393,'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/130 Mobile Safari/537.36'],
      ['ios',390,'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1'],
      ['small',320,'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/130 Mobile Safari/537.36'],
    ]) {
      const context=await browser.newContext({viewport:{width,height:844},userAgent:ua,isMobile:width<=720,hasTouch:width<=720,reducedMotion:'reduce'});
      const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
      let enrolled=false,answer=null,failProfile=true,profileCalls=0,activityCalls=0,holdProfile=null,releaseProfile,loginConfirmed=false,profileReady=false;
      const profile={full_name:'Михаил Орлов',team:'Разработка',city:'Москва'};
      await context.route('**/*',async route=>{
        const u=new URL(route.request().url());
        if(u.origin===base){await route.continue();return;}
        assert.equal(u.origin,'https://myteam-backend-eu.onrender.com','Unexpected external request');
        const path=u.pathname,method=route.request().method();
        let data={state:'authenticated',csrf_token:'isolated-csrf'};
        if(path==='/bridge/bootstrap/')data={session:'isolated',csrf_token:'isolated-csrf'};
        else if(path==='/api/login/')data={code:'47529',bot_url:'https://t.me/isolated_bot',csrf_token:'isolated-csrf'};
        else if(path==='/api/login/status/')Object.assign(data,loginConfirmed?{state:'needs_profile',profile:{full_name:'',team:'',city:''},achievements:[]}:{state:'waiting',expired:false});
        else if(path==='/api/activities/') {activityCalls++;data.current={kind:answer?'completed':'active',starts_at:start,ends_at:end,activity_title:'Random Coffee',meeting_id:id,answer,participants:[{name:'Михаил Орлов',team:'Разработка',city:'Москва'},{name:'Елена Волкова',team:'Маркетинг',city:'Казань'}],instructions:'Договоритесь об онлайн-встрече и выберите удобное время. Познакомьтесь и расскажите, чем занимается ваша команда.',contacts_url:'https://t.me/isolated_bot'};data.next={id,starts_at:end,ends_at:'2026-11-04T06:00:00Z',closes_at:'2026-10-27T18:00:00Z',activity_title:'Random Coffee',registration_open:true,reachable:true,enrolled};}
        else if(path==='/api/profile/') {
          profileCalls++;if(holdProfile)await holdProfile;
          if(failProfile&&method==='GET'&&profileReady){failProfile=false;await route.fulfill({status:503,contentType:'application/json',body:'{"error":"temporary"}'});return;}
          if(method==='POST'){Object.assign(profile,route.request().postDataJSON());profileReady=true;}data.profile=profile;data.achievements=[{title:'Первый кофе',description:'Твоя первая подтверждённая встреча.'}];
        }
        else if(path==='/api/history/')data.entries=[{meeting_id:id,activity_title:'Random Coffee',starts_at:start,ends_at:end,answer,can_rate:!answer}];
        else if(path.includes('/enrollment/')) {enrolled=route.request().postDataJSON().action==='enroll';data.status='saved';}
        else if(path.includes('/feedback/')) {if(method==='POST'){const body=route.request().postDataJSON();answer={outcome:body.outcome,rating:body.outcome==='yes'?Number(body.rating):null,final:true};}Object.assign(data,{activity_title:'Random Coffee',starts_at:start,ends_at:end,answer,readonly:false});}
        else if(path==='/api/logout/')data={status:'logged_out'};
        else throw Error('Unexpected API '+path);
        await route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
      });
      // Guest intro stays local and repeats on a new opening.
      await page.goto(base);await page.getByRole('heading',{name:'Знакомься с коллегами',exact:true}).waitFor();
      assert.equal(await page.evaluate(()=>document.documentElement.dataset.platform),platform==='desktop'?'generic':platform==='small'?'android':platform);assert.equal(activityCalls,0);await shot(page,platform+'-onboarding');
      assert.equal(await page.locator('#intro-progress').getAttribute('value'),'1');assert.equal(await page.getByRole('button',{name:'Предыдущий шаг',exact:true}).count(),0);
      await page.getByRole('button',{name:'Дальше',exact:true}).click();await page.getByText('Знакомство · 2 из 3',{exact:true}).waitFor({state:'attached'});assert.equal(await page.locator('#intro-progress').getAttribute('value'),'2');await shot(page,platform+'-onboarding-step2');
      await page.getByRole('button',{name:'Предыдущий шаг',exact:true}).click();await page.getByRole('heading',{name:'Знакомься с коллегами',exact:true}).waitFor();assert.equal(activityCalls,0);
      await page.getByRole('button',{name:'Дальше',exact:true}).click();await page.reload();await page.getByText('Знакомство · 1 из 3',{exact:true}).waitFor({state:'attached'});
      await page.getByRole('button',{name:'Дальше',exact:true}).click();await page.getByRole('button',{name:'Дальше',exact:true}).click();await page.getByRole('heading',{name:'Выбери ближайшую активность',exact:true}).waitFor();assert.equal(await page.locator('#intro-progress').getAttribute('value'),'3');await shot(page,platform+'-onboarding-step3');
      if(width<=393){await page.setViewportSize({width,height:568});await shot(page,platform+'-onboarding-short');await page.getByRole('button',{name:'Войти через Telegram',exact:true}).scrollIntoViewIfNeeded();const text=await page.locator('[data-body]').boundingBox(),cta=await page.locator('[data-intro-next]').boundingBox();assert.ok(text.y+text.height<=cta.y,'CTA overlaps intro text');await page.setViewportSize({width,height:844});}
      assert.equal(await page.getByRole('button',{name:'Пропустить',exact:true}).count(),0);await page.getByRole('button',{name:'Войти через Telegram',exact:true}).click();await page.locator('[data-code]').waitFor();await shot(page,platform+'-login');
      loginConfirmed=true;await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await page.getByRole('heading',{name:'Давайте познакомимся',exact:true}).waitFor();
      assert.equal(await page.getByRole('button',{name:'Профиль',exact:true}).count(),0);await shot(page,platform+'-mandatory-profile');
      await page.getByLabel('Как вас зовут',{exact:true}).fill(profile.full_name);await page.getByLabel('Команда',{exact:true}).fill(profile.team);await page.getByLabel('Город, где вы сейчас',{exact:true}).fill(profile.city);await page.getByRole('button',{name:'Продолжить',exact:true}).click();await page.getByRole('button',{name:'Поделиться результатом',exact:true}).waitFor();await shot(page,platform+'-activities');
      assert.equal(await page.locator('[data-open="history"] img').getAttribute('src'),'web/icons/doc-clock.svg');
      await page.getByRole('button',{name:'Записаться',exact:true}).click();await page.getByRole('button',{name:'Отменить запись',exact:true}).waitFor();await shot(page,platform+'-enrolled');
      await page.getByRole('button',{name:'Профиль',exact:true}).click();await page.getByRole('button',{name:'Повторить',exact:true}).waitFor();await shot(page,platform+'-profile-error');
      assert.equal(await page.getByRole('dialog').count(),0);assert.equal(await page.locator('#main').isVisible(),false);
      await page.getByRole('button',{name:'Повторить',exact:true}).click();await page.getByLabel('Как вас зовут',{exact:true}).waitFor();await shot(page,platform+'-profile');
      await page.setViewportSize({width,height:600});await page.evaluate(()=>window.scrollTo(0,160));await page.waitForFunction(()=>document.querySelector('#app').classList.contains('scrolled'));assert.equal(await page.locator('#appbar-title').evaluate(n=>getComputedStyle(n).opacity),'1');await shot(page,platform+'-profile-scrolled');
      if(width<=720)assert.equal(await page.locator('#appbar-title').evaluate(n=>getComputedStyle(n).textAlign),platform==='ios'?'center':'left');await page.evaluate(()=>window.scrollTo(0,0));await page.setViewportSize({width,height:844});
      await page.getByLabel('Команда',{exact:true}).fill('Продукт');await page.getByRole('button',{name:'Сохранить',exact:true}).click();await page.getByText('Профиль сохранён.',{exact:true}).waitFor();assert.equal(profile.team,'Продукт');
      const before=activityCalls;await page.goBack();await page.getByRole('heading',{name:'Активности',exact:true}).waitFor();assert.equal(activityCalls,before,'Back refetched activities');
      await page.getByRole('button',{name:'История',exact:true}).click();await page.getByRole('button',{name:'Оценить активность',exact:true}).waitFor();await shot(page,platform+'-history');
      await page.getByRole('button',{name:'Оценить активность',exact:true}).click();await page.getByRole('dialog').waitFor();await page.getByRole('radio',{name:'Да',exact:true}).check();
      await page.getByRole('radio',{name:'4 из 5',exact:true}).check();
      const rating=await page.locator('.star-options').boundingBox();assert.equal(rating.width,264);
      assert.equal(await page.locator('.star-option.selected').count(),4);
      assert.equal(await page.locator('#panel').evaluate(n=>n.scrollWidth>n.clientWidth),false,'Dialog overflow');await shot(page,platform+'-rating');
      await page.keyboard.press('Escape');await page.getByRole('dialog').waitFor({state:'hidden'});await page.getByRole('heading',{name:'История активностей',exact:true}).waitFor();
      await page.getByRole('button',{name:'Оценить активность',exact:true}).click();await page.getByRole('radio',{name:'Нет',exact:true}).check();assert.equal(await page.locator('[data-rating-panel]').isVisible(),false);
      await page.getByLabel('Почему не получилось?',{exact:true}).fill('Не нашли общее время.');await page.getByRole('button',{name:'Сохранить результат',exact:true}).click();await page.getByText('Не получилось провести активность.',{exact:true}).waitFor();assert.equal(await page.getByRole('button',{name:'Оценить активность',exact:true}).count(),0);
      await page.getByRole('button',{name:'Вернуться к активностям',exact:true}).click();await page.getByRole('heading',{name:'Активности',exact:true}).waitFor();
      // Returning before a slow profile response must not reopen the screen.
      holdProfile=new Promise(r=>releaseProfile=r);await page.getByRole('button',{name:'Профиль',exact:true}).click();await page.getByRole('heading',{name:'Профиль',exact:true}).waitFor();
      await page.waitForFunction(()=>document.querySelector('#screen-content [role="status"]')!==null);await shot(page,platform+'-profile-loading');await page.getByRole('button',{name:'Вернуться к активностям',exact:true}).click();releaseProfile();holdProfile=null;
      await page.getByRole('heading',{name:'Активности',exact:true}).waitFor();assert.equal(await page.locator('#screen').isVisible(),false);
      await page.getByRole('button',{name:'Профиль',exact:true}).click();await page.getByRole('button',{name:'Выйти',exact:true}).click();await page.getByRole('heading',{name:'Знакомься с коллегами',exact:true}).waitFor();assert.equal(await page.locator('[data-code]').count(),0);
      console.log(platform+': PASS');await context.close();
    }
    assert.deepEqual(errors,[]);console.log('Isolated navigation/platform/rating checks passed; screenshots: '+snapshots);
  } finally {await browser.close();await new Promise(r=>server.close(r));}
})().catch(error=>{console.error(error);server.close();process.exitCode=1;});
