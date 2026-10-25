/* TUI toast: polite announcements, mobile queue, desktop stack, 5s timeout. */
(() => {
  const host=document.querySelector('#toast-host'),template=document.querySelector('#tpl-toast');
  const desktop=matchMedia('(min-width: 721px)'),pending=[],active=new Set();
  const hasPopover=typeof host.showPopover==='function';
  const isOpen=()=>hasPopover&&host.matches(':popover-open');
  let recent=null;
  function syncHost(){
    const dialog=document.querySelector('#panel'),parent=dialog.open?dialog:document.body;
    if(host.parentNode!==parent){
      if(isOpen())host.hidePopover();
      parent.append(host);
    }
    if(active.size&&host.showPopover&&!isOpen())host.showPopover();
    if(!active.size&&isOpen())host.hidePopover();
  }
  function remove(item){
    if(!active.has(item))return;
    clearTimeout(item.timer);active.delete(item);item.node.remove();syncHost();drain();
  }
  function pause(item,reason){if(!active.has(item))return;if(!item.paused.size)item.remaining=Math.max(0,item.remaining-(performance.now()-item.started));item.paused.add(reason);clearTimeout(item.timer);}
  function resume(item,reason){if(!active.has(item))return;if(reason)item.paused.delete(reason);if(item.paused.size)return;clearTimeout(item.timer);item.started=performance.now();item.timer=setTimeout(()=>remove(item),item.remaining);}
  function render(message,kind){
    const node=template.content.firstElementChild.cloneNode(true);
    node.dataset.kind=kind;node.querySelector('.toast-message').textContent=message;
    node.querySelector('[data-toast-success]').toggleAttribute('hidden',kind!=='success');
    node.querySelector('[data-toast-error]').toggleAttribute('hidden',kind!=='error');
    const item={node,remaining:5000,timer:null,started:0,paused:new Set()};
    node.querySelector('.toast-dismiss').onclick=()=>remove(item);
    node.addEventListener('pointerenter',e=>{if(e.pointerType==='mouse')pause(item,'pointer');});node.addEventListener('pointerleave',()=>resume(item,'pointer'));
    node.addEventListener('focusin',()=>pause(item,'focus'));node.addEventListener('focusout',()=>resume(item,'focus'));
    let start;
    node.addEventListener('pointerdown',e=>{if(e.pointerType!=='mouse')start={x:e.clientX,y:e.clientY};});
    node.addEventListener('pointerup',e=>{if(start&&start.y-e.clientY>32&&Math.abs(start.x-e.clientX)<64)remove(item);start=null;});
    node.addEventListener('pointercancel',()=>{start=null;});
    active.add(item);syncHost();host.prepend(node);resume(item);
  }
  function drain(){while(pending.length&&(desktop.matches||active.size===0)){const item=pending.shift();render(item.message,item.kind);}}
  function push(kind,message){
    const now=performance.now();
    if(recent&&recent.kind===kind&&recent.message===message&&now-recent.at<500)return;
    recent={kind,message,at:now};pending.push({kind,message});drain();
  }
  function clear(){pending.length=0;for(const item of [...active]){clearTimeout(item.timer);item.node.remove();}active.clear();recent=null;syncHost();}
  desktop.addEventListener('change',()=>{
    if(!desktop.matches&&active.size>1){
      const items=[...active];
      for(const item of items.slice(1)){clearTimeout(item.timer);pending.push({kind:item.node.dataset.kind,message:item.node.querySelector('.toast-message').textContent});active.delete(item);item.node.remove();}
    }
    drain();
  });
  window.MyTeamToasts={success:message=>push('success',message),error:message=>push('error',message),clear,syncHost};
})();
