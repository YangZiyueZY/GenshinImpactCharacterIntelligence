"""Official miHoYo wiki sources -- replaces the dead content API and the datamined mirrors.

Two endpoints are used, both owned by miHoYo:

  OBC / baike.mihoyo.com (CN official wiki, 观测枢)
    GET {OBC_API}/home/content/list?app_sn=ys_obc&channel_os=webgame&channel_id=25
      -> data.list[0].list[] = the 角色 channel: content_id, title, icon, ext
         (ext carries 地区/星级/元素/武器 filters). This replaces the old
         ys.mihoyo.com/content/ysCn/getContentList (URL_ZH), which now answers
         retcode -1.
    NOTE its per-entry endpoint (/v1/content/info) answers retcode -2010
    "内容不存在" for every real content id, so voice lines are taken from HoYoLab.

  HoYoLab wiki (official international wiki)
    POST {HOYO_API}get_entry_page_list   {"menu_id": 2, ...}  -> character list
    GET  {HOYO_API}entry_page?entry_page_id=<id>              -> entry_page
         components[component_id="voice"].data is a JSON string whose "list" holds
         [{title, desc, audios[]}] -- title is "关于X…" / "About X", i.e. the
         relationship edge we need, with the Chinese and English localisation in
         the same record. Language is selected with the x-rpc-language header
         (query/URL lang= is ignored), and the voice list order is identical
         across languages, so zh and en align by index.

Everything is cached under data_raw/{obc,hoyolab}/ so re-runs cost nothing.
"""

import html
import json
import os
import time

import requests

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OBC_CACHE = os.path.join(REPO_ROOT, "data_raw", "obc")
HOYO_CACHE = os.path.join(REPO_ROOT, "data_raw", "hoyolab")
OBC_API = "https://api-takumi.mihoyo.com/common/blackboard/ys_obc/v1"
HOYO_API = "https://sg-wiki-api-static.hoyolab.com/hoyowiki/wapi/"
CHARACTER_CHANNEL_ID = 25
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# The traveller variants are story avatars, not network members: the existing
# data (built from the old official list) never contained them either.
EXCLUDED_NAMES = {"旅行者", "空", "荧"}
EXCLUDED_NAME_PREFIXES = ("旅行者",)


def is_excluded_name(name):
    return name in EXCLUDED_NAMES or any(name.startswith(p) for p in EXCLUDED_NAME_PREFIXES)


def clean_text(text):
    if not text:
        return ""
    text = html.unescape(text)
    # strip the wiki HTML (<br>, <p><span ...>) without a regex escape mess
    out, depth = [], 0
    for ch in text:
        if ch == "<":
            depth += 1
            continue
        if ch == ">":
            depth = max(0, depth - 1)
            continue
        if depth == 0:
            out.append(ch)
    text = "".join(out)
    # in-wiki cross references look like \$[{...}]\$
    while "$[{" in text:
        i = text.find("$[{")
        j = text.find("}]$", i)
        if j < 0:
            break
        text = text[:i] + text[j + 3:]
    return " ".join(text.split())


def normalize_title(text):
    return (text or "").rstrip().rstrip("…。. ")


def audio_key(record):
    """Stable cross-language key for one voice line.

    Every voice record carries the CN/EN/JP/KR audio urls, and the file hash in
    front of the "_" is the same in every language response. Record *order* and
    record *ids* are not: the zh and en voice lists are each sorted by their own
    locale's titles, so pairing them by index silently mis-pairs the text (it
    shows up as duplicate edges and as "Diluc about Lisa" hanging off the
    "About the Vision" line). Join on this hash instead.
    """
    auds = record.get("audios") or []
    ordered = [a for a in auds if (a.get("name") or "") == "CN"] or auds
    for a in ordered:
        tail = (a.get("url") or "").rsplit("/", 1)[-1]
        if tail:
            return tail.split("_")[0]
    return None


class WikiSources:
    def __init__(self, cache_ttl_hours=24 * 7, force=False, verbose=True):
        self.ttl = cache_ttl_hours * 3600
        self.force = force
        self.verbose = verbose
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA, "Referer": "https://wiki.hoyolab.com/"})
        self.calls = 0
        os.makedirs(OBC_CACHE, exist_ok=True)
        os.makedirs(HOYO_CACHE, exist_ok=True)

    def _log(self, msg):
        if self.verbose:
            print(msg, flush=True)

    def _cached(self, path, fetch):
        if not self.force and os.path.exists(path) and time.time() - os.path.getmtime(path) < self.ttl:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        data = fetch()
        if data is not None:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
        return data

    # ------------------------------------------------------------------ OBC
    def obc_characters(self):
        path = os.path.join(OBC_CACHE, "characters.json")

        def fetch():
            r = self.session.get(OBC_API + "/home/content/list", timeout=45, params={
                "app_sn": "ys_obc", "channel_os": "webgame",
                "channel_id": CHARACTER_CHANNEL_ID, "page": 1, "limit": 20})
            self.calls += 1
            j = r.json()
            if j.get("retcode") != 0:
                raise RuntimeError("OBC list failed: " + str(j.get("message")))
            node = (j.get("data") or {}).get("list") or [{}]
            inner = node[0].get("list") or []
            out = {}
            for item in inner:
                name = normalize_title(item.get("title") or "")
                if not name or name in out:
                    continue
                meta = {}
                try:
                    ext = json.loads(item.get("ext") or "{}")
                except ValueError:
                    ext = {}
                for ch in ext.values():
                    raw = ((ch or {}).get("filter") or {}).get("text") or ""
                    try:
                        tags = json.loads(raw) if raw else []
                    except ValueError:
                        tags = []
                    for tag in tags:
                        if "/" in tag:
                            key, value = tag.split("/", 1)
                            meta[key] = value
                out[name] = {
                    "content_id": item.get("content_id"),
                    "name": name,
                    "icon": item.get("icon") or "",
                    "region": meta.get("地区", ""),
                    "rarity": meta.get("星级", ""),
                    "element": meta.get("元素", ""),
                    "weapon": meta.get("武器", ""),
                    "summary": clean_text(item.get("summary")),
                }
            self._log("  OBC 角色频道: " + str(len(out)) + " entries")
            return out

        return self._cached(path, fetch) or {}

    # -------------------------------------------------------------------- HoYoLab
    def hoyo_list(self, lang):
        path = os.path.join(HOYO_CACHE, "list_" + lang + ".json")

        def fetch():
            headers = {"x-rpc-language": lang, "x-rpc-wiki_app": "genshin",
                       "Content-Type": "application/json",
                       "Origin": "https://wiki.hoyolab.com"}
            out, page = [], 1
            while True:
                j = self.session.post(HOYO_API + "get_entry_page_list", headers=headers,
                                      timeout=40, json={"filters": [], "menu_id": 2,
                                                        "page_num": page, "page_size": 30,
                                                        "use_es": True}).json()
                self.calls += 1
                if j.get("retcode") != 0:
                    raise RuntimeError("HoYoLab list failed: " + str(j.get("message")))
                d = j.get("data") or {}
                out += d.get("list") or []
                total = int(d.get("total") or 0)
                if len(out) >= total or not d.get("list"):
                    break
                page += 1
                time.sleep(0.4)
            return out

        return self._cached(path, fetch) or []

    def hoyo_entry(self, entry_id, lang):
        path = os.path.join(HOYO_CACHE, "entry_" + str(entry_id) + "_" + lang + ".json")

        def fetch():
            headers = {"x-rpc-language": lang, "x-rpc-wiki_app": "genshin",
                       "Referer": "https://wiki.hoyolab.com/",
                       "Origin": "https://wiki.hoyolab.com"}
            j = self.session.get(HOYO_API + "entry_page", headers=headers, timeout=40,
                                 params={"entry_page_id": entry_id}).json()
            self.calls += 1
            if j.get("retcode") != 0:
                return None
            page = (j.get("data") or {}).get("page") or {}
            parts = {}
            for module in page.get("modules") or []:
                for comp in module.get("components") or []:
                    raw = (comp.get("data") or "").strip()
                    if not raw:
                        continue
                    try:
                        parts[comp.get("component_id")] = json.loads(raw).get("list") or []
                    except ValueError:
                        continue
            return {"id": page.get("id"), "name": page.get("name"),
                    "icon": page.get("icon_url"), "components": parts}

        return self._cached(path, fetch)

    def voices(self, entry_id):
        """(zh voice list, en voice records keyed by audio hash)."""
        zh = (self.hoyo_entry(entry_id, "zh-cn") or {}).get("components", {}).get("voice") or []
        en_list = (self.hoyo_entry(entry_id, "en-us") or {}).get("components", {}).get("voice") or []
        en_map = {}
        for record in en_list:
            key = audio_key(record)
            if key and key not in en_map:
                en_map[key] = record
        return zh, en_map


def build_dataset(prev_chars, verbose=True):
    """node_data/edge_data in the same shape prepare_data() produces."""
    src = WikiSources(verbose=verbose)
    obc = src.obc_characters()
    zh_list = src.hoyo_list("zh-cn")
    en_by_id = {c.get("entry_page_id"): c.get("name") for c in src.hoyo_list("en-us")}

    prev_by_name = {c["name_zh"]: c for c in prev_chars}
    tracked, skipped_voiceless = [], []
    for item in zh_list:
        name = normalize_title(item.get("name") or "")
        if not name or is_excluded_name(name):
            continue
        entry_id = item.get("entry_page_id")
        zh_voice, en_voice = src.voices(entry_id)
        if not zh_voice:
            skipped_voiceless.append(name)
            continue
        tracked.append({"name": name, "entry_id": entry_id,
                        "name_en": en_by_id.get(entry_id) or "",
                        "zh": zh_voice, "en": en_voice})

    if skipped_voiceless:
        src._log("  listed but no voice data yet: " + ", ".join(skipped_voiceless))

    # characters we already ship but the official wiki no longer lists (they are
    # kept, with their previous lines, by merge_data)
    tracked_names = {t["name"] for t in tracked}
    dropped_from_wiki = [n for n in prev_by_name if n not in tracked_names]

    node_data, edge_data = [], []
    paired = total_zh = duplicate_rows = 0
    for i, t in enumerate(tracked):
        name = t["name"]
        total_zh += len(t["zh"])
        prev = prev_by_name.get(name, {})
        meta = obc.get(name, {})
        avatar_id = prev.get("id") if isinstance(prev.get("id"), int) else 9000 + i
        rarity_txt = meta.get("rarity", "")
        node_data.append({
            "avatarId": avatar_id,
            "name_zh": name,
            "name_en": t["name_en"] or prev.get("name_en") or "",
            "rarity": 5 if "五星" in rarity_txt else (4 if "四星" in rarity_txt else prev.get("rarity", 5)),
            "bodyType": prev.get("bodyType", ""),
            "weaponType": meta.get("weapon") or prev.get("weaponType", ""),
            "element": meta.get("element") or prev.get("element", ""),
            "region": meta.get("region") or prev.get("region", ""),
            "img_url": meta.get("icon") or prev.get("img_url") or "",
        })
        seen_rows = set()
        for idx, voice in enumerate(t["zh"]):
            en_voice = t["en"].get(audio_key(voice)) or {}
            if en_voice:
                paired += 1
            title_zh = normalize_title(clean_text(voice.get("title")))
            title_en = normalize_title(clean_text(en_voice.get("title")))
            content_zh = clean_text(voice.get("desc"))
            content_en = clean_text(en_voice.get("desc"))
            if not title_zh or not content_zh:
                continue
            # the same title/content pair can appear twice on one page
            dedupe = (title_zh, content_zh)
            if dedupe in seen_rows:
                duplicate_rows += 1
                continue
            seen_rows.add(dedupe)
            edge_data.append({
                "avatarId": avatar_id,
                "fetterId": idx,
                "title_zh": title_zh,
                "title_en": title_en,
                "content_zh": content_zh,
                "content_en": content_en,
            })

    if verbose:
        src._log("  official dataset: " + str(len(node_data)) + " characters, "
                 + str(len(edge_data)) + " voice rows, " + str(src.calls) + " http calls")
        src._log("  zh/en pairing by audio hash: " + str(paired) + "/" + str(total_zh)
                 + (" (dropped " + str(duplicate_rows) + " duplicate rows)"
                    if duplicate_rows else ""))
        if total_zh and paired < total_zh:
            src._log("  WARNING: " + str(total_zh - paired) + " lines have no English"
                     " counterpart; their content_en stays empty")
        if dropped_from_wiki:
            src._log("  in data but not in the official list: "
                     + ", ".join(dropped_from_wiki[:10]))
    return node_data, edge_data


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    prev = json.load(open(os.path.join(REPO_ROOT, "data", "char_data.json"), encoding="utf-8"))
    nodes, edges = build_dataset(prev)
    print("OK", len(nodes), len(edges))
