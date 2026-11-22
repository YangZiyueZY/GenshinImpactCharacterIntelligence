/* 提瓦特关系档案馆 — application bootstrap (Editorial Archive rewrite) */
import * as data from "./data.js";
import * as dom from "./dom.js";
const { $, $$ } = dom;
import { initGraph } from "./graph.js";
import { initDossier } from "./dossier.js";
import { initPlayer } from "./player.js";
import { initIndexPanel } from "./index-panel.js";

async function main(){
  const boot = $("#boot .boot-inner p");
  try { await data.loadAll(); }
  catch(e){ if(boot) boot.textContent = "加载数据失败：" + e.message; return; }
  await data.preloadImages([...data.state.people.values()].map(p=>p.img));

  const ctx = { state:data.state, data, dom };
  const graph = initGraph(ctx); ctx.graph = graph;
  const dossier = initDossier(ctx); ctx.dossier = dossier;
  const player = initPlayer(ctx); ctx.player = player;
  const indexPanel = initIndexPanel(ctx); ctx.indexPanel = indexPanel;

  graph.build();
  const { focused } = data.readUrl();
  graph.applyLayout(data.state.layout, false);
  if(data.state.showEn) document.body.classList.add("show-en");
  dossier.render();
  if(focused) dossier.open();
  graph.highlightSelection();
  setTimeout(()=>graph.fitGraph(), 80);
  setTimeout(()=>graph.resetView && 0, 0);

  $$(".layout-tabs [data-layout], .mobile-layout-switch [data-layout]").forEach(b=>{
    const on = b.dataset.layout === data.state.layout;
    b.classList.toggle("is-active", on);
    b.setAttribute("aria-selected", String(on));
  });

  document.addEventListener("keydown", e=>{
    if(e.key==="Escape"){
      if($("#quoteCard")?.classList.contains("is-show")){
        $("#quoteCard").classList.remove("is-show");
        $("#quoteCard").setAttribute("aria-hidden","true");
      } else if($("#searchResults")?.classList.contains("is-open")){
        $("#searchResults").classList.remove("is-open");
        $("#search")?.blur();
      } else if(document.body.classList.contains("index-open")){
        document.body.classList.remove("index-open");
      } else if(data.state.selected.length){
        data.state.selected.pop();
        dossier.render(); graph.highlightSelection(); data.updateUrl();
      }
    }
  });
  window.addEventListener("resize", ()=>{ if(graph.cy) graph.cy.resize(); }, {passive:true});
  window.addEventListener("orientationchange", ()=>{ setTimeout(()=>{ if(graph.cy){ graph.cy.resize(); graph.fitGraph(); } },220); }, {passive:true});

  window.__app = { state:data.state, cy:graph.cy, graph, dossier, player, indexPanel,
    selectPerson: dossier.selectPerson, applyLayout: graph.applyLayout };
  requestAnimationFrame(()=>$("#boot")?.classList.add("is-done"));
  setTimeout(()=>$("#boot")?.remove(), 900);
}
document.addEventListener("DOMContentLoaded", main);
