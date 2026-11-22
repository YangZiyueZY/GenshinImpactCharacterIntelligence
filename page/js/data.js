/* 提瓦特关系档案馆 — data layer (Editorial Archive rewrite) */
export const KEY = "genshin-relations-ui";
export const ELEMENT_COLOR = { 风:"#4E8C6B", 岩:"#9A7430", 雷:"#5E6785", 草:"#5E7C3A", 水:"#3F7590", 火:"#B14E34", 冰:"#4A8192", "":"#7A7568" };
export const ELEMENT_LABEL = { 风:"风", 岩:"岩", 雷:"雷", 草:"草", 水:"水", 火:"火", 冰:"冰" };
export const LANG_LABEL = { zh:"中配", ja:"日配", en:"英配", ko:"韩配" };
export const SOURCE_LABEL = { hoyolab:"HoYoLab", biligame:"B站wiki" };
export const LAYOUTS = ["fcose","concentric","avsdf","grid"];

export const state = {
  base:"", chars:[], profile:{}, aliases:{},
  people:new Map(), byZh:new Map(), slugTo:new Map(),
  edges:new Map(), outMap:new Map(), inMap:new Map(), voice:new Map(),
  selected:[], path:null,
  filters:{ element:new Set(), weapon:new Set(), region:new Set(), rarity:new Set() },
  layout:"fcose", drawerTab:"voice", lang:"zh", source:"hoyolab", showEn:false,
  audio:{ item:null, lang:"zh", source:"hoyolab", autoplay:false },
};

const $ = (sel, root=document) => root.querySelector(sel);
const slugify = s => (s||"").toLowerCase().replace(/['’·]/g,"").replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"");
const fetchJson = async url => { const r = await fetch(url,{cache:"force-cache"}); if(!r.ok) throw new Error("HTTP "+r.status+" "+url); return r.json(); };

export function elColor(el){ return ELEMENT_COLOR[el] || ELEMENT_COLOR[""]; }
export function fmt(n){ return Number(n||0).toLocaleString("zh-CN"); }

export async function loadAll(){
  const local = ["localhost","127.0.0.1",""].includes(location.hostname) || location.protocol === "file:";
  const inPageDir = local || /\/page\/?$/.test(location.pathname);
  state.base = inPageDir ? "../data/" : "data/";
  const full = state.base.includes("..");
  const [charData, profile, aliases] = await Promise.all([
    fetchJson(state.base + (full ? "char_data.json" : "char_data_min.json")),
    fetchJson(state.base + "profile.json").catch(()=>({})),
    fetchJson(state.base + "alias.json").catch(()=>({})),
  ]);
  state.chars = charData; state.profile = profile; state.aliases = aliases;
  for(const c of charData){
    const prof = profile[c.name_zh] || {};
    const p = { id:c.id, zh:c.name_zh, en:c.name_en, slug:slugify(c.name_en||c.name_zh),
      img:state.base+"image/"+encodeURIComponent(c.name_zh)+".png",
      bg:'url("'+state.base+"image/"+encodeURIComponent(c.name_zh)+'.png")',
      ver:c.ver||"", element:prof.element||"", weapon:prof.weapon||"", region:prof.region||"",
      rarity:prof.rarity||"", title:prof.title||"", affiliation:prof.affiliation||"",
      birthday:prof.birthday||"", constellation:prof.constellation||"", release:prof.release||"",
      cv:{zh:prof.cv_zh,ja:prof.cv_ja,en:prof.cv_en,ko:prof.cv_ko}, lines:c.lines||[], outTotal:0, inTotal:0 };
    state.people.set(p.en,p); state.byZh.set(p.zh,p); state.slugTo.set(p.slug,p);
    state.outMap.set(p.en,new Map()); state.inMap.set(p.en,new Map());
  }
  for(const p of state.people.values()){
    p.lines.forEach((l,i)=>{ l.__index=i; });
    for(const l of p.lines){
      const to=l.target_en, target=state.people.get(to); if(!target) continue;
      const key=p.en+"|"+to; let e=state.edges.get(key);
      if(!e){ e={from:p.en,to,lines:[]}; state.edges.set(key,e); }
      e.lines.push(l); p.outTotal++; target.inTotal++;
      if(!state.outMap.get(p.en).has(to)) state.outMap.get(p.en).set(to,[]);
      state.outMap.get(p.en).get(to).push(l);
      if(!state.inMap.get(to).has(p.en)) state.inMap.get(to).set(p.en,[]);
      state.inMap.get(to).get(p.en).push(l);
    }
  }
}

export async function loadVoice(person){
  if(state.voice.has(person.zh)) return state.voice.get(person.zh);
  try { const v = await fetchJson(state.base+"voice/"+encodeURIComponent(person.zh)+".json"); state.voice.set(person.zh,v); return v; }
  catch(e){ state.voice.set(person.zh,null); return null; }
}
export function aliasesOf(p){ const a=state.aliases[p.zh]; return a ? [...(a.alias_zh||[]),...(a.alias_en||[])] : []; }
export function personMatches(p,term){
  if(!term) return true;
  const t=term.toLowerCase();
  return p.zh.includes(term)||p.en.toLowerCase().includes(t)||(p.title&&p.title.toLowerCase().includes(t))||aliasesOf(p).some(x=>x.toLowerCase().includes(t));
}
export function slugForName(term){
  const t=(term||"").trim().toLowerCase(); if(!t) return null;
  for(const p of state.people.values()) if(p.en.toLowerCase()===t||p.zh===term.trim()||p.slug===t) return p;
  return null;
}
export function activeFilters(){ return Object.values(state.filters).some(s=>s.size>0); }
export function passesFilters(p){
  const f=state.filters;
  if(f.element.size && !f.element.has(p.element||"")) return false;
  if(f.weapon.size && !f.weapon.has(p.weapon||"")) return false;
  if(f.region.size && !f.region.has(p.region||"")) return false;
  if(f.rarity.size && !f.rarity.has(p.rarity||"")) return false;
  return true;
}
export function setFilter(group,value,on){ if(!state.filters[group]) return; on?state.filters[group].add(value):state.filters[group].delete(value); }
export function toggleFilter(group,value){ const s=state.filters[group]; if(!s) return; s.has(value)?s.delete(value):s.add(value); }
export function clearFilters(){ for(const s of Object.values(state.filters)) s.clear(); }
export function filterSummary(){
  const parts=[];
  for(const [g,label] of [["element","元素"],["weapon","武器"],["region","地区"],["rarity","星级"]]){
    const s=state.filters[g]; if(s.size) parts.push(label+" "+s.size);
  }
  return parts.length ? parts.join(" · ") : "全部";
}
export function saveUi(){
  try { localStorage.setItem(KEY,JSON.stringify({layout:state.layout,lang:state.lang,source:state.source,showEn:state.showEn,tab:state.drawerTab})); } catch(e){}
}
export function loadUi(){ try { return JSON.parse(localStorage.getItem(KEY)||"{}")||{}; } catch(e){ return {}; } }
export function updateUrl(){
  const p=new URLSearchParams(location.search);
  const a=state.selected[0]?.slug, b=state.selected[1]?.slug;
  if(a) p.set("a",a); else p.delete("a");
  if(b) p.set("b",b); else p.delete("b");
  p.set("layout",state.layout);
  if(state.drawerTab!=="voice") p.set("tab",state.drawerTab); else p.delete("tab");
  history.replaceState(null,"","?"+p.toString());
}
export function readUrl(){
  const p=new URLSearchParams(location.search);
  const a=p.get("a"), b=p.get("b");
  state.layout = LAYOUTS.includes(p.get("layout")) ? p.get("layout") : (loadUi().layout||"fcose");
  if(p.get("tab")) state.drawerTab=p.get("tab");
  const pa=a?state.slugTo.get(a)||slugForName(a):null;
  const pb=b?state.slugTo.get(b)||slugForName(b):null;
  if(pa) state.selected.push(pa);
  if(pb&&pb!==pa) state.selected.push(pb);
  return { focused:Boolean(pa) };
}
export function preloadImages(urls,concurrency=8){
  return new Promise(resolve=>{ let i=0,active=0,done=0; const total=urls.length; if(!total) return resolve();
    const next=()=>{ while(active<concurrency&&i<total){ const url=urls[i++]; active++; const img=new Image();
      const fin=()=>{ active--; done++; done===total?resolve():next(); }; img.onload=fin; img.onerror=fin; img.src=url; } }; next(); });
}
