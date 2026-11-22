/* Editorial Archive — index panel controller
   Contract: initIndexPanel(ctx), ctx={state,data,dom,graph,dossier,player}.
   Owns: 4 filter groups, overview stats, search dropdown, layout/index/lang/reset/random/path wiring. */
export function initIndexPanel(ctx){
  const {state,data,dom,graph,dossier}=ctx;
  const $=dom.$, $$=dom.$$, mk=dom.el;
  const byId=(id)=>document.getElementById(id);
  const focusPerson=(p,zoom=1.35)=>{
    if(!p) return;
    if(typeof dossier?.selectPerson==="function") dossier.selectPerson(p);
    if(typeof graph?.focusPerson==="function") graph.focusPerson(p);
    else if(graph?.cy){
      const n=graph.cy.getElementById(p.en);
      if(n&&n.length) graph.cy.animate({center:{eles:n},zoom,duration:520});
    }
  };

  
  function runPath(fromPerson,toPerson){
    const prev=new Map(), queue=[fromPerson.en], seen=new Set([fromPerson.en]);
    while(queue.length){
      const cur=queue.shift();
      if(cur===toPerson.en) break;
      const neighbours=new Set([...(state.outMap.get(cur)?.keys()||[]),...(state.inMap.get(cur)?.keys()||[])]);
      for(const next of neighbours){ if(seen.has(next)) continue; seen.add(next); prev.set(next,cur); queue.push(next); }
    }
    if(!seen.has(toPerson.en)) return null;
    const nodes=[toPerson.en];
    while(nodes[nodes.length-1]!==fromPerson.en){ const p=prev.get(nodes[nodes.length-1]); if(!p) return null; nodes.push(p); }
    nodes.reverse();
    return nodes.map(en=>state.people.get(en)).filter(Boolean);
  }
  function maybeRunPath(){
    if(state.selected.length!==2) return;
    const nodes=runPath(state.selected[0],state.selected[1]);
    if(!nodes){ if(typeof dom.toast==="function") dom.toast("两人之间没有已知关系链"); return; }
    if(typeof graph?.showPath==="function") graph.showPath(nodes);
    const hint=byId("pathHint"); if(hint) hint.textContent="关系链："+nodes.map(n=>n.zh).join(" → ");
    const clear=byId("pathClear"); if(clear) clear.hidden=false;
  }
  document.addEventListener("teyvat:selectionchange",maybeRunPath);

  /* ── filter chips ─────────────────────────────────────────────── */
  const GROUPS=[
    ["element","filterElement","元素",["风","岩","雷","草","水","火","冰"]],
    ["weapon","filterWeapon","武器",["单手剑","双手剑","长柄武器","弓","法器"]],
    ["region","filterRegion","地区",["蒙德","璃月","稻妻","须弥","枫丹","纳塔","至冬","挪德卡莱","其他"]],
    ["rarity","filterRarity","星级",["五星","四星"]],
  ];
  const chipButtons=new Map(); // group -> Map(value -> button)

  function groupValues(group,order){
    const values=new Set();
    for(const p of state.people.values()){
      const v=p[group]||"";
      if(v) values.add(v);
    }
    const rank=(v)=>{const i=order.indexOf(v);return i<0?99:i;};
    return [...values].sort((a,b)=>rank(a)-rank(b)||a.localeCompare(b,"zh-Hans"));
  }

  function buildChips(){
    for(const [group,id,,order] of GROUPS){
      const host=byId(id);
      if(!host) continue;
      host.replaceChildren();
      const map=new Map();
      for(const value of groupValues(group,order)){
        const chip=mk("button","chip");
        chip.type="button";
        chip.dataset.group=group;
        chip.dataset.value=value;
        chip.dataset[group]=value;
        chip.setAttribute("aria-pressed",String(state.filters[group].has(value)));
        if(group==="element"){
          chip.dataset.el=value;
          chip.style.setProperty("--chip-dot",data.elColor(value));
          chip.appendChild(mk("span","dot"));
        }
        chip.appendChild(mk("span","chip-label",value||"未知"));
        chip.addEventListener("click",()=>{
          data.toggleFilter(group,value);
          chip.setAttribute("aria-pressed",String(state.filters[group].has(value)));
          applyFilterChange();
        });
        host.appendChild(chip);
        map.set(value,chip);
      }
      chipButtons.set(group,map);
    }
  }

  function syncChips(){
    for(const [group,map] of chipButtons){
      const selected=state.filters[group];
      for(const [value,chip] of map) chip.setAttribute("aria-pressed",String(selected.has(value)));
    }
  }

  function applyFilterChange(){
    if(typeof graph?.applyFilters==="function") graph.applyFilters();
    data.saveUi();
    data.updateUrl();
    renderStats();
  }

  /* ── overview stats + top 5 ───────────────────────────────────── */
  function visiblePeople(){
    return [...state.people.values()].filter(p=>data.passesFilters(p));
  }
  function countTo(node,target,decimals=0){
    if(!node) return;
    if(node._countTimer) cancelAnimationFrame(node._countTimer);
    const from=Number(node.textContent)||0;
    if(matchMedia("(prefers-reduced-motion:reduce)").matches){
      node.textContent=target.toFixed(decimals);return;
    }
    const start=performance.now(),dur=420;
    const tick=(now)=>{
      const t=Math.min(1,(now-start)/dur),eased=1-Math.pow(1-t,3);
      node.textContent=(from+(target-from)*eased).toFixed(decimals);
      if(t<1) node._countTimer=requestAnimationFrame(tick);
      else node.textContent=target.toFixed(decimals);
    };
    node._countTimer=requestAnimationFrame(tick);
  }
  function renderStats(){
    const people=visiblePeople();
    const active=people.filter(p=>p.outTotal+p.inTotal>0);
    const ids=new Set(people.map(p=>p.en));
    let edges=0;
    for(const e of state.edges.values()) if(ids.has(e.from)&&ids.has(e.to)) edges++;
    const totalLinks=active.reduce((s,p)=>s+p.outTotal+p.inTotal,0);
    const avg=active.length?Math.round((totalLinks/active.length)*10)/10:0;
    countTo(byId("statNodes"),active.length);
    countTo(byId("statEdges"),edges);
    countTo(byId("statAvg"),avg,1);
    const top=active.slice().sort((a,b)=>b.inTotal-a.inTotal||a.zh.localeCompare(b.zh,"zh-Hans")).slice(0,5);
    const list=byId("topMentioned");
    if(!list) return;
    list.replaceChildren();
    const max=top[0]?.inTotal||1;
    for(const p of top){
      const row=mk("button","mini-row");
      row.type="button";
      row.appendChild(mk("span","mini-name",p.zh));
      const bar=mk("span","bar");
      bar.appendChild(mk("i"));
      bar.firstChild.style.width=Math.round((p.inTotal/max)*100)+"%";
      row.appendChild(bar);
      row.appendChild(mk("b","",data.fmt(p.inTotal)));
      row.setAttribute("aria-label",p.zh+" 被提及 "+p.inTotal+" 次，点击清除筛选并查看档案");
      row.addEventListener("click",()=>{
        data.clearFilters();
        syncChips();
        applyFilterChange();
        focusPerson(p);
      });
      list.appendChild(row);
    }
  }

  /* ── search dropdown ──────────────────────────────────────────── */
  function wireSearch(){
    const input=byId("search"),box=byId("searchResults");
    if(!input||!box) return;
    let active=-1,rows=[];
    const close=()=>{
      box.classList.remove("is-open");box.replaceChildren();active=-1;rows=[];
      input.setAttribute("aria-expanded","false");
    };
    const selectAt=(i)=>{
      const p=rows[i];if(!p) return;
      focusPerson(p,1.4);close();input.blur();
    };
    const render=()=>{
      const term=input.value.trim();
      if(!term){close();return;}
      const hits=[...state.people.values()].filter(p=>data.personMatches(p,term)).slice(0,8);
      rows=hits;box.replaceChildren();
      if(!hits.length){
        box.appendChild(mk("div","empty","没有找到「"+term+"」"));
        box.classList.add("is-open");input.setAttribute("aria-expanded","true");return;
      }
      hits.forEach((p,i)=>{
        const row=mk("div","result-row");
        row.setAttribute("role","option");
        row.id="searchOpt"+i;
        row.setAttribute("aria-selected",String(i===0));
        const avatar=mk("span","result-avatar");
        avatar.style.backgroundImage="url('"+p.img+"')";
        const meta=mk("span","result-meta");
        meta.appendChild(mk("b","",p.zh));
        meta.appendChild(mk("small","",[p.en,p.title,p.region].filter(Boolean).join(" · ")));
        row.append(avatar,meta,mk("span","result-hit",p.outTotal+"说 / "+p.inTotal+"被说"));
        row.addEventListener("click",()=>selectAt(i));
        box.appendChild(row);
      });
      active=0;box.classList.add("is-open");input.setAttribute("aria-expanded","true");
    };
    input.setAttribute("role","combobox");
    input.setAttribute("aria-controls","searchResults");
    input.setAttribute("aria-expanded","false");
    input.addEventListener("input",render);
    input.addEventListener("focus",()=>{if(input.value.trim()&&!box.classList.contains("is-open")) render();});
    input.addEventListener("keydown",(e)=>{
      if(e.key==="ArrowDown"||e.key==="ArrowUp"){
        e.preventDefault();
        if(!rows.length) return;
        active=(active+(e.key==="ArrowDown"?1:-1)+rows.length)%rows.length;
        $$(".result-row",box).forEach((r,i)=>{
          r.classList.toggle("is-active",i===active);
          r.setAttribute("aria-selected",String(i===active));
        });
        byId("searchOpt"+active)?.scrollIntoView({block:"nearest"});
      }else if(e.key==="Enter"){
        e.preventDefault();selectAt(active>=0?active:0);
      }else if(e.key==="Escape"){
        input.value="";close();input.blur();
      }
    });
    box.addEventListener("mousedown",(e)=>e.preventDefault());
    document.addEventListener("pointerdown",(e)=>{
      if(!box.contains(e.target)&&e.target!==input) close();
    });
    document.addEventListener("keydown",(e)=>{
      const tag=(e.target&&e.target.tagName||"").toLowerCase();
      if(e.key==="/"&&!e.ctrlKey&&!e.metaKey&&!e.altKey&&tag!=="input"&&tag!=="textarea"){
        e.preventDefault();input.focus();input.select();
      }
    });
  }

  /* ── layout / index / reset / pair / lang ─────────────────────── */
  function syncLayout(name){
    for(const b of $$("[data-layout]")){
      if(b.getAttribute("role")!=="tab") continue;
      const on=b.dataset.layout===name;
      b.classList.toggle("is-active",on);
      b.setAttribute("aria-selected",String(on));
    }
  }
  function wireLayout(){
    for(const b of $$("[data-layout]")){
      b.addEventListener("click",()=>{
        const name=b.dataset.layout;
        if(!data.LAYOUTS.includes(name)) return;
        if(typeof graph?.applyLayout==="function") graph.applyLayout(name);
        else {state.layout=name;data.saveUi();data.updateUrl();}
        syncLayout(name);
      });
    }
    syncLayout(state.layout);
  }
  function setIndexOpen(open){
    document.body.classList.toggle("index-hidden",!open);
    document.body.classList.toggle("index-open",!!open);
    data.setPanelOpen?.("index",open);
    const t=byId("toggleIndex");
    if(t) t.setAttribute("aria-pressed",String(!!open));
    const fab=byId("fabIndex");
    if(fab) fab.setAttribute("aria-expanded",String(!!open));
  }
  function wireActions(){
    byId("toggleIndex")?.addEventListener("click",()=>setIndexOpen(document.body.classList.contains("index-hidden")));
    byId("fabIndex")?.addEventListener("click",()=>setIndexOpen(true));
    byId("resetView")?.addEventListener("click",()=>{
      if(typeof graph?.resetView==="function") graph.resetView();
      if(typeof dom?.toast==="function") dom.toast("视图已重置");
    });
    byId("randomPair")?.addEventListener("click",()=>{
      if(typeof dossier?.showRandomPair==="function") dossier.showRandomPair();
    });
    byId("langToggle")?.addEventListener("click",()=>{
      if(typeof dossier?.setShowEn==="function") dossier.setShowEn();
      else {state.showEn=!state.showEn;data.saveUi();data.updateUrl();}
      byId("langToggle")?.setAttribute("aria-pressed",String(!!state.showEn));
    });
    byId("pathClear")?.addEventListener("click",()=>{
      state.path=null;
      if(typeof graph?.clearPath==="function") graph.clearPath();
      const hint=byId("pathHint"); if(hint) hint.textContent="在图中依次点选两名角色，查出他们之间最短的关系链。";
      const clear=byId("pathClear"); if(clear) clear.hidden=true;
      data.updateUrl();
    });
    byId("langToggle")?.setAttribute("aria-pressed",String(!!state.showEn));
    setIndexOpen(!window.matchMedia("(max-width:760px)").matches);
    if(window.matchMedia("(max-width:760px)").matches) setIndexOpen(false);
  }

  buildChips();
  renderStats();
  wireSearch();
  wireLayout();
  wireActions();
  return {buildChips,syncChips,renderStats,applyFilterChange,syncLayout,setIndexOpen};
}
