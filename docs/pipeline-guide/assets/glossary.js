// Text-node annotation preserves the original wording and never rewrites markup/code blocks.
(() => {
  const entries = JSON.parse(document.getElementById('glossary-data').textContent);
  const byAlias = new Map();
  for (const entry of entries) for (const alias of [entry.term, ...(entry.aliases || [])]) byAlias.set(alias.toLowerCase(), entry);
  const escape = value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const pattern = new RegExp(`(?<![A-Za-z0-9_])(${[...byAlias.keys()].sort((a,b)=>b.length-a.length).map(escape).join('|')})(?![A-Za-z0-9_])`, 'gi');
  const tip = document.createElement('div');tip.id='term-tooltip';tip.role='tooltip';tip.hidden=true;document.body.append(tip);
  let anchor=null, timer=null;
  function hide(){clearTimeout(timer);if(anchor)anchor.removeAttribute('aria-describedby');anchor=null;tip.hidden=true;}
  function position(){
    if(!anchor?.isConnected){hide();return;}
    const r=anchor.getBoundingClientRect();
    tip.style.left='0px';tip.style.top='0px';
    const box=tip.getBoundingClientRect();
    tip.style.left=`${Math.max(10,Math.min(r.left,innerWidth-box.width-10))}px`;
    tip.style.top=`${Math.max(10,r.bottom+8+box.height<innerHeight?r.bottom+8:r.top-box.height-8)}px`;
  }
  function show(target, items){
    hide();anchor=target;
    const host=document.querySelector('dialog[open]') || document.body;host.append(tip);
    tip.replaceChildren();
    for(const item of items){const title=document.createElement('strong');title.textContent=item.term;const text=document.createElement('p');text.textContent=item.description;tip.append(title,text);}
    tip.hidden=false;anchor.setAttribute('aria-describedby',tip.id);position();
  }
  function annotate(root){
    const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,{acceptNode(text){
      const el=text.parentElement;
      if(!text.textContent.trim() || el.closest('script,style,pre,svg,a,.term-hint,.detail-source,.node-action,.node-top'))return NodeFilter.FILTER_REJECT;
      if(el.closest('code') && /[/\\]/.test(el.closest('code').textContent))return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    }});
    const texts=[];while(walker.nextNode())texts.push(walker.currentNode);
    for(const text of texts){
      const matches=[...text.textContent.matchAll(pattern)];if(!matches.length)continue;
      const fragment=document.createDocumentFragment();let offset=0;
      for(const match of matches){
        fragment.append(text.textContent.slice(offset,match.index));
        const term=document.createElement('span');term.className='term-hint';term.dataset.term=match[0].toLowerCase();term.textContent=match[0];
        // A flow node is already a button. Do not nest focusable controls inside it.
        if(!text.parentElement.closest('button'))term.tabIndex=0;
        fragment.append(term);offset=match.index+match[0].length;
      }
      fragment.append(text.textContent.slice(offset));text.replaceWith(fragment);
    }
  }
  const roots=[...document.querySelectorAll('#nodes,#map-title,#map-description,#detail-title,#detail-summary,#detail-panel,#reference-body,#reader article')];
  const observer=new MutationObserver(()=>{hide();refresh();});
  function refresh(){observer.disconnect();roots.forEach(annotate);roots.forEach(root=>observer.observe(root,{childList:true,subtree:true,characterData:true}));}
  refresh();
  document.addEventListener('pointerover',event=>{const term=event.target.closest?.('.term-hint');if(term){clearTimeout(timer);show(term,[byAlias.get(term.dataset.term)]);}else if(tip.contains(event.target))clearTimeout(timer);});
  document.addEventListener('pointerout',event=>{if(event.target.closest?.('.term-hint') || tip.contains(event.target))timer=setTimeout(hide,160);});
  document.addEventListener('focusin',event=>{
    const term=event.target.closest?.('.term-hint');
    if(term)show(term,[byAlias.get(term.dataset.term)]);
    else if(event.target.matches('.flow-node')){const items=[...new Set([...event.target.querySelectorAll('.term-hint')].map(el=>byAlias.get(el.dataset.term)))];if(items.length)show(event.target,items);else hide();}
    else hide();
  });
  document.addEventListener('focusout',()=>{timer=setTimeout(hide,160);});
  document.addEventListener('click',event=>{
    const term=event.target.closest?.('.term-hint');
    if(term){event.preventDefault();event.stopPropagation();show(term,[byAlias.get(term.dataset.term)]);}
    else if(!tip.contains(event.target))hide();
  },true);
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!tip.hidden){event.preventDefault();event.stopImmediatePropagation();hide();}},true);
  addEventListener('scroll',event=>{if(!tip.contains(event.target))hide();},true);addEventListener('resize',hide);addEventListener('beforeprint',hide);
  document.querySelector('#reference-dialog').addEventListener('close',hide);
})();
