/* Two non-modal hints per successful sign-in, following the supplied tui-tooltip. */
(() => {
  const key='myteam.activity-hints';
  const steps=[['.current-week','Тут будет написано что делать'],['.next-week','А тут можно записаться']];
  let tip,anchor,host,observer;
  function hide(){
    if(anchor)anchor.removeAttribute('aria-describedby');
    tip?.remove();tip=null;anchor=null;observer?.disconnect();observer=null;
    window.removeEventListener('resize',position);window.removeEventListener('scroll',position,true);
    document.removeEventListener('keydown',escape);
  }
  function finish(){hide();sessionStorage.removeItem(key);}
  function escape(event){if(event.key==='Escape'){event.preventDefault();finish();}}
  function position(){
    if(!tip||!anchor?.isConnected)return hide();
    const rect=anchor.getBoundingClientRect(),width=tip.offsetWidth,height=tip.offsetHeight;
    const left=Math.max(12,Math.min(innerWidth-width-12,rect.left+16));
    const below=rect.top+rect.height+12;
    const top=below+height<=innerHeight-12?below:Math.max(12,rect.top-height-12);
    tip.style.left=left+'px';tip.style.top=top+'px';
    tip.dataset.side=top>=rect.bottom?'below':'above';
    tip.style.setProperty('--hint-arrow',Math.max(16,Math.min(width-16,rect.left+Math.min(rect.width/2,48)-left))+'px');
  }
  function show(root){
    const value=sessionStorage.getItem(key);
    if(value===null||root.hidden||location.hash!=='#/'||document.querySelector('dialog[open]'))return;
    const step=Number(value);if(!Number.isInteger(step)||!steps[step])return finish();
    const card=root.querySelector(steps[step][0]);if(!card)return;
    if(tip&&anchor?.isConnected&&host===root)return;
    hide();host=root;anchor=card.querySelector('.eyebrow')||card;
    anchor.scrollIntoView({block:'nearest',behavior:'instant'});
    tip=document.createElement('button');tip.type='button';tip.id='activity-hint';tip.className='activity-hint';
    tip.textContent=steps[step][1];
    tip.setAttribute('aria-label',steps[step][1]+(step===0?'. Следующая подсказка':'. Закрыть подсказку'));
    anchor.setAttribute('aria-describedby',tip.id);
    tip.onclick=()=>{
      const focused=document.activeElement===tip;
      hide();
      if(step===0){sessionStorage.setItem(key,'1');show(root);if(focused)tip?.focus({preventScroll:true});}
      else {sessionStorage.removeItem(key);if(focused){const target=card.querySelector('button,a')||root.querySelector('h1');target?.focus({preventScroll:true});}}
    };
    document.body.append(tip);position();
    observer=new ResizeObserver(position);observer.observe(card);observer.observe(tip);
    window.addEventListener('resize',position);window.addEventListener('scroll',position,true);document.addEventListener('keydown',escape);
  }
  window.MyTeamActivityHints={show,hide,arm(){hide();sessionStorage.setItem(key,'0');},reset:finish};
})();
