/* 提瓦特关系档案馆 — dossier controller (Editorial Archive rewrite)
 * Owns: #dossierBody content, sheet drag, three tabs, side-by-side compare.
 * Depends only on ctx = {state, data, dom, graph, player}.
 */
export function initDossier(ctx) {
  const { state, data, dom, graph } = ctx;
  const playerRef = () => ctx.player;
  const { $, $$, el, icon, toast } = dom;
  const { LANG_LABEL, SOURCE_LABEL } = data;
  const dossier = $("#dossier");
  const body = $("#dossierBody");
  const grip = $("#dossierGrip");
  const closeBtn = $("#dossierClose");
  let renderSerial = 0;

  const pickAudio = (item, source, lang) => {
    if (!item || !item.audios) return null;
    const preferred = source === "hoyolab" ? ["hoyolab", "biligame"] : ["biligame", "hoyolab"];
    const primary = "zh";
    const fallback = lang === "zh" ? ["ja", "en", "ko"] : [lang, "zh", "ja", "en", "ko"];
    for (const src of preferred) {
      const langs = item.audios[src];
      if (!langs) continue;
      if (langs[lang]) return { url: langs[lang], source: src, lang };
      for (const l of fallback) if (langs[l]) return { url: langs[l], source: src, lang: l };
      if (langs[primary]) return { url: langs[primary], source: src, lang: primary };
    }
    return null;
  };

  function badge(text, cls) {
    return el("span", "badge" + (cls ? " " + cls : ""), text);
  }

  function open() {
    if (!dossier) return;
    dossier.classList.add("is-open");
    dossier.setAttribute("aria-hidden", "false");
    document.body.classList.add("dossier-open");
  }
  function close() {
    if (!dossier) return;
    dossier.classList.remove("is-open");
    dossier.setAttribute("aria-hidden", "true");
    document.body.classList.remove("dossier-open");
  }

  function selectPerson(person) {
    if (!person) return;
    const idx = state.selected.findIndex((p) => p && p.en === person.en);
    if (idx === 0) { clearSelection(); return; }
    if (idx > 0) state.selected = [state.selected[0]];
    else state.selected.push(person);
    if (state.selected.length > 2) state.selected = state.selected.slice(-2);
    if (graph && typeof graph.highlightSelection === "function") graph.highlightSelection();
    render();
    data.updateUrl();
    open();
  }

  function clearSelection() {
    state.selected = [];
    if (graph && typeof graph.highlightSelection === "function") graph.highlightSelection();
    close();
    if (body) body.replaceChildren();
    data.updateUrl();
  }

  function setShowEn() {
    state.showEn = !state.showEn;
    document.body.classList.toggle("show-en", state.showEn);
    data.saveUi();
    render();
    return state.showEn;
  }

  function markPlaying(item) {
    $$(".voice", body).forEach((row) => row.classList.toggle("is-playing", row.dataset.key === String(item?.title)));
  }

  function render() {
    document.dispatchEvent(new CustomEvent("teyvat:selectionchange", { detail: { count: state.selected.length } }));
    if (!body) return;
    if (!state.selected.length) { close(); body.replaceChildren(); return; }
    open();
    if (state.selected.length === 2) renderCompare(body, state.selected[0], state.selected[1]);
    else renderDetail(body, state.selected[0]);
  }

  function renderDetail(host, person) {
    host.replaceChildren();
    if (!person) return;
    const hero = el("div", "hero");
    const av = el("div", "hero-avatar");
    av.style.backgroundImage = "url('" + person.img + "')";
    const meta = el("div", "hero-meta");
    const name = el("div", "hero-name");
    name.append(el("h1", null, person.zh), el("span", "en", person.en));
    const badges = el("div", "hero-badges");
    if (person.element) {
      const b = badge(data.ELEMENT_LABEL[person.element] || person.element, "el");
      b.style.setProperty("--el-color", data.elColor(person.element));
      badges.append(b);
    }
    if (person.weapon) badges.append(badge(person.weapon));
    if (person.region) badges.append(badge(person.region));
    if (person.rarity) badges.append(badge(person.rarity, "star"));
    if (person.ver) badges.append(badge("v" + person.ver, "ver"));
    meta.append(name, badges);
    hero.append(av, meta);
    host.append(hero);

    const facts = el("dl", "facts");
    const rows = [
      ["称号", person.title], ["所属", person.affiliation], ["生日", person.birthday],
      ["命之座", person.constellation], ["实装", person.release || person.ver],
    ].filter(([, v]) => v);
    rows.forEach(([k, v], i) => {
      const cell = el("div", "fact");
      cell.style.animationDelay = (40 * i) + "ms";
      cell.append(el("dt", null, k), el("dd", null, v));
      facts.append(cell);
    });
    if (rows.length) host.append(facts);

    const cv = el("div", "cv-row");
    for (const [code, label] of Object.entries(LANG_LABEL)) {
      const nm = person.cv?.[code];
      if (!nm) continue;
      const span = el("span", "cv");
      span.append(el("b", null, label + " CV"), document.createTextNode(" " + nm));
      cv.append(span);
    }
    if (cv.children.length) host.append(cv);

    const tabs = el("div", "tabs");
    tabs.setAttribute("role", "tablist");
    const panelId = "dossierPanel";
    const defs = [
      ["voice", "语音", (state.voice.get(person.zh)?.items || []).length],
      ["mentions", "提及 TA", person.outTotal],
      ["mentioned", "被 TA 提及", person.inTotal],
    ];
    defs.forEach(([key, label, count]) => {
      const b = el("button", "tab" + (state.drawerTab === key ? " is-active" : ""));
      b.type = "button";
      b.dataset.tab = key;
      b.setAttribute("role", "tab");
      b.setAttribute("aria-selected", String(state.drawerTab === key));
      b.setAttribute("aria-controls", panelId);
      b.append(el("span", null, label), el("span", "count", count ? "(" + count + ")" : ""));
      b.addEventListener("click", () => {
        state.drawerTab = key;
        data.saveUi();
        data.updateUrl();
        render();
      });
      tabs.append(b);
    });
    tabs.addEventListener("keydown",(ev)=>{
      const keys=["ArrowLeft","ArrowRight","Home","End"];
      if(!keys.includes(ev.key)) return;
      ev.preventDefault();
      const list=defs.map(x=>x[0]);
      const cur=list.indexOf(state.drawerTab);
      const next=ev.key==="Home"?0:ev.key==="End"?list.length-1:(cur+(ev.key==="ArrowRight"?1:-1)+list.length)%list.length;
      state.drawerTab=list[next]; data.saveUi(); data.updateUrl(); render();
      const nb=host.querySelector('[role="tab"][aria-selected="true"]'); if(nb) nb.focus();
    });
    host.append(tabs);

    const panel = el("div", "drawer-panel");
    panel.id = panelId;
    panel.setAttribute("role", "tabpanel");
    host.append(panel);
    if (state.drawerTab === "voice") renderVoiceTab(panel, person);
    else renderRelations(panel, person, state.drawerTab === "mentions" ? "out" : "in");
  }

  function renderVoiceTab(panel, person) {
    const serial = ++renderSerial;
    panel.replaceChildren(el("div", "empty", "正在加载语音…"));
    data.loadVoice(person).then((payload) => {
      if (serial !== renderSerial || !panel.isConnected) return;
      if (!payload) { panel.replaceChildren(el("div", "empty", "这个角色还没有语音数据")); return; }
      const head = el("div", "panel-head");
      head.append(el("h2", null, "角色语音"));
      const sources = [...new Set((payload.items || []).flatMap((it) => Object.keys(it.audios || {})))];
      if (sources.length > 1) {
        const sw = el("div", "source-switch");
        sources.forEach((src) => {
          const b = el("button", "switch-btn" + (state.source === src ? " is-active" : ""), SOURCE_LABEL[src] || src);
          b.type = "button";
          b.setAttribute("aria-pressed", String(state.source === src));
          b.addEventListener("click", () => {
            state.source = src; data.saveUi(); render();
          });
          sw.append(b);
        });
        head.append(sw);
      }
      const langSw = el("div", "lang-switch");
      Object.entries(LANG_LABEL).forEach(([code, label]) => {
        const b = el("button", "switch-btn" + (state.lang === code ? " is-active" : ""), label);
        b.type = "button";
        b.setAttribute("aria-pressed", String(state.lang === code));
        b.addEventListener("click", () => {
          state.lang = code; data.saveUi(); render();
        });
        langSw.append(b);
      });
      head.append(langSw);
      const list = el("div", "voice-list");
      (payload.items || []).forEach((item, i) => {
        const row = el("div", "voice");
        row.dataset.key = String(item.title);
        row.style.setProperty("--i", String(Math.min(i, 24)));
        const picked = pickAudio(item, state.source, state.lang);
        const btn = el("button", "play");
        btn.type = "button";
        btn.disabled = !picked;
        btn.append(icon("play"));
        btn.setAttribute("aria-label", "播放 " + (item.title || ""));
        btn.addEventListener("click", () => {
          if (!picked) return;
          playerRef()?.play(item, picked.lang, picked.source);
        });
        const title = el("div", "title", state.showEn && item.title_en ? item.title_en : item.title);
        const text = el("div", "text");
        text.append(el("span", "zh", item.text || ""), el("span", "en", item.text_en || ""));
        const meta = el("div", "meta");
        if (item.line !== null && item.line !== undefined) meta.append(el("span", "tag", "关系台词"));
        if (picked) meta.append(el("span", "tag", (SOURCE_LABEL[picked.source] || picked.source) + " · " + (LANG_LABEL[picked.lang] || picked.lang)));
        else meta.append(el("span", "tag", "暂无音频"));
        row.append(btn, title, text, meta);
        list.append(row);
      });
      panel.replaceChildren(head, list);
    }).catch(() => {
      if (serial === renderSerial) panel.replaceChildren(el("div", "empty", "这个角色还没有语音数据"));
    });
  }

  function renderRelations(panel, person, dir) {
    panel.replaceChildren();
    const map = dir === "out" ? state.outMap.get(person.en) : state.inMap.get(person.en);
    const entries = [...(map?.entries() || [])].sort((a, b) => b[1].length - a[1].length);
    if (!entries.length) {
      panel.append(el("div", "empty", dir === "out" ? "TA 没有提到过其他角色" : "暂无角色提到 TA"));
      return;
    }
    const group = el("div", "relation-group");
    group.append(el("h3", null, dir === "out" ? "TA 说起过（" + entries.length + " 人）" : "被说起（" + entries.length + " 人）"));
    entries.forEach(([en, lines], i) => {
      const other = state.people.get(en);
      if (!other) return;
      const row = el("button", "rel-row");
      row.type = "button";
      row.style.animationDelay = (i * 18) + "ms";
      const img = el("img");
      img.src = other.img;
      img.alt = "";
      img.loading = "lazy";
      const who = el("span", "who");
      who.append(el("b", null, other.zh), el("small", null, (lines[0]?.content_zh || "").slice(0, 34)));
      row.append(img, who, el("span", "n", lines.length + " 条"));
      row.addEventListener("click", () => { state.drawerTab = "voice"; selectPerson(other); });
      group.append(row);
    });
    panel.append(group);
  }

  function quoteRow(person, line) {
    const row = el("div", "voice");
    row.dataset.key = String(line.title_zh || line.title || "");
    row.style.setProperty("--i", "0");
    const btn = el("button", "play");
    btn.type = "button";
    btn.append(icon("play"));
    btn.setAttribute("aria-label", "播放 " + ((state.showEn ? line.title_en : line.title_zh) || ""));
    btn.addEventListener("click", async () => {
      const payload = await data.loadVoice(person);
      const item = (payload?.items || []).find((it) => it.line === line.__index);
      if (!item) { toast("这条语音暂无音频"); return; }
      playerRef()?.play(item, state.lang, state.source);
    });
    const title = el("div", "title", (state.showEn ? line.title_en : line.title_zh) || "");
    const text = el("div", "text");
    text.append(el("span", "zh", line.content_zh || ""), el("span", "en", line.content_en || ""));
    row.append(btn, title, text);
    return row;
  }

  function renderCompare(host, a, b) {
    host.replaceChildren();
    if (!a || !b) return;
    const forward = state.outMap.get(a.en)?.get(b.en) || [];
    const backward = state.outMap.get(b.en)?.get(a.en) || [];

    const head = el("div", "compare-head");
    const pair = el("div", "pair");
    [a, b].forEach((p) => {
      const side = el("button", "side");
      side.type = "button";
      const img = el("img");
      img.src = p.img; img.alt = ""; img.loading = "lazy";
      side.append(img, el("b", null, p.zh));
      side.addEventListener("click", () => selectPerson(p));
      pair.append(side);
    });
    const swap = el("span", "swap");
    swap.append(icon("link"));
    pair.insertBefore(swap, pair.children[1]);
    head.append(pair);
    host.append(head);

    const mutual = forward.length > 0 && backward.length > 0;
    host.append(el("p", "compare-summary", mutual
      ? "双向提及：" + a.zh + " " + forward.length + " 条 · " + b.zh + " " + backward.length + " 条"
      : forward.length ? b.zh + " 从未回应 " + a.zh + " 的这番话"
        : a.zh + " 从未回应 " + b.zh + " 的这番话"));

    const actions = el("div", "compare-actions");
    const autoplay = el("button", "ghost-btn", "连播两人对话");
    autoplay.type = "button";
    autoplay.prepend(icon("audio"));
    autoplay.addEventListener("click", () => {
      const lines = [];
      forward.forEach((l) => lines.push({ item: l, person: a, line: l }));
      backward.forEach((l) => lines.push({ item: l, person: b, line: l }));
      const queue = lines.map(({ person, line }) => {
        let item = line;
        if (state.voice.has(person.zh)) {
          const payload = state.voice.get(person.zh);
          item = (payload?.items || []).find((it) => it.line === line.__index) || line;
        }
        return { person, line, item };
      });
      const first = queue.shift();
      if (!first) { toast("两人在语音里没有互相提到过对方"); return; }
      Promise.resolve(data.loadVoice(first.person)).then((payload) => {
        const item = (payload?.items || []).find((it) => it.line === first.line.__index) || first.item;
        playerRef()?.play(item, state.lang, state.source, queue.map((q) => ({ person: q.person, line: q.line, item: q.item })));
      });
    });
    actions.append(autoplay);
    host.append(actions);

    if (!forward.length && !backward.length) {
      host.append(el("div", "empty", "两人在语音里没有互相提到过对方"));
      return;
    }
    const groups = [];
    if (forward.length && backward.length) groups.push(["互相提到", [...forward.map((l) => ({ person: a, line: l })), ...backward.map((l) => ({ person: b, line: l }))]]);
    else if (forward.length) groups.push(["仅 " + a.zh + " 提到", forward.map((l) => ({ person: a, line: l }))]);
    else groups.push(["仅 " + b.zh + " 提到", backward.map((l) => ({ person: b, line: l }))]);
    const shown = new Set();
    groups.forEach(([label, entries]) => {
      const group = el("div", "relation-group");
      group.append(el("h3", null, label));
      entries.forEach(({ person, line }) => {
        const id = person.en + "|" + (line.title_zh || line.title || "");
        if (shown.has(id)) return;
        shown.add(id);
        group.append(quoteRow(person, line));
      });
      host.append(group);
    });
  }

  function showRandomPair() {
    const pairs = [];
    for (const [key, edge] of state.edges) {
      if (state.outMap.get(edge.to)?.has(edge.from)) pairs.push([state.people.get(edge.from), state.people.get(edge.to)]);
    }
    if (!pairs.length) { toast("暂无互为提及的角色对"); return; }
    const pair = pairs[Math.floor(Math.random() * pairs.length)];
    state.selected = [pair[0], pair[1]];
    if (graph && typeof graph.highlightSelection === "function") graph.highlightSelection();
    render(); data.updateUrl(); open();
  }

  function showEdgeQuote(from, to, lines) {
    if (!from || !to) return;
    state.selected = [from, to];
    if (graph && typeof graph.highlightSelection === "function") graph.highlightSelection();
    renderCompare(body, from, to);
    data.updateUrl();
    open();
  }

  // phone sheet: drag the grip down to dismiss, transform only
  if (grip && dossier) {
    let startY = null;
    grip.addEventListener("pointerdown", (e) => {
      startY = e.clientY;
      try { grip.setPointerCapture(e.pointerId); } catch (_) {}
      dossier.classList.add("is-dragging");
    });
    grip.addEventListener("pointermove", (e) => {
      if (startY === null) return;
      const dy = Math.max(0, e.clientY - startY);
      dossier.style.transform = "translateY(" + dy + "px)";
    });
    const end = (e) => {
      if (startY === null) return;
      const dy = Math.max(0, (e.clientY ?? startY) - startY);
      dossier.classList.remove("is-dragging");
      dossier.style.transform = "";
      startY = null;
      if (dy > 90) clearSelection();
    };
    grip.addEventListener("pointerup", end);
    grip.addEventListener("pointercancel", end);
  }
  if (closeBtn) closeBtn.addEventListener("click", clearSelection);

  return { selectPerson, clearSelection, open, close, render, showRandomPair, setShowEn, showEdgeQuote, markPlaying };
}
