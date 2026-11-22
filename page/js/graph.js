/* 提瓦特关系档案馆 — graph plate (Editorial Archive rewrite) */
export function initGraph(ctx){
  const { state, data, dom } = ctx;
  const { $, $$, el, icon, toast } = dom;
  let cy = null, gridInfo = null, gridLabelLayer = null, concentricBusy = 0, nudgeTimer = null;
  const cyHost = $("#cy");
  if(!cyHost) return { cy:null, build(){}, applyLayout(){}, applyFilters(){}, resetView(){}, fitGraph(){}, focusPerson(){}, highlightSelection(){}, showPath(){}, clearPath(){}, setViewportToIds(){}, showEdgeCard(){}, hideEdgeCard(){} };

  const isNarrow = () => window.matchMedia("(max-width: 760px)").matches;
  const cap = () => Math.min(window.devicePixelRatio || 1, isNarrow() ? 1.25 : 1.5);
  const LEVEL = deg => { const d=+deg||0; if(d<=0) return 1; if(d<=2) return 2; if(d<=4) return 3; if(d<=7) return 4; if(d<=11) return 5; if(d<=16) return 6; if(d<=24) return 7; return 8; };
  const NODE_PITCH = 74;

  function concentricLayout(){
    const centre = state.selected[state.selected.length-1] || null;
    const buckets = new Map();
    const add=(r,p)=>{ if(!buckets.has(r)) buckets.set(r,[]); buckets.get(r).push(p); };
    if(centre){
      for(const p of state.people.values()){
        if(p.en===centre.en) continue;
        const shared=(state.outMap.get(centre.en)?.get(p.en)||[]).length+(state.outMap.get(p.en)?.get(centre.en)||[]).length;
        add(shared>0?Math.max(1,Math.min(4,Math.ceil(shared/3))):5,p);
      }
    } else {
      for(const p of state.people.values()) add(LEVEL(p.outTotal+p.inTotal),p);
    }
    const pos={}; if(centre) pos[centre.en]={x:0,y:0};
    const rings=[...buckets.entries()].sort((a,b)=>a[0]-b[0]);
    let radius=centre?120:0, lastConnected=radius;
    rings.forEach(([ring,group],index)=>{
      group.sort((a,b)=>(b.outTotal+b.inTotal)-(a.outTotal+a.inTotal)||a.en.localeCompare(b.en));
      const needed=(NODE_PITCH*group.length)/(2*Math.PI);
      if(index===0&&!centre){
        const discR=Math.max(110,NODE_PITCH*Math.sqrt(group.length/Math.PI));
        const golden=Math.PI*(3-Math.sqrt(5));
        group.forEach((p,i)=>{ const r=discR*Math.sqrt((i+.5)/group.length), a=i*golden; pos[p.en]={x:Math.cos(a)*r,y:Math.sin(a)*r}; });
        radius=discR; return;
      }
      const step=centre?150:170;
      if(!(centre&&ring===5)) lastConnected=Math.max(radius,needed);
      radius=Math.max(radius+step,needed);
      if(centre&&ring===5) radius=Math.max(needed*.8,lastConnected*1.5+160);
      group.forEach((p,i)=>{ const a=-Math.PI/2+(i/Math.max(1,group.length))*Math.PI*2; pos[p.en]={x:Math.cos(a)*radius,y:Math.sin(a)*radius}; });
    });
    return pos;
  }

  function gridLayout(){
    const COL=88, ROW=108, GROUP_GAP=1;
    const groups=new Map();
    for(const p of state.people.values()){
      const ver=p.ver||"1.0"; const parts=String(ver==="1.0"?"0.0.1":ver).split(".").map(Number);
      const major=parts[0]||0; if(!groups.has(major)) groups.set(major,[]);
      groups.get(major).push({p,minor:parts[1]||0,patch:parts[2]||0});
    }
    const majors=[...groups.keys()].sort((a,b)=>a-b), pos={}, rows=[]; let row=0;
    for(const major of majors){
      const list=groups.get(major).sort((a,b)=>a.minor-b.minor||a.patch-b.patch||a.p.en.localeCompare(b.p.en));
      let col=0, prev=null;
      for(const g of list){ if(prev!==null&&g.minor!==prev) col+=GROUP_GAP; pos[g.p.en]={x:col*COL,y:row*ROW}; col++; prev=g.minor; }
      rows.push({row,label:major===0?"开服前":"v"+major+".x",count:list.length}); row++;
    }
    return {pos,rows,COL,ROW};
  }

  function buildStyle(){
    const ink="#17140F", paper="#F2ECE0", seal="#A63E2E", teal="#2B4A52", rule="rgba(23,20,15,.6)";
    return [
      { selector:"node", style:{
        width:50,height:50,"background-image":"data(bg)","background-fit":"cover","background-color":paper,
        "border-width":1.4,"border-color":"data(elColor)","shape":"ellipse",
        "shadow-blur":0,"shadow-opacity":0,"overlay-opacity":0,label:"",color:ink,
        "font-family":"Songti SC, serif","font-size":11,"text-valign":"bottom","text-margin-y":5,
        "text-outline-color":paper,"text-outline-width":2.4,"text-outline-opacity":.95,
      }},
      { selector:"node.hl", style:{ label:"data(nameZh)","border-width":2.4,width:62,height:62,"z-index":30,
        "underlay-color":teal,"underlay-opacity":.1,"underlay-padding":7 }},
      { selector:"node.sel", style:{ label:"data(nameZh)","border-color":seal,"border-width":2.8,width:72,height:72,"z-index":40,
        "underlay-color":seal,"underlay-opacity":.12,"underlay-padding":10 }},
      { selector:"node.onpath", style:{ "border-color":seal,"border-width":2.4,width:64,height:64,label:"data(nameZh)","z-index":35 }},
      { selector:"node.dim", style:{opacity:.14} },
      { selector:"edge", style:{
        width:"mapData(strength,1,5,0.6,2.2)","line-color":"data(edgeColor)","target-arrow-color":"data(edgeColor)",
        "target-arrow-shape":"triangle","arrow-scale":.62,"curve-style":"bezier","control-point-step-size":40,opacity:.28,
      }},
      { selector:"edge.hl", style:{opacity:.95,"line-color":seal,"target-arrow-color":seal,"z-index":10} },
      { selector:"edge.inhl", style:{opacity:.6,"line-color":teal,"target-arrow-color":teal} },
      { selector:"edge.dim", style:{opacity:.05} },
      { selector:"edge.onpath", style:{opacity:1,"line-color":seal,"target-arrow-color":seal,width:3,"z-index":20} },
      { selector:".hidden", style:{display:"none"} },
    ];
  }

  function build(){
    if(cy){ cy.destroy(); cy=null; }
    const nodes=[], edges=[];
    for(const p of state.people.values()){
      nodes.push({group:"nodes",data:{id:p.en,nameZh:p.zh,nameEn:p.en,img:p.img,bg:p.bg,
        elColor:data.elColor(p.element),degree:p.outTotal+p.inTotal,ver:p.ver}});
    }
    for(const e of state.edges.values()){
      const count=e.lines.length;
      edges.push({group:"edges",data:{id:e.from+"__"+e.to,source:e.from,target:e.to,
        count,strength:Math.min(count,5),edgeColor:data.elColor((state.people.get(e.to)||{}).element)}});
    }
    cy = cytoscape({ container:cyHost, elements:[...nodes,...edges], boxSelectionEnabled:false,
      minZoom:.08,maxZoom:3,wheelSensitivity:.22,pixelRatio:cap(),style:buildStyle(),layout:{name:"preset"} });
    cy.on("mouseover","node",evt=>{ evt.target.addClass("hl"); });
    cy.on("mouseout","node",evt=>evt.target.removeClass("hl"));
    cy.on("tap","node",evt=>{ evt.stopPropagation(); const p=state.byZh.get(evt.target.data("nameZh")); if(p) ctx.dossier?.selectPerson(p); });
    cy.on("mouseover","edge",evt=>{ const e=evt.target; e.addClass("hl"); const oe=evt.originalEvent||{}; showEdgeCard(e,{x:oe.clientX||0,y:oe.clientY||0}); });
    cy.on("mouseout","edge",evt=>{ evt.target.removeClass("hl"); scheduleTipHide(); });
    cy.on("tap","edge",evt=>{ evt.stopPropagation(); const e=evt.target; const oe=evt.originalEvent||{}; showEdgeCard(e,{x:oe.clientX||window.innerWidth/2,y:oe.clientY||window.innerHeight/2},true); });
    cy.on("tap",evt=>{ if(evt.target===cy) ctx.dossier?.clearSelection(); });
    renderLegend();
  }

  function renderLegend(){
    const host=$("#legend"); if(!host) return;
    host.replaceChildren();
    for(const [code,color] of Object.entries(data.ELEMENT_COLOR)){
      if(!code) continue;
      const item=el("span","legend-item"); const sw=el("i","legend-swatch"); sw.style.background=color;
      item.append(sw,el("span",null,code)); host.append(item);
    }
    host.append(el("span","legend-note","连线 = 语音中的「关于…」评价 · 粗细代表条数"));
  }

  function nudgeRepaint(delay=0){
    clearTimeout(nudgeTimer);
    nudgeTimer=setTimeout(()=>{
      if(!cy) return; cy.resize();
      try { const r=cy.renderer(); if(r&&typeof r.redraw==="function") r.redraw(); } catch(e){}
      const z=cy.zoom(), c={x:cy.width()/2,y:cy.height()/2};
      cy.zoom({level:z*1.0015,renderedPosition:c}); cy.zoom({level:z,renderedPosition:c});
    },delay);
  }

  function ensureGridLabels(){
    if(gridLabelLayer&&gridLabelLayer.isConnected) return gridLabelLayer;
    gridLabelLayer=el("div","row-labels"); $("#stage").appendChild(gridLabelLayer);
    cy?.on("viewport",renderGridLabels); return gridLabelLayer;
  }
  function renderGridLabels(){
    if(state.layout!=="grid"||!gridInfo||!cy) return;
    const layer=ensureGridLabels();
    if(layer.childElementCount!==gridInfo.rows.length){
      layer.replaceChildren();
      for(const r of gridInfo.rows) layer.appendChild(el("span","row-label",r.label));
    }
    const zoom=cy.zoom(), pan=cy.pan(), kids=layer.children;
    for(let i=0;i<gridInfo.rows.length;i++){
      const node=kids[i]; if(!node) continue;
      const x=-120*zoom+pan.x, y=gridInfo.rows[i].row*gridInfo.ROW*zoom+pan.y;
      node.style.transform="translate3d("+Math.round(x)+"px,"+Math.round(y)+"px,0) translateY(-50%)";
    }
  }
  function clearGridLabels(){ if(gridLabelLayer) gridLabelLayer.replaceChildren(); }

  function setViewportToIds(ids,padding=90){
    if(!cy) return;
    const box={x1:Infinity,y1:Infinity,x2:-Infinity,y2:-Infinity};
    for(const id of ids){ const n=cy.getElementById(id); if(!n||!n.length) continue; const p=n.position();
      box.x1=Math.min(box.x1,p.x); box.y1=Math.min(box.y1,p.y); box.x2=Math.max(box.x2,p.x); box.y2=Math.max(box.y2,p.y); }
    if(!isFinite(box.x1)) return;
    const w=Math.max(1,box.x2-box.x1), h=Math.max(1,box.y2-box.y1), pad=padding*2;
    const level=Math.max(cy.minZoom(),Math.min(cy.maxZoom(),Math.min((cy.width()-pad)/w,(cy.height()-pad)/h)));
    const cx=(box.x1+box.x2)/2, cyMid=(box.y1+box.y2)/2;
    cy.zoom({level}); cy.pan({x:cy.width()/2-cx*level,y:cy.height()/2-cyMid*level});
  }
  function fitGraph(){ if(cy) cy.animate({fit:{eles:cy.elements(),padding:70},duration:420,easing:"ease-in-out"}); }
  function applyFilters(){
    if(!cy) return;
    for(const p of state.people.values()) cy.getElementById(p.en)?.toggleClass("hidden",!data.passesFilters(p));
    nudgeRepaint(120);
  }
  function applyLayout(name,animate=true){
    if(!cy) return;
    state.layout=name;
    $$(".layout-tabs [data-layout], .mobile-layout-switch [data-layout]").forEach(b=>{
      const on=b.dataset.layout===name; b.classList.toggle("is-active",on); b.setAttribute("aria-selected",String(on));
    });
    const title=$("#plateTitle"), sub=$("#plateSub"), no=$("#plateNo");
    const meta={
      fcose:["星图","I","力导向布局 · 节点为角色，连线为语音中的「关于…」评价"],
      concentric:["同心","II","连通度决定环序 · 选中角色后以其为圆心重排"],
      avsdf:["环列","III","圆周排布 · 交叉最小化"],
      grid:["年表","IV","按实装版本成行 · 连线跨越时间"]
    }[name]||["星图","I",""];
    if(title) title.textContent=meta[0]; if(no) no.textContent=meta[1]; if(sub) sub.textContent=meta[2];
    document.body.dataset.layout=name;
    if(name==="fcose"){
      if(Math.seedrandom) Math.seedrandom("teyvat");
      cy.layout({name:"fcose",animate,animationDuration:700,randomize:true,nodeSeparation:170,
        idealEdgeLength:()=>112,nodeRepulsion:()=>62000,edgeElasticity:()=>.12,gravity:.28,numIter:1200}).run();
    } else if(name==="concentric"){
      concentricBusy=Date.now()+2000;
      const pos=concentricLayout();
      cy.layout({name:"preset",animate,animationDuration:700,positions:n=>pos[n.id()]||{x:0,y:0},fit:false}).run();
      cy.fit(cy.nodes(),90); nudgeRepaint(animate?800:160);
    } else if(name==="avsdf"){
      cy.layout({name:"avsdf",animate,animationDuration:700,nodeSeparation:90}).run();
    } else {
      gridInfo=gridLayout();
      cy.layout({name:"preset",animate,animationDuration:700,positions:n=>gridInfo.pos[n.id()]||{x:0,y:0},fit:true,padding:70}).run();
      renderGridLabels();
    }
    if(name!=="grid") clearGridLabels();
    if(name!=="concentric") nudgeRepaint(animate?900:260);
    setTimeout(()=>cy?.resize(),260);
    data.saveUi?.();
  }
  function resetView(){ clearPath(); ctx.dossier?.clearSelection(); applyLayout(state.layout); fitGraph(); }
  function focusPerson(person){ if(!cy||!person) return; const n=cy.getElementById(person.en); if(n&&n.length) cy.animate({center:{eles:n},zoom:1.2,duration:520}); }
  function highlightSelection(){
    if(!cy) return;
    cy.elements().removeClass("sel hl dim inhl onpath");
    const focus=state.selected[state.selected.length-1];
    if(!focus) return;
    cy.getElementById(focus.en)?.addClass("sel");
    for(const n of cy.nodes()){
      const p=state.people.get(n.id()); if(!p||p.en===focus.en) continue;
      const shared=(state.outMap.get(focus.en)?.get(p.en)||[]).length+(state.outMap.get(p.en)?.get(focus.en)||[]).length;
      const rev=(state.inMap.get(focus.en)?.has(p.en));
      if(shared||rev) n.addClass("inhl");
    }
    cy.edges().forEach(e=>{
      const s=e.source().id(),t=e.target().id();
      if(s===focus.en||t===focus.en) e.addClass("hl");
    });
    if(state.layout==="concentric"&&Date.now()>=concentricBusy){
      concentricBusy=Date.now()+1600;
      const pos=concentricLayout();
      cy.layout({name:"preset",animate:true,animationDuration:620,positions:n=>pos[n.id()]||{x:0,y:0},fit:false}).run();
      cy.fit(cy.nodes(),90); nudgeRepaint(700);
    }
  }
  function showPath(nodes){
    if(!cy||!nodes?.length) return;
    cy.elements().removeClass("onpath");
    nodes.forEach(n=>cy.getElementById(n.en||n)?.addClass("onpath"));
    const bar=$("#pathbar"); if(!bar) return;
    bar.replaceChildren(); bar.hidden=false;
    nodes.forEach((n,i)=>{
      if(i){ const arrow=el("span","path-arrow","→"); bar.append(arrow); }
      const p=typeof n==="string"?state.people.get(n):n; if(!p) return;
      const img=el("img"); img.src=p.img; img.alt="";
      const wrap=el("span","path-node"); wrap.append(img,el("span",null,p.zh)); bar.append(wrap);
    });
    const close=el("button","path-close","×"); close.type="button"; close.setAttribute("aria-label","清除关系链");
    close.addEventListener("click",clearPath); bar.append(close);
    setViewportToIds(nodes.map(n=>typeof n==="string"?n:n.en),110);
    if(typeof dom.toast==="function") dom.toast("关系链：中间隔 "+(nodes.length-2)+" 个角色");
  }
  function clearPath(){ if(cy) cy.elements().removeClass("onpath"); const bar=$("#pathbar"); if(bar){ bar.hidden=true; bar.replaceChildren(); } }

  let tipTimer=null;
  function scheduleTipHide(){ clearTimeout(tipTimer); tipTimer=setTimeout(hideEdgeCard,260); }
  function hideEdgeCard(){ const c=$("#quoteCard"); if(c){ c.classList.remove("is-show"); c.setAttribute("aria-hidden","true"); } }
  function showEdgeCard(edge,pos,pinned=false){
    const card=$("#quoteCard"); if(!card||!cy) return;
    const from=state.people.get(edge.source().id()), to=state.people.get(edge.target().id());
    if(!from||!to) return;
    const count=edge.data("count")||0;
    card.replaceChildren();
    card.append(el("div","quote-head",from.zh+" → "+to.zh),el("div","quote-sub",count+" 条关于 TA 的语音证言"));
    const lines=state.outMap.get(from.en)?.get(to.en)||[];
    lines.slice(0,2).forEach(l=>{ const q=el("div","quote-line",l.content_zh||""); card.append(q); });
    card.style.left=Math.min(pos.x+14,window.innerWidth-360)+"px";
    card.style.top=Math.min(pos.y+14,window.innerHeight-180)+"px";
    card.classList.add("is-show"); card.setAttribute("aria-hidden","false");
    clearTimeout(tipTimer);
    if(!pinned) tipTimer=setTimeout(hideEdgeCard,2200);
  }

  // zoom controls
  $("#zoomIn")?.addEventListener("click",()=>cy?.zoom({level:Math.min(3,(cy.zoom()||1)*1.25)}));
  $("#zoomOut")?.addEventListener("click",()=>cy?.zoom({level:Math.max(.08,(cy.zoom()||1)/1.25)}));
  cyHost.addEventListener("wheel",()=>setTimeout(()=>{ const z=$("#zoomLevel"); if(z&&cy) z.textContent=Math.round(cy.zoom()*100)+"%"; },80),{passive:true});

  return { get cy(){ return cy; }, build, applyLayout, applyFilters, resetView, fitGraph, focusPerson, highlightSelection, showPath, clearPath, setViewportToIds, showEdgeCard, hideEdgeCard };
}
