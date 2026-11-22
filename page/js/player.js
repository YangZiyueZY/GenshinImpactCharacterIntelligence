/* 提瓦特关系档案馆 — audio player controller (Editorial Archive rewrite)
 * Builds <audio> and the progress slider into #playerBody (no audio in HTML).
 */
export function initPlayer(ctx) {
  const { state, data, dom } = ctx;
  const dossierRef = () => ctx.dossier;
  const { $, el, icon, toast } = dom;
  const host = $("#playerBody");
  const panel = $("#player");
  if (!host) return { play() {}, toggle() {}, stop() {}, seek() {} };

  const audio = document.createElement("audio");
  audio.id = "audio";
  audio.preload = "metadata";
  host.append(audio);

  const avatar = el("div", "player-avatar");
  const title = el("div", "player-title", "尚未播放");
  const sub = el("div", "player-sub", "");
  const head = el("div", "player-head");
  const label = el("div", "player-label");
  label.append(title, sub);
  head.append(avatar, label);

  const playBtn = el("button", "player-btn");
  playBtn.type = "button";
  playBtn.setAttribute("aria-label", "播放或暂停");
  playBtn.append(icon("play"));
  const closeBtn = el("button", "player-btn");
  closeBtn.type = "button";
  closeBtn.setAttribute("aria-label", "关闭播放器");
  closeBtn.append(icon("close"));

  const track = el("div", "player-track");
  track.setAttribute("role", "slider");
  track.setAttribute("tabindex", "0");
  track.setAttribute("aria-label", "播放进度");
  track.setAttribute("aria-valuemin", "0");
  track.setAttribute("aria-valuemax", "100");
  track.setAttribute("aria-valuenow", "0");
  const fill = el("div", "player-fill");
  track.append(fill);
  const time = el("div", "player-time", "0:00");

  const controls = el("div", "player-controls");
  controls.append(playBtn, track, time, closeBtn);
  host.append(head, controls);

  let queue = [];
  let current = null;

  const setIcon = (playing) => {
    playBtn.replaceChildren(icon(playing ? "pause" : "play"));
  };
  const openPanel = () => {
    if (!panel) return;
    panel.classList.add("is-open");
    panel.setAttribute("aria-hidden", "false");
  };
  const closePanel = () => {
    if (!panel) return;
    panel.classList.remove("is-open");
    panel.setAttribute("aria-hidden", "true");
  };
  const fmtTime = (s) => {
    const t = Math.floor(s || 0);
    return Math.floor(t / 60) + ":" + String(t % 60).padStart(2, "0");
  };
  const updateProgress = () => {
    const d = audio.duration || 0;
    const pct = d ? Math.min(100, Math.max(0, (audio.currentTime / d) * 100)) : 0;
    fill.style.transform = "scaleX(" + (pct / 100).toFixed(4) + ")";
    track.setAttribute("aria-valuenow", String(Math.round(pct)));
    time.textContent = fmtTime(audio.currentTime);
  };

  function play(item, lang, source, nextQueue) {
    if (!item || !item.audios) { toast("这条语音暂无可播放的音频"); return; }
    const order = source === "biligame" ? ["biligame", "hoyolab"] : ["hoyolab", "biligame"];
    let picked = null;
    for (const src of order) {
      const langs = item.audios[src];
      if (!langs) continue;
      if (langs[lang]) { picked = { url: langs[lang], source: src, lang }; break; }
      for (const l of ["zh", "en", "ja", "ko"]) if (langs[l]) { picked = { url: langs[l], source: src, lang: l }; break; }
      if (picked) break;
    }
    if (!picked) { toast("这条语音暂无可播放的音频"); return; }
    queue = Array.isArray(nextQueue) ? nextQueue.slice() : [];
    current = item;
    state.audio.item = item;
    state.audio.lang = picked.lang;
    state.audio.source = picked.source;
    state.audio.autoplay = queue.length > 0;
    audio.src = picked.url;
    audio.currentTime = 0;
    const person = ctx.state.selected.find((p) => p && p.zh === (item.speaker_zh || item.speaker)) || state.selected[0];
    avatar.style.backgroundImage = person ? "url('" + person.img + "')" : "";
    title.textContent = item.title || person?.zh || "角色语音";
    sub.textContent = (person?.zh || "") + " · " + (data.LANG_LABEL[picked.lang] || picked.lang) + " · " + (data.SOURCE_LABEL[picked.source] || picked.source);
    fill.style.transform = "scaleX(0)";
    track.setAttribute("aria-valuenow", "0");
    time.textContent = "0:00";
    setIcon(false);
    openPanel();

    audio.play().then(() => {
      setIcon(true);
      if (dossierRef() && typeof dossierRef().markPlaying === "function") dossierRef().markPlaying(item);
    }).catch(() => {
      toast("浏览器拦截了自动播放，请再点一次");
      setIcon(false);
    });
  }

  function toggle() {
    if (!audio.src) return;
    if (audio.paused) audio.play().catch(() => {});
    else audio.pause();
  }
  function stop() {
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    queue = [];
    current = null;
    state.audio.autoplay = false;
    setIcon(false);
    closePanel();
    if (dossierRef() && typeof dossierRef().markPlaying === "function") dossierRef().markPlaying(null);
  }
  function seek(ratio) {
    if (!isFinite(audio.duration)) return;
    audio.currentTime = Math.min(1, Math.max(0, ratio)) * audio.duration;
    updateProgress();
  }

  const seekAt = (clientX) => {
    const r = track.getBoundingClientRect();
    if (!r.width) return;
    seek((clientX - r.left) / r.width);
  };
  track.addEventListener("click", (e) => seekAt(e.clientX));
  let dragging = false;
  track.addEventListener("pointerdown", (e) => {
    dragging = true;
    try { track.setPointerCapture(e.pointerId); } catch (_) {}
    seekAt(e.clientX);
  });
  track.addEventListener("pointermove", (e) => { if (dragging) seekAt(e.clientX); });
  track.addEventListener("pointerup", () => { dragging = false; });
  track.addEventListener("pointercancel", () => { dragging = false; });
  track.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight" || e.key === "ArrowUp") { e.preventDefault(); seek((audio.currentTime + 5) / (audio.duration || 1)); }
    else if (e.key === "ArrowLeft" || e.key === "ArrowDown") { e.preventDefault(); seek((audio.currentTime - 5) / (audio.duration || 1)); }
    else if (e.key === "Home") { e.preventDefault(); seek(0); }
    else if (e.key === "End") { e.preventDefault(); seek(1); }
  });

  playBtn.addEventListener("click", toggle);
  closeBtn.addEventListener("click", stop);
  audio.addEventListener("timeupdate", updateProgress);
  audio.addEventListener("play", () => setIcon(true));
  audio.addEventListener("pause", () => setIcon(false));
  audio.addEventListener("loadedmetadata", updateProgress);
  audio.addEventListener("ended", () => {
    setIcon(false);
    if (dossierRef() && typeof dossierRef().markPlaying === "function") dossierRef().markPlaying(null);
    if (state.audio.autoplay && queue.length) {
      const next = queue.shift();
      state.audio.autoplay = queue.length > 0;
      if (!next) return;
      const remaining = queue.slice();
      Promise.resolve(data.loadVoice(next.person)).then((payload) => {
        const item = (payload?.items || []).find((it) => it.line === next.line?.__index) || next.item;
        if (item && item.audios) {
          play(item, state.lang, state.source, remaining);
        } else if (remaining.length) {
          const later = remaining.shift();
          Promise.resolve(data.loadVoice(later.person)).then((p2) => {
            const it2 = (p2?.items || []).find((it) => it.line === later.line?.__index) || later.item;
            if (it2?.audios) play(it2, state.lang, state.source, remaining);
          });
        }
      });
    }
  });
  audio.addEventListener("error", () => { toast("音频加载失败，可换一个语音来源试试"); setIcon(false); });

  return { play, toggle, stop, seek };
}
