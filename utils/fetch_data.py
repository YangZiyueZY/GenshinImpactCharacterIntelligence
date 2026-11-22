"""Regenerate data/char_data.json from the official character list + datamined tables.

Pipeline (see .github/workflows/update.yml):
  1. read the previous data file (the source of stable id / ver values)
  2. resolve the current game version (REF_VER / REF_DATE / PERIOD, or --ver)
  3. fetch the official character list (URL_ZH) -> released names, ids, icon urls
  4. diff against the previous data -> new characters
  5. download the datamined tables (DATA_REPO_URL) and decode names + voice lines
  6. build the graph: each "about X" voice line becomes an edge speaker -> X
  7. merge, keeping characters that only exist in the previous data file
  8. validate, back up, write data/char_data.json + data/char_data_min.json
  9. sync new characters into the Notion mirror, download missing icons
 10. commit + push and fire the webhook notification (CI only)

Fixes vs. the previous revision
  * runs locally: works from any CWD, every env var is optional at import time,
    the Notion step is skipped when unconfigured, and git steps are skipped when
    this is not a checkout / when nothing changed
  * non-destructive merge: characters already in char_data.json but absent from
    the official list (datamined, not-yet-released characters) are preserved
    instead of silently deleted; opt into the old behaviour with --strict-released
  * a failed/unreachable download aborts with a clear message instead of a deep
    KeyError, and outputs are validated before anything on disk is overwritten
  * calc_ver no longer raises KeyError when REF_VER is missing, and accepts the
    full X.Y.Z reference form it assumes
  * --dry-run / --offline / --refresh / --ver / --no-images / --no-notion flags
  * alias entries can no longer overwrite a real character name

Local usage:
  python utils/fetch_data.py --offline --refresh --dry-run
  python utils/fetch_data.py --offline --refresh
  set URL_ZH=... & set DATA_REPO_URL=... & python utils/fetch_data.py --refresh
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

sys.path.insert(0, str(Path(__file__).resolve().parent))
from download_images import download_images            # noqa: E402
from prepare_data import download_data, prepare_data    # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DATA_FILE = DATA_DIR / "char_data.json"
DATA_FILE_MIN = DATA_DIR / "char_data_min.json"
ALIAS_FILE = DATA_DIR / "alias.json"
IMAGE_DIR = DATA_DIR / "image"
BACKUP_ROOT = REPO_ROOT / "local" / "backup"

ABOUT_PREFIXES = ("About ", "关于", "对")
TITLE_SPLIT = {"en": ":", "zh": "·"}
ALLOWED_KEYS = ["id", "name_zh", "name_en", "img_url", "ver", "lines"]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def log(msg=""):
    print(msg, flush=True)


def _session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    s.mount("https://", HTTPAdapter(max_retries=Retry(
        total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])))
    return s


# --------------------------------------------------------------------------
# inputs
# --------------------------------------------------------------------------
def load_prev_data(path=DATA_FILE):
    if not os.path.exists(path):
        log("WARNING: previous data file missing (" + str(path) + ") -> starting empty")
        return []
    with open(path, encoding="utf8") as f:
        return json.load(f)


def load_aliases(path=ALIAS_FILE):
    if not os.path.exists(path):
        log("WARNING: alias file missing (" + str(path) + ")")
        return {}
    with open(path, encoding="utf8") as f:
        return json.load(f)


# Official character list endpoint, currently served behind ys.mihoyo.com. The
# previous URL (ys.mihoyo.com/content/ysCn/getContentList) now answers retcode
# -1; this content_v2 endpoint returns the documented {"data":{"list":[{
# "sTitle","sExt"}],"iTotal":n}} shape. iPageSize must cover all characters in
# one page because only the first page is read.
DEFAULT_URL_ZH = (
    "https://act-api-takumi-static.mihoyo.com/content_v2_user/app/"
    "16471662a82d418a/getContentList?iAppId=43&iChanId=726&iPageSize=200"
    "&iPage=1&sLangKey=zh-cn"
)


def fetch_char_official(url=None, timeout=20):
    """Official website character list -> {name_zh: {id, name_zh, img_url}}.

    Expects {"data": {"list": [{"sTitle", "sExt"}], "iTotal": n}}, the shape of
    the miHoYo content-web (OBC/黑板) API that the official character page uses.
    """
    url = url or os.getenv("URL_ZH") or DEFAULT_URL_ZH
    if not url:
        raise RuntimeError("URL_ZH is not set (official character list endpoint)")

    S = _session()
    response = S.get(url=url, timeout=timeout)
    response.raise_for_status()
    try:
        data = response.json()
    except ValueError as e:
        raise RuntimeError("official list response is not JSON: " + str(response.text)[:200]) from e

    payload = data.get("data") or {}
    char_list = payload.get("list") or []
    if not char_list:
        raise RuntimeError("official list is empty (unexpected response shape: "
                           + str(list(data.keys())) + ")")

    char_count = payload.get("iTotal") or len(char_list)
    char_dict = {}
    missing_img = []
    for i, entry in enumerate(char_list):
        name = entry.get("sTitle")
        if not name:
            continue
        img_url = None
        try:
            ext = json.loads(entry.get("sExt") or "{}")
        except (TypeError, ValueError):
            ext = {}
        for group in ext.values():
            for item in group if isinstance(group, list) else []:
                if not isinstance(item, dict) or "name" not in item:
                    continue
                if (img_url is None
                        and (item["name"].startswith("UI_AvatarIcon_")
                             or item["name"].endswith(name + ".png")
                             or item["name"].endswith("头像.png")
                             or item["name"].endswith("Icon.png"))):
                    img_url = item.get("url")
        if img_url is None:
            missing_img.append(name)
        char_dict[name] = {
            "id": char_count - i,          # newest first in the list -> id 1 = Jean
            "name_zh": name,
            "img_url": img_url or "",
        }
    if missing_img:
        log("  WARNING: no icon url found for " + str(len(missing_img))
            + " official entries: " + ", ".join(missing_img[:12]))
    log("  Official character list: " + str(len(char_dict)) + " entries (iTotal=" + str(char_count) + ")")
    return char_dict


def official_from_prev(prev_dict):
    """Offline stand-in for the official list: everything already in the data."""
    return {name: {"id": c.get("id"), "name_zh": name, "img_url": c.get("img_url", "")}
            for name, c in prev_dict.items()}


# --------------------------------------------------------------------------
# version bookkeeping
# --------------------------------------------------------------------------
def calc_ver(ref_ver=None, ref_date=None, period=None):
    """Estimate the current game version from a reference version + elapsed days.

    REF_VER is a full X.Y.Z version (Z = banner half, 1 or 2) and PERIOD the
    length of one banner half in days. Encoding: X.Y.Z -> X*100 + Y*10 + (Z-1)*5,
    one elapsed period adds 5, then 0 -> ".1" and 5 -> ".2". Returns "" when the
    reference values are unavailable.
    """
    ref_ver = ref_ver if ref_ver is not None else os.getenv("REF_VER", "")
    ref_date = ref_date if ref_date is not None else os.getenv("REF_DATE", "")
    period = period if period is not None else os.getenv("PERIOD", "")
    offset = float(os.getenv("VER_ADJUST", "0") or 0)

    if not ref_ver or not ref_date or not period:
        log("  REF_VER/REF_DATE/PERIOD not fully set -> cannot estimate version")
        return ""
    try:
        parts = ref_ver.strip().split(".")
        if len(parts) < 3:
            parts.append("1")
        half = 0 if parts[-1] in ("1", "0") else 5
        n_ref = int(parts[0]) * 100 + int(parts[1]) * 10 + half
        days = (datetime.now() - datetime.fromisoformat(ref_date.strip())).days
        n = n_ref + (days // int(period)) * 5 + int(round(offset * 100))
    except (ValueError, TypeError) as e:
        log("  WARNING: could not compute version (" + type(e).__name__ + ": " + str(e) + ")")
        return ""
    v = list(str(n))
    v[-1] = {"0": "1", "5": "2"}.get(v[-1], v[-1])
    ver = ".".join(v[:-2] + [v[-2], v[-1]]) if len(v) > 2 else ".".join(v)
    return ver


def max_prev_ver(prev_dict):
    best, best_key = "", (-1, -1, -1)
    for entry in prev_dict.values():
        ver = str(entry.get("ver") or "")
        parts = [(int(p) if p.isdigit() else 0) for p in ver.split(".")]
        parts = (parts + [0, 0, 0])[:3]
        if tuple(parts) > best_key:
            best_key, best = tuple(parts), ver
    return best


def find_new_chars(official_dict, prev_dict):
    """Names listed officially but missing from the data file (release order)."""
    if len(official_dict) <= len(prev_dict):
        # The official list can be shorter than our data (we keep datamined
        # characters too), so compare by membership rather than by count.
        return [name for name in official_dict if name not in prev_dict]
    return [name for name in official_dict if name not in prev_dict]


# --------------------------------------------------------------------------
# graph construction
# --------------------------------------------------------------------------
def filter_data(node_data, edge_data, allowed_names):
    """Keep only the characters we actually track (otherwise voice lines would
    reference placeholder/test avatars)."""
    filtered_node_data, seen = [], set()
    for node in node_data:
        name = node["name_zh"]
        if name in allowed_names and name not in seen:
            filtered_node_data.append(node)
            seen.add(name)
    allowed_ids = {node["avatarId"] for node in filtered_node_data}
    filtered_edge_data = [e for e in edge_data if e.get("avatarId") in allowed_ids]
    return filtered_node_data, filtered_edge_data


def process_title(title, prefix="", remove_about=False, strip=False):
    if strip:
        title = title.rstrip("…")
    if remove_about:
        for s in ABOUT_PREFIXES:
            title = title.removeprefix(s)
    return prefix + title


def process_content(content):
    # the raw data carries literal backslash-n sequences instead of newlines
    return (content or "").replace("\\n", "\n")


def build_target_map(node_data, aliases):
    """name/alias -> avatarId. Real names win; a conflicting alias is reported."""
    target_to_avatarID, conflicts = {}, []
    for char in node_data:
        target_to_avatarID[char["name_zh"]] = char["avatarId"]
        if char.get("name_en"):
            target_to_avatarID[char["name_en"]] = char["avatarId"]

    name_to_avatarID = {c["name_zh"]: c["avatarId"] for c in node_data}
    id_to_name = {c["avatarId"]: c["name_zh"] for c in node_data}
    for char in node_data:
        name = char["name_zh"]
        entry = aliases.get(name) or {}
        for alias in list(entry.get("alias_zh") or []) + list(entry.get("alias_en") or []):
            owner = target_to_avatarID.get(alias)
            if owner is not None and owner != name_to_avatarID[name]:
                conflicts.append(alias + " (already " + str(id_to_name.get(owner, owner))
                                 + " -> " + name + ")")
                continue
            target_to_avatarID[alias] = name_to_avatarID[name]
    if conflicts:
        log("  WARNING: alias conflicts ignored: " + "; ".join(conflicts))
    return target_to_avatarID


def make_graph(edge_data, node_data, aliases=None):
    """Turn raw fetter voice lines into edges speaker -> mentioned character."""
    aliases = aliases if aliases is not None else load_aliases()
    avatarID_to_nameZH = {e["avatarId"]: e["name_zh"] for e in node_data}
    avatarID_to_nameEN = {e["avatarId"]: e["name_en"] for e in node_data}
    target_to_avatarID = build_target_map(node_data, aliases)

    def find_quote_targets(title, curr_avatarID, lang, notes=None):
        targets = set()
        if not title:
            return targets
        if process_title(title, remove_about=True) == title:
            return targets  # not an "about X" line
        target_text = title.split(TITLE_SPLIT[lang])[0].lower()
        for target, avatar_id in target_to_avatarID.items():
            if avatar_id == curr_avatarID or not target:
                continue
            if target.lower() in target_text:
                targets.add(avatar_id)
                if notes is not None and len(target) <= 1 and lang == "zh":
                    notes.append("single-char match: " + target + " in " + repr(title)[:40])
        return targets

    char_dict = {}
    for entry in node_data:
        # first avatar row wins for identical names (e.g. traveller variants)
        char_dict.setdefault(entry["name_zh"], dict(entry, lines=[]))

    notes = []
    matched_lines = 0
    for edge in edge_data:
        targets = set()
        for lang in ("zh", "en"):
            targets |= find_quote_targets(edge["title_" + lang], edge["avatarId"], lang, notes)
        if not targets:
            continue
        source_id = edge["avatarId"]
        source_name = avatarID_to_nameZH[source_id]
        matched_lines += 1
        for target_id in targets:
            char_dict[source_name]["lines"].append({
                "target_zh": avatarID_to_nameZH[target_id],
                "title_zh": process_title(edge["title_zh"], prefix=source_name, strip=True),
                "content_zh": process_content(edge["content_zh"]),
                "target_en": avatarID_to_nameEN[target_id],
                "title_en": (
                    # wiki-sourced lines carry no English title, so rebuild the
                    # same "<Speaker> about <Target>" shape the game tables used
                    process_title(edge["title_en"],
                                  prefix=avatarID_to_nameEN[source_id] + " about ",
                                  remove_about=True, strip=True)
                    if edge.get("title_en")
                    else avatarID_to_nameEN[source_id] + " about "
                    + (avatarID_to_nameEN.get(target_id) or avatarID_to_nameZH[target_id])
                ),
                "content_en": process_content(edge["content_en"]),
            })
    log("  Voice lines resolved to edges: " + str(matched_lines)
        + " of " + str(len(edge_data)) + " raw lines")
    if notes:
        log("  NOTE: " + str(len(notes)) + " matches relied on a single-character name "
            "(possible false positives, e.g. 钢琴 vs 琴)")
    return char_dict


# --------------------------------------------------------------------------
# merge / report / write
# --------------------------------------------------------------------------
def merge_lines(fresh_lines, prev_lines):
    """Union of freshly scraped lines and lines we already ship.

    The wiki can lag behind the game (a voice line added in a later patch is
    simply absent there), so dropping old-only lines would silently lose edges.
    Fresh content wins; old lines whose (target, title) is unknown are kept.
    """
    if not prev_lines:
        return list(fresh_lines or [])
    seen = {(l.get("target_zh"), l.get("title_zh")) for l in fresh_lines or []}
    kept = [l for l in prev_lines if (l.get("target_zh"), l.get("title_zh")) not in seen]
    return list(fresh_lines or []) + kept


def merge_data(char_dict, official_dict, prev_dict, ver, strict_released=False,
               keep_old_lines=True):
    """Combine freshly built characters with official metadata and the old file.

    Returns (merged_dict, new_names, dropped_names, synthesized_names, kept_lines)
    where kept_lines counts characters whose old lines survived a refresh.
    """
    merged, new_names, dropped, synthesized = {}, [], [], []
    kept_lines = []
    used_ids = {c["id"] for c in prev_dict.values() if isinstance(c.get("id"), int)}
    next_id = (max(used_ids) + 1) if used_ids else 1

    for name in official_dict:
        official = official_dict[name] or {}
        prev = prev_dict.get(name)
        char = char_dict.get(name)
        if char is None:
            synthesized.append(name)
            char = {"name_zh": name,
                    "name_en": official.get("name_en") or (prev or {}).get("name_en") or name,
                    "lines": list((prev or {}).get("lines", []))}
        else:
            char = dict(char)
        if prev and isinstance(prev.get("id"), int):
            char["id"] = prev["id"]                  # ids are stable once assigned
        else:
            new_names.append(name)
            candidate = official.get("id")
            if isinstance(candidate, int) and candidate not in used_ids:
                char["id"] = candidate
            else:
                char["id"] = next_id
                next_id += 1
            used_ids.add(char["id"])
            char["ver"] = ver
        if prev:
            char["ver"] = prev.get("ver", ver)
        char["img_url"] = official.get("img_url") or (prev or {}).get("img_url", "")
        if keep_old_lines and prev:
            before = len(char.get("lines") or [])
            char["lines"] = merge_lines(char.get("lines"), prev.get("lines"))
            if len(char["lines"]) > before:
                kept_lines.append((name, len(char["lines"]) - before))
        merged[name] = char

    for name, prev in prev_dict.items():
        if name in merged:
            continue
        if strict_released:
            dropped.append(name)
            continue
        # Characters we already ship but the official list does not show yet
        # (datamined / not released): keep them, refreshed when the raw data
        # still describes them, otherwise carried over untouched.
        char = char_dict.get(name)
        char = dict(char) if char is not None else dict(prev)
        char["id"] = prev.get("id")
        char["ver"] = prev.get("ver", "")
        char["img_url"] = prev.get("img_url", "")
        char["name_en"] = char.get("name_en") or prev.get("name_en", name)
        char["lines"] = merge_lines(char.get("lines"), prev.get("lines"))
        used_ids.add(char["id"])
        merged[name] = char

    if synthesized:
        log("  WARNING: tracked but no fresh voice data: "
            + ", ".join(synthesized[:10]) + (" …" if len(synthesized) > 10 else ""))
    if kept_lines:
        total = sum(n for _, n in kept_lines)
        log("  Kept " + str(total) + " line(s) that the wiki no longer lists, across "
            + str(len(kept_lines)) + " character(s): "
            + ", ".join(name + "(+" + str(n) + ")" for name, n in kept_lines[:8])
            + (" …" if len(kept_lines) > 8 else ""))
    return merged, new_names, dropped, synthesized, kept_lines


def build_report(char_dict, prev_dict, new_names, dropped):
    prev_lines = {n: len(c.get("lines", [])) for n, c in prev_dict.items()}
    now_lines = {n: len(c.get("lines", [])) for n, c in char_dict.items()}
    added = [n for n in char_dict if n not in prev_dict]
    removed = [n for n in prev_dict if n not in char_dict]
    changed = sorted(((n, now_lines[n] - prev_lines.get(n, 0)) for n in char_dict
                      if now_lines[n] != prev_lines.get(n, 0)),
                     key=lambda x: -abs(x[1]))
    total_prev = sum(prev_lines.values())
    total_now = sum(now_lines.values())
    return {
        "chars_prev": len(prev_dict), "chars_now": len(char_dict),
        "lines_prev": total_prev, "lines_now": total_now,
        "new_names": new_names, "added": added, "removed": removed,
        "dropped_by_strict": dropped, "changed": changed,
    }


def print_report(rep):
    log("")
    log("=== 更新报告 / update report ===")
    log("  角色 characters : " + str(rep["chars_prev"]) + " -> " + str(rep["chars_now"]))
    log("  语音边 edges     : " + str(rep["lines_prev"]) + " -> " + str(rep["lines_now"])
        + " (+" + str(rep["lines_now"] - rep["lines_prev"]) + ")")
    if rep["new_names"]:
        log("  新增 new         : " + ", ".join(rep["new_names"]))
    if rep["removed"]:
        log("  消失 gone        : " + ", ".join(rep["removed"]))
    if rep["dropped_by_strict"]:
        log("  已剔除 dropped   : " + str(len(rep["dropped_by_strict"])) + " -> "
            + ", ".join(rep["dropped_by_strict"][:20]))
    log("  语音变化 changed (top 25):")
    for name, delta in rep["changed"][:25]:
        log("    " + ("+" if delta > 0 else "") + str(delta) + "  " + name)
    log("")


def validate(char_dict, prev_dict):
    """Hard integrity gate: never write a file that the page cannot render."""
    errors, warnings = [], []
    names_zh = {c["name_zh"] for c in char_dict.values()}
    names_en = {c["name_en"] for c in char_dict.values()}
    ids = {}
    for name, char in char_dict.items():
        for key in ALLOWED_KEYS:
            if key not in char:
                errors.append(name + " missing key " + key)
        ids.setdefault(char["id"], []).append(name)
        if not char.get("img_url"):
            warnings.append(name + " has no icon url")
        if not char.get("ver"):
            warnings.append(name + " has no version tag")
        for line in char.get("lines", []):
            if line["target_zh"] not in names_zh or line["target_en"] not in names_en:
                errors.append(name + " -> unknown target " + line["target_zh"])
    for id_, owners in ids.items():
        if len(owners) > 1:
            errors.append("duplicate id " + str(id_) + " used by " + ", ".join(owners))
    if len(char_dict) < len(prev_dict):
        errors.append("character count shrank from " + str(len(prev_dict)) + " to "
                      + str(len(char_dict)) + " (refusing to delete characters)")
    for w in warnings[:10]:
        log("  WARNING: " + w)
    if len(warnings) > 10:
        log("  WARNING: … and " + str(len(warnings) - 10) + " more")
    if errors:
        for e in errors[:20]:
            log("  ERROR: " + e)
        raise ValueError("validation failed with " + str(len(errors)) + " error(s); "
                         "nothing was written")
    log("  Validation OK: " + str(len(char_dict)) + " characters, no duplicate ids, "
        "all edge targets resolvable")


def write_data_file(char_dict, data_file=DATA_FILE, data_file_min=DATA_FILE_MIN):
    char_data = [{k: char[k] for k in ALLOWED_KEYS} for char in char_dict.values()]
    char_data.sort(key=lambda x: x["id"])
    text = json.dumps(char_data, ensure_ascii=False, indent=4)
    with open(data_file, "w", encoding="utf8") as f:
        f.write(text)
    with open(data_file_min, "w", encoding="utf8") as f:
        f.write(json.dumps(char_data, ensure_ascii=False, separators=(",", ":")))
    log("  Wrote " + str(os.path.getsize(data_file)) + " bytes -> "
        + str(data_file) + " (+" + str(os.path.getsize(data_file_min)) + " min)")
    return char_data


def backup_data(reason="pre-update"):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_ROOT / (stamp + "-" + reason)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "data").mkdir(exist_ok=True)
    for src in (DATA_FILE, DATA_FILE_MIN, ALIAS_FILE):
        if os.path.exists(src):
            shutil.copy2(src, dest / "data" / os.path.basename(src))
    log("  Backup of the previous data -> " + str(dest))
    return dest


# --------------------------------------------------------------------------
# CI side effects
# --------------------------------------------------------------------------
def in_git_repo():
    try:
        out = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                             capture_output=True, text=True, cwd=str(REPO_ROOT))
        return out.returncode == 0 and out.stdout.strip() == "true"
    except OSError:
        return False


def commit_changes(msg):
    if not in_git_repo():
        log("  Not a git checkout -> skipping commit")
        return False
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=str(REPO_ROOT)).returncode == 0:
        log("  Nothing staged -> skipping commit")
        return False
    author = "github-actions[bot]"
    email = "41898282+github-actions[bot]@users.noreply.github.com"
    for cmd in (["git", "config", "user.name", author], ["git", "config", "user.email", email],
                ["git", "add", "."], ["git", "commit", "-m", msg], ["git", "push"]):
        subprocess.run(cmd, check=True, cwd=str(REPO_ROOT))
    return True


def send_message(msg):
    try:
        payload = {}
        raw = os.getenv("PAYLOAD1")
        if raw and "=" in raw:
            k, v = raw.split("=", 1)
            payload[k] = v
        url = os.getenv("MSG_URL")
        if not url:
            log("  MSG_URL not set -> skipping notification")
            return
        requests.get(url, params=dict(payload, text=msg), timeout=15)
    except Exception:
        traceback.print_exc()


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main(refresh=False, offline=False, dry_run=False, strict_released=False,
         ver_override=None, url_zh=None, data_base_url=None, max_age_hours=24,
         force_download=False, do_images=True, force_images=False,
         do_notion=True, do_backup=True, source="wiki", keep_old_lines=True):
    with open(DATA_FILE, encoding="utf8") if False else open(str(DATA_FILE), encoding="utf8")             if os.path.exists(DATA_FILE) else _NullCtx() as _f:
        pass
    data_prev = load_prev_data()
    prev_dict = {char["name_zh"]: char for char in data_prev}
    log("Loaded previous data: " + str(len(prev_dict)) + " characters")

    ver = ver_override or calc_ver()
    if not ver:
        ver = max_prev_ver(prev_dict)
        log("  Using the newest known version as the default ver tag: " + ver)
    log("Updating for v" + ver)

    # 1. the tracked-character universe ("official list")
    if source == "hoyolab":
        # official miHoYo wiki: OBC channel list + HoYoLab bilingual voice pages
        from hoyolab_source import build_dataset
        node_data, edge_data = build_dataset(data_prev)
        official_dict = {
            n["name_zh"]: {
                # ids stay None for newcomers so merge_data allocates max(id)+1
                "id": n["avatarId"] if n["name_zh"] in prev_dict else None,
                "name_zh": n["name_zh"],
                "name_en": n.get("name_en") or "",
                "img_url": n.get("img_url", ""),
            }
            for n in node_data
        }
        log("  Official universe: " + str(len(official_dict)) + " tracked characters")
        new_names = find_new_chars(official_dict, prev_dict)
    elif offline:
        official_dict = official_from_prev(prev_dict)
        new_names = []
        log("  OFFLINE mode: the official list is replaced by the existing data "
            "(" + str(len(official_dict)) + " names); no brand-new character can be detected")
    else:
        try:
            official_dict = fetch_char_official(url_zh)
        except Exception as e:
            log("  ERROR: cannot fetch the official character list: " + str(e)[:200])
            if not refresh:
                raise
            log("  Falling back to offline mode (refresh of existing characters only)")
            official_dict = official_from_prev(prev_dict)
        new_names = find_new_chars(official_dict, prev_dict)

    if not new_names and not refresh:
        log("No new chars found (use --refresh to rebuild voice lines anyway)")
        return 0
    if new_names:
        log("  New char " + " ".join(new_names))
    elif refresh:
        log("  Refreshing lines for existing characters")

    # 2. raw game data (legacy --source excel path only)
    if source != "hoyolab":
        download_data(url_base=data_base_url, max_age_hours=max_age_hours,
                      force=force_download)
        node_data, edge_data = prepare_data()

    # 3. build the graph over the union of official + already tracked characters
    allowed = set(official_dict) | set(prev_dict)
    node_data, edge_data = filter_data(node_data, edge_data, allowed)
    char_dict = make_graph(edge_data, node_data)

    # 4. merge, report, validate
    merged, new_names, dropped, _synth, _kept = merge_data(
        char_dict, official_dict, prev_dict, ver, strict_released=strict_released,
        keep_old_lines=keep_old_lines)
    unnamed = [n for n, c in merged.items() if not c.get("name_en")]
    for n in unnamed:
        merged[n]["name_en"] = n  # name_en is the node id in page/script.js
    if unnamed:
        log("  WARNING: no English name for " + str(len(unnamed))
            + " character(s), using the Chinese name as id: " + ", ".join(unnamed[:8]))

    rep = build_report(merged, prev_dict, new_names, dropped)
    print_report(rep)
    validate(merged, prev_dict)

    if dry_run:
        log("DRY RUN: nothing written")
        return 0

    # 5. write, mirror, icons
    if do_backup:
        backup_data()
    write_data_file(merged)

    if do_notion:
        try:
            from notion_db import update_remote_table
            update_remote_table(merged, new_names)
        except Exception as e:
            log("  Skipped Notion sync: " + str(e)[:200])

    if do_images:
        download_images(str(DATA_FILE), str(IMAGE_DIR), force=force_images)

    commit_msg = ("v" + ver + " " + " ".join(
        char["name_zh"] + char["name_en"] for char in merged.values() if char.get("ver") == ver))
    if os.getenv("GITHUB_ACTIONS") is not None:
        log("Committing changes —— " + commit_msg)
        commit_changes(commit_msg)
        send_message(commit_msg)
    else:
        log("Commit message: " + commit_msg)
    log("Done.")
    return 0


class _NullCtx:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Update the Genshin social-network data files")
    p.add_argument("--refresh", action="store_true",
                   help="rebuild voice lines even when no new character appeared")
    p.add_argument("--offline", action="store_true",
                   help="skip the official character list (refresh from datamined data only)")
    p.add_argument("--dry-run", action="store_true",
                   help="compute and report everything, write nothing")
    p.add_argument("--strict-released", action="store_true",
                   help="drop characters that are missing from the official list "
                        "(old behaviour; deletes datamined characters)")
    p.add_argument("--ver", help="override the estimated game version, e.g. 7.1.2")
    p.add_argument("--url-zh", help="official character list endpoint (else $URL_ZH)")
    p.add_argument("--data-base-url", help="datamined JSON base url (else $DATA_REPO_URL)")
    p.add_argument("--max-age-hours", type=float, default=24,
                   help="reuse cached raw files younger than this (default 24)")
    p.add_argument("--force-download", action="store_true", help="ignore the raw file cache")
    p.add_argument("--no-images", action="store_true", help="skip icon downloads")
    p.add_argument("--force-images", action="store_true", help="re-download existing icons")
    p.add_argument("--no-notion", action="store_true", help="skip the Notion mirror step")
    p.add_argument("--no-backup", action="store_true", help="skip the pre-write backup")
    p.add_argument("--replace-lines", action="store_true",
                   help="drop voice lines that the current source no longer lists "
                        "(default: keep them, the wiki can lag behind the game)")
    p.add_argument("--source", choices=["excel", "hoyolab"], default="excel",
                   help="excel = datamined ExcelBinOutput tables (default: the game's "
                        "own fetter text; needs DATA_REPO_URL, which defaults to a live "
                        "mirror); hoyolab = official wiki bilingual voice pages")
    return p.parse_args(argv)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    a = parse_args()
    sys.exit(main(
        refresh=a.refresh, offline=a.offline, dry_run=a.dry_run,
        strict_released=a.strict_released, ver_override=a.ver, url_zh=a.url_zh,
        data_base_url=a.data_base_url, max_age_hours=a.max_age_hours,
        force_download=a.force_download, do_images=not a.no_images,
        force_images=a.force_images, do_notion=not a.no_notion,
        do_backup=not a.no_backup, source=a.source,
        keep_old_lines=not a.replace_lines))
