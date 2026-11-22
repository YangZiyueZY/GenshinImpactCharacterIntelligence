"""Second voice provider: the biligame 原神 WIKI (MediaWiki).

Why a second provider
  The HoYoLab wiki gives every line in four languages, but its audio is 0.5-2 MB
  of wav on an overseas CDN. The biligame wiki carries the same four languages as
  ~50 KB ogg files on patchwiki.biligame.com, which is fast inside China. The page
  lets the visitor pick either source, so both are stored per line:

      "audios": {"hoyolab": {...}, "biligame": {"zh": ..., "ja": ..., "en": ..., "ko": ...}}

Voice pages
  <char>语音 is wikitext with one {{角色/语音}} or {{角色/语音1}} block per line:
      |语音类型=关于芭芭拉…      |语音内容=<zh>   |语音内容英语=<en>
      |语音文件={{player|琴_关于芭芭拉}}        -> File:琴_关于芭芭拉.ogg
      |语音文件日语=..., 语音文件英语=..., 语音文件韩语=...
  Pages are fetched in batches (the wiki answers HTTP 567 when hammered) and
  cached under data_raw/biligame/.
"""

import json
import os
import re
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hoyolab_source import clean_text, normalize_title  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")
CACHE = os.path.join(REPO_ROOT, "data_raw", "biligame")
API = "https://wiki.biligame.com/ys/api.php"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
FILE_PARAM = {"zh": "语音文件", "ja": "语音文件日语", "en": "语音文件英语", "ko": "语音文件韩语"}
AUDIO_EXTS = (".ogg", ".mp3", ".wav", ".flac", ".m4a")


class Wiki:
    def __init__(self, cache_dir=CACHE, min_interval=0.5, ttl_hours=24 * 30):
        self.cache_dir = cache_dir
        self.min_interval = min_interval
        self.ttl = ttl_hours * 3600
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA})
        self._last = 0.0
        self.calls = 0
        os.makedirs(cache_dir, exist_ok=True)

    def _throttle(self):
        wait = self.min_interval - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()

    def api(self, params, tries=5):
        """One API call with adaptive backoff.

        The wiki front-end answers HTTP 567 (its WAF) once requests come too
        fast, and keeps doing so for a while: on the first 567 the pacing is
        raised permanently and the call waits much longer than a normal retry.
        """
        for attempt in range(tries):
            self._throttle()
            try:
                r = self.session.get(API, params=dict(params, format="json",
                                                       formatversion="2"), timeout=45)
                self.calls += 1
                if r.status_code == 200 and r.text.lstrip().startswith("{"):
                    return r.json()
                if r.status_code == 567:
                    self.min_interval = min(4.0, max(self.min_interval * 1.5, 1.2))
                    wait = 30 * (attempt + 1)
                    print("    WAF 567 -> pacing " + str(round(self.min_interval, 2))
                          + "s, sleep " + str(wait) + "s", flush=True)
                    time.sleep(wait)
                    continue
                print("    wiki HTTP " + str(r.status_code) + " -> backoff", flush=True)
            except Exception as e:
                print("    " + type(e).__name__ + " -> backoff", flush=True)
            time.sleep(8 * (attempt + 1))
        return None

    def wikitexts(self, titles, batch=20):
        """{title: wikitext} fetched in batches, cached per page."""
        out = {}
        todo = []
        for title in titles:
            path = os.path.join(self.cache_dir, re.sub(r'[\\/:*?"<>|]', "_", title) + ".wikitext")
            if os.path.exists(path) and time.time() - os.path.getmtime(path) < self.ttl:
                with open(path, encoding="utf-8") as f:
                    out[title] = f.read()
            else:
                todo.append((title, path))
        for i in range(0, len(todo), batch):
            chunk = todo[i:i + batch]
            data = self.api({"action": "query", "prop": "revisions",
                             "titles": "|".join(t for t, _ in chunk),
                             "rvprop": "content", "rvslots": "main"})
            if not data:
                continue
            for page in (data.get("query") or {}).get("pages", []):
                title = page.get("title") or ""
                text = ""
                revs = page.get("revisions") or []
                if revs:
                    slot = revs[0].get("slots", {}).get("main", {})
                    text = slot.get("content") or revs[0].get("content") or ""
                if text:
                    for t, path in chunk:
                        if t == title or t.replace(" ", "_") == title.replace(" ", "_"):
                            with open(path, "w", encoding="utf-8") as f:
                                f.write(text)
                            out[t] = text
                            break
            print("    fetched batch " + str(i // batch + 1) + "/"
                  + str((len(todo) + batch - 1) // batch), flush=True)
        return out

    def _save_cache(self, cache, cache_path):
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=0)

    def file_urls(self, names, batch=25):
        """{file name without extension: url} for File:<name>.ogg (fallback mp3/wav)."""
        cache_path = os.path.join(self.cache_dir, "files.json")
        cache = {}
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                cache = json.load(f)

        def norm(name):
            return (name or "").replace(" ", "_")

        pending = []
        for n in dict.fromkeys(names):
            if n and norm(n) not in cache:
                pending.append(norm(n))
        for ext in AUDIO_EXTS:
            if not pending:
                break
            still = []
            for i in range(0, len(pending), batch):
                chunk = pending[i:i + batch]
                titles = "|".join("File:" + name + ext for name in chunk)
                data = self.api({"action": "query", "titles": titles,
                                 "prop": "imageinfo", "iiprop": "url|size"})
                resolved = {}
                for page in (data or {}).get("query", {}).get("pages", []):
                    # MediaWiki normalises the namespace: "File:X.ogg" comes back as
                    # "文件:X.ogg" (and underscores become spaces)
                    title = page.get("title") or ""
                    base = title.rsplit(":", 1)[-1] if ":" in title else title
                    for e in AUDIO_EXTS:
                        if base.endswith(e):
                            base = base[: -len(e)]
                            break
                    info = (page.get("imageinfo") or [{}])[0]
                    if info.get("url") and not page.get("missing"):
                        resolved[norm(base)] = info["url"]
                for name in chunk:
                    if name in resolved:
                        cache[name] = resolved[name]
                    else:
                        still.append(name)
                done = len(cache)
                if done % 250 < batch:
                    self._save_cache(cache, cache_path)
                print("    " + ext + ": " + str(len(resolved)) + " resolved, "
                      + str(len(still)) + " still pending, " + str(done) + " cached",
                      flush=True)
            pending = [n for n in still if n not in cache]
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=0)
        return cache


def split_top(text):
    parts, depth, cur, i = [], 0, "", 0
    while i < len(text):
        if text.startswith("{{", i) or text.startswith("[[", i):
            depth += 1
            cur += text[i:i + 2]
            i += 2
            continue
        if text.startswith("}}", i) or text.startswith("]]", i):
            depth -= 1
            cur += text[i:i + 2]
            i += 2
            continue
        if text[i] == "|" and depth == 0:
            parts.append(cur)
            cur = ""
            i += 1
            continue
        cur += text[i]
        i += 1
    parts.append(cur)
    return parts


def blocks(wikitext, prefix="角色/语音"):
    normalized = re.sub(r"\{\{\s+", "{{", wikitext or "")
    out, i = [], 0
    while True:
        j = normalized.find("{{" + prefix, i)
        if j < 0:
            break
        depth, k = 1, j + 2
        while k < len(normalized) - 1 and depth:
            if normalized.startswith("{{", k):
                depth += 1
                k += 2
            elif normalized.startswith("}}", k):
                depth -= 1
                k += 2
            else:
                k += 1
        out.append(normalized[j:k])
        i = k
    return out


def player_file(value):
    m = re.search(r"\{\{\s*player[^|]*\|\s*([^}|]+?)\s*\}\}", value or "")
    return (m.group(1) if m else (value or "")).strip()


def parse_page(wikitext):
    items = []
    for block in blocks(wikitext):
        body = block[2:]
        if body.endswith("}}"):
            body = body[:-2]
        params = {}
        for part in split_top(body):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            params[key.strip()] = value.strip()
        title = normalize_title(clean_text(params.get("语音类型")))
        if not title:
            continue
        items.append({
            "title": title,
            "files": {lang: player_file(params.get(key)) for lang, key in FILE_PARAM.items()
                      if params.get(key)},
            "text": clean_text(params.get("语音内容")),
        })
    return items


def enrich(scope="related", verbose=True):
    """scope="related" resolves audio only for graph edges (fast), "all" for every line."""
    chars = json.load(open(os.path.join(DATA_DIR, "char_data.json"), encoding="utf-8"))
    names = [c["name_zh"] for c in chars]
    wiki = Wiki()
    pages = wiki.wikitexts([n + "语音" for n in names])
    parsed = {n: parse_page(pages.get(n + "语音", "")) for n in names}

    wanted = {}
    for char in chars:
        path = os.path.join(DATA_DIR, "voice", char["name_zh"] + ".json")
        if not os.path.exists(path):
            continue
        payload = json.load(open(path, encoding="utf-8"))
        wanted[char["name_zh"]] = set(
            (it.get("title") or "").strip()
            for it in payload["items"] if scope == "all" or it.get("line") is not None)
    needed = [f for name, items in parsed.items()
              for it in items if it["title"] in wanted.get(name, ())
              for f in it["files"].values()]
    if verbose:
        print("pages:", len(pages), "| items:", sum(len(v) for v in parsed.values()),
              "| file lookups:", len(needed), flush=True)
    urls = wiki.file_urls(needed)

    stats = {"items": 0, "line_items": 0, "audio_added": 0, "chars": 0, "unresolved": 0}
    for char in chars:
        name = char["name_zh"]
        path = os.path.join(DATA_DIR, "voice", name + ".json")
        if not os.path.exists(path):
            continue
        payload = json.load(open(path, encoding="utf-8"))
        by_title = {}
        for item in parsed.get(name, []):
            by_title.setdefault(item["title"], item)
        for item in payload["items"]:
            stats["items"] += 1
            source = by_title.get(normalize_title(item.get("title") or ""))
            if not source:
                continue
            audios = {lang: urls.get((fn or "").replace(" ", "_"))
                      for lang, fn in source["files"].items()}
            audios = {lang: u for lang, u in audios.items() if u}
            if not audios:
                stats["unresolved"] += 1
                continue
            item.setdefault("audios", {})["biligame"] = audios
            stats["audio_added"] += 1
            if item.get("line") is not None:
                stats["line_items"] += 1
        sources = sorted({src for it in payload["items"] for src in (it.get("audios") or {})})
        payload["sources"] = sources
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        stats["chars"] += 1

    if verbose:
        print("merged biligame audio into", stats["chars"], "characters;",
              stats["audio_added"], "/", stats["items"], "items now have biligame audio",
              "(" + str(stats["line_items"]) + " of them relation lines),",
              stats["unresolved"], "had no resolvable file", flush=True)
        print("wiki calls:", wiki.calls, flush=True)
    return stats


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    scope = sys.argv[1] if len(sys.argv) > 1 else "related"
    enrich(scope=scope)
