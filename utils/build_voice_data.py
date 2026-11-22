"""Build the voice + profile side-data used by the redesigned page.

Inputs (all already cached by utils/hoyolab_source.py):
  data/char_data.json                     the graph itself (122 chars, 1209 edges)
  data_raw/hoyolab/entry_<id>_zh-cn.json  official wiki entry per character
  data_raw/hoyolab/entry_<id>_en-us.json  English counterpart, joined by audio hash
  data_raw/hoyolab/list_zh-cn.json        name -> entry_page_id

Outputs:
  data/profile.json          per character: element/weapon/rarity/region/birthday/
                             constellation/title/affiliation/CVs/release version
  data/voice/<name>.json     every voice line of a character with mp3 urls for
                             zh/ja/en/ko, plus the index of the matching graph edge
                             (the "关于X" lines), so hovering an edge can play it.

Language names differ per locale response: the zh-cn response labels the audios
汉语/日语/英语/韩语, the en-us one CN/JP/EN/KR -- both are accepted here.
"""

import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "utils"))

from hoyolab_source import audio_key, clean_text, normalize_title  # noqa: E402

DATA_DIR = os.path.join(REPO_ROOT, "data")
CACHE = os.path.join(REPO_ROOT, "data_raw", "hoyolab")
VOICE_DIR = os.path.join(DATA_DIR, "voice")

LANG_ALIASES = {
    "zh": ("汉语", "CN", "中文"),
    "ja": ("日语", "JP"),
    "en": ("英语", "EN"),
    "ko": ("韩语", "KR"),
}

PROFILE_KEYS = {
    "生日": "birthday",
    "命之座": "constellation",
    "称号": "title",
    "星之楔": "element",
    "所属": "affiliation",
    "汉语 CV": "cv_zh",
    "日语 CV": "cv_ja",
    "英语 CV": "cv_en",
    "韩语 CV": "cv_ko",
    "实装版本": "release",
    "所在国家": "nation",
    "性别": "gender",
}


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def audio_urls(record):
    """{zh, ja, en, ko} from one voice record."""
    out = {}
    for audio in record.get("audios") or []:
        name = (audio.get("name") or "").strip()
        for lang, aliases in LANG_ALIASES.items():
            if name in aliases and lang not in out:
                out[lang] = audio.get("url") or ""
    return out


def list_meta(lang="zh-cn"):
    """name -> {element, weapon, rarity, region} from the wiki list filters."""
    items = load_json(os.path.join(CACHE, "list_" + lang + ".json"), []) or []
    out = {}
    for item in items:
        name = item.get("name")
        if not name:
            continue
        meta = {}
        for key, field in (("character_vision", "element"), ("character_weapon", "weapon"),
                           ("character_rarity", "rarity"), ("character_region", "region")):
            values = ((item.get("filter_values") or {}).get(key) or {}).get("values") or []
            if not values:
                continue
            value = values[0]
            if isinstance(value, dict):
                value = value.get("value") or value.get("enum_string") or ""
            meta[field] = str(value).strip()
        out[name] = meta
    return out


def build_profile(entry_zh):
    """baseInfo component -> flat profile dict."""
    profile = {}
    for item in entry_zh.get("components", {}).get("baseInfo") or []:
        key = (item.get("key") or "").strip()
        values = item.get("value") or []
        if key not in PROFILE_KEYS or not values:
            continue
        value = clean_text(str(values[0]))
        if value:
            profile[PROFILE_KEYS[key]] = value
    return profile


def match_line_index(line_title_zh, line_content_zh, speaker, voice_items):
    """Find the voice record that produced one graph edge.

    Edge titles look like "<speaker>关于<target>" while the wiki title is
    "关于<target>…"; both are normalised before comparing, and the content text
    is used as a fallback for titles that legitimately differ.
    """
    stripped = normalize_title(line_title_zh or "")
    if stripped.startswith(speaker):
        stripped = stripped[len(speaker):]
    stripped = normalize_title(stripped)
    for idx, item in enumerate(voice_items):
        if normalize_title(item.get("title") or "") == stripped:
            return idx
    content = (line_content_zh or "")[:40]
    if content:
        for idx, item in enumerate(voice_items):
            if (clean_text(item.get("desc") or "")[:40] == content):
                return idx
    return None


def main():
    chars = load_json(os.path.join(DATA_DIR, "char_data.json"), [])
    zh_list = load_json(os.path.join(CACHE, "list_zh-cn.json"), [])
    id_of = {c.get("name"): c.get("entry_page_id") for c in zh_list}
    os.makedirs(VOICE_DIR, exist_ok=True)

    profile_out = {}
    meta_by_name = list_meta()
    stats = {"chars": 0, "voice_items": 0, "with_audio": 0, "edges_matched": 0,
             "edges_total": 0, "missing_entry": []}

    for char in chars:
        name = char["name_zh"]
        entry_id = id_of.get(name)
        entry_zh = load_json(os.path.join(CACHE, "entry_%s_zh-cn.json" % entry_id), {}) if entry_id else {}
        entry_en = load_json(os.path.join(CACHE, "entry_%s_en-us.json" % entry_id), {}) if entry_id else {}
        if not entry_zh:
            stats["missing_entry"].append(name)
            continue

        components = entry_zh.get("components") or {}
        voice_items = components.get("voice") or []
        en_by_key = {}
        for record in (entry_en.get("components") or {}).get("voice") or []:
            key = audio_key(record)
            if key and key not in en_by_key:
                en_by_key[key] = record

        items = []
        for record in voice_items:
            audios = audio_urls(record)
            en_record = en_by_key.get(audio_key(record)) or {}
            items.append({
                "title": normalize_title(clean_text(record.get("title"))),
                "title_en": normalize_title(clean_text(en_record.get("title"))),
                "text": clean_text(record.get("desc")),
                "text_en": clean_text(en_record.get("desc")),
                # keyed by source so a second provider (e.g. the CN wiki) can be
                # added later without touching the page
                "audios": {"hoyolab": {k: v for k, v in audios.items() if v}} if audios else {},
                "line": None,
            })
            stats["voice_items"] += 1
            if audios:
                stats["with_audio"] += 1

        for idx, line in enumerate(char.get("lines") or []):
            stats["edges_total"] += 1
            hit = match_line_index(line.get("title_zh"), line.get("content_zh"), name, items)
            if hit is None:
                continue
            items[hit]["line"] = idx
            stats["edges_matched"] += 1

        profile = build_profile(entry_zh)
        # the list filters carry weapon/rarity/region which baseInfo lacks
        for field, value in (meta_by_name.get(name) or {}).items():
            if value and not profile.get(field):
                profile[field] = value
        # the list filter says "风元素", baseInfo says "风": keep one short form
        if profile.get("element"):
            profile["element"] = profile["element"].replace("元素", "")
        profile["name_zh"] = name
        profile["name_en"] = char.get("name_en") or ""
        profile["icon"] = "../data/image/%s.png" % name
        profile_out[name] = profile

        sources = sorted({src for item in items for src in (item.get("audios") or {})})
        payload = {"name": name, "name_en": char.get("name_en") or "",
                   "sources": ["hoyolab"] if sources else [], "items": items}
        with open(os.path.join(VOICE_DIR, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        stats["chars"] += 1

    with open(os.path.join(DATA_DIR, "profile.json"), "w", encoding="utf-8") as f:
        json.dump(profile_out, f, ensure_ascii=False, separators=(",", ":"))

    total_size = sum(os.path.getsize(os.path.join(VOICE_DIR, f))
                     for f in os.listdir(VOICE_DIR))
    print("characters:", stats["chars"], "| voice items:", stats["voice_items"],
          "| with audio:", stats["with_audio"])
    print("edge -> voice match:", str(stats["edges_matched"]) + "/" + str(stats["edges_total"]))
    if stats["missing_entry"]:
        print("no wiki entry:", stats["missing_entry"])
    print("voice dir:", round(total_size / 1024 / 1024, 2), "MB,", len(os.listdir(VOICE_DIR)), "files")
    print("profile.json:", round(os.path.getsize(os.path.join(DATA_DIR, "profile.json")) / 1024, 1), "KB")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
