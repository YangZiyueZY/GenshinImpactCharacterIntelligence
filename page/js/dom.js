/* 提瓦特关系档案馆 — DOM helpers */
export const $ = (sel, root=document) => root.querySelector(sel);
export const $$ = (sel, root=document) => Array.from(root.querySelectorAll(sel));
export function el(tag, cls, text){
  const n=document.createElement(tag);
  if(cls) n.className=cls;
  if(text!==undefined && text!==null) n.textContent=text;
  return n;
}
export function icon(id, cls){
  const ns="http://www.w3.org/2000/svg";
  const svg=document.createElementNS(ns,"svg");
  svg.setAttribute("class","ico"+(cls?" "+cls:""));
  svg.setAttribute("aria-hidden","true");
  const use=document.createElementNS(ns,"use");
  use.setAttribute("href","vendor/icons.svg#"+id);
  svg.appendChild(use);
  return svg;
}
export function toast(msg, ms=2200){
  const node=$("#toast"); if(!node) return;
  node.textContent=msg; node.classList.add("is-show");
  clearTimeout(toast._t); toast._t=setTimeout(()=>node.classList.remove("is-show"),ms);
}
export function setPanelOpen(name, open){
  const body=document.body;
  if(name==="index"){ body.classList.toggle("index-open",!!open); const b=$("#fabIndex"); if(b) b.setAttribute("aria-expanded",String(!!open)); }
  if(name==="dossier"){ const d=$("#dossier"); if(d){ d.classList.toggle("is-open",!!open); d.setAttribute("aria-hidden",String(!open)); } body.classList.toggle("dossier-open",!!open); }
}
