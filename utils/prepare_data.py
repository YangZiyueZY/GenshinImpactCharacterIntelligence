"""Download and decode the raw game-data tables that feed the social graph.

Fixes vs. the previous revision
  * paths are resolved from the repo root, so the script runs from any CWD
  * required vs. optional source files are distinguished: a failed download of a
    required file aborts with a clear message instead of crashing later with a
    KeyError deep inside prepare_data()
  * cached files are validated (parseable + non-empty) before being reused
  * downloads are atomic (*.part -> final name) and retried
  * every TextMap lookup tolerates unknown hashes (previously one missing hash
    killed the whole run)
"""

import json
import os
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_RAW_DIR = os.path.join(REPO_ROOT, "data_raw")

# Live mirror of the datamined tables (verified 2026-11: all 7 files, including
# the 51 MB TextMapCHS). Dimbreath/AnimeData and Dimbreath/GenshinData are gone.
DEFAULT_DATA_REPO_URL = (
    "https://raw.githubusercontent.com/DimbreathBot/AnimeGameData/main/"
)
# Mirrors, tried in order per file. The 50 MB+ TextMaps regularly fail over a
# plain raw.githubusercontent.com connection (proxy resets), so a failing file
# falls over to the next host instead of aborting the run. jsDelivr is not in
# this list: it refuses anything above 20 MB with 403.
DATA_REPO_MIRRORS = (
    "https://raw.githack.com/DimbreathBot/AnimeGameData/main/",
    "https://gh-proxy.com/https://raw.githubusercontent.com/DimbreathBot/AnimeGameData/main/",
    "https://ghfast.top/https://raw.githubusercontent.com/DimbreathBot/AnimeGameData/main/",
)

# Without these the graph cannot be built at all.
REQUIRED_FILES = {
    "node_data": "ExcelBinOutput/AvatarExcelConfigData.json",
    "edge_data": "ExcelBinOutput/FettersExcelConfigData.json",
    "textmap_zh": "TextMap/TextMapCHS.json",
    "textmap_en": "TextMap/TextMapEN.json",
}
# A missing optional file only degrades quality (element/region, medium textmaps).
OPTIONAL_FILES = {
    "node_data_extra": "ExcelBinOutput/FetterInfoExcelConfigData.json",
    "textmap_medium_zh": "TextMap/TextMap_MediumCHS.json",
    "textmap_medium_en": "TextMap/TextMap_MediumEN.json",
}
data_path = {**REQUIRED_FILES, **OPTIONAL_FILES}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def _session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    s.mount("https://", HTTPAdapter(max_retries=Retry(
        total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])))
    return s


def local_path_of(path, raw_dir=DEFAULT_RAW_DIR):
    return os.path.join(raw_dir, path.split("/")[-1])


def _is_fresh(filepath, max_age_hours):
    if not os.path.exists(filepath):
        return False
    return (time.time() - os.path.getmtime(filepath)) / 3600 < max_age_hours


def _is_valid_json(filepath, min_bytes=8):
    """A cached file is only reusable when it really holds a JSON document."""
    if not os.path.exists(filepath) or os.path.getsize(filepath) < min_bytes:
        return False
    try:
        with open(filepath, encoding="utf-8") as f:
            json.load(f)
        return True
    except Exception:
        return False


def download_file(url, download_path, session=None, timeout=60):
    """Atomic download. Returns True on success."""
    session = session or _session()
    tmp = download_path + ".part"
    os.makedirs(os.path.dirname(download_path), exist_ok=True)
    try:
        with session.get(url, timeout=timeout, stream=True) as response:
            response.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in response.iter_content(chunk_size=65536):
                    f.write(chunk)
        os.replace(tmp, download_path)
        return True
    except Exception as e:
        print("    download failed: " + url + " (" + type(e).__name__ + ": " + str(e)[:120] + ")")
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        return False


def download_data(url_base=None, raw_dir=DEFAULT_RAW_DIR, max_age_hours=24, force=False):
    """Fetch every source table; abort when a required table is unavailable.

    url_base defaults to the DATA_REPO_URL env var and must point at the *root*
    of a datamined JSON mirror, e.g. https://host/<owner>/<repo>/raw/<branch>/
    """
    url_base = url_base or os.getenv("DATA_REPO_URL") or DEFAULT_DATA_REPO_URL
    os.makedirs(raw_dir, exist_ok=True)
    summary = {"downloaded": [], "cached": [], "missing_required": [], "missing_optional": []}

    if not url_base:
        # Offline mode: reuse whatever is already cached.
        for key, path in data_path.items():
            fp = local_path_of(path, raw_dir)
            if _is_valid_json(fp):
                summary["cached"].append(fp)
            elif key in REQUIRED_FILES:
                summary["missing_required"].append(os.path.basename(path))
        if summary["missing_required"]:
            raise RuntimeError(
                "DATA_REPO_URL is not set and required sources are not cached: "
                + ", ".join(summary["missing_required"]))
        print("  DATA_REPO_URL unset -> working from cached data_raw/ only")
        return summary

    url_base = url_base.rstrip("/") + "/"
    bases = [url_base] + [m for m in DATA_REPO_MIRRORS if m != url_base]
    session = _session()
    for key, path in data_path.items():
        download_path = local_path_of(path, raw_dir)
        if not force and _is_fresh(download_path, max_age_hours) and _is_valid_json(download_path):
            print("  Skipping " + os.path.basename(download_path)
                  + ", cache younger than " + str(max_age_hours) + "h")
            summary["cached"].append(download_path)
            continue
        ok = False
        for base in bases:
            url = base + path
            # "?inline=false" is only meaningful on some hosts and harmless elsewhere
            if "?" not in url:
                url += "?inline=false"
            if download_file(url, download_path, session):
                ok = True
                break
            print("    falling back to the next mirror for " + os.path.basename(path))
        if ok:
            print("  Downloaded " + os.path.basename(download_path)
                  + " (" + str(os.path.getsize(download_path)) + " bytes)")
            summary["downloaded"].append(download_path)
        elif _is_valid_json(download_path):
            print("  Kept stale cache for " + os.path.basename(download_path))
            summary["cached"].append(download_path)
        elif key in REQUIRED_FILES:
            summary["missing_required"].append(os.path.basename(path))
        else:
            summary["missing_optional"].append(os.path.basename(path))

    if summary["missing_required"]:
        raise RuntimeError("Failed to obtain required source files: "
                           + ", ".join(summary["missing_required"])
                           + " (base url: " + url_base + ")")
    if summary["missing_optional"]:
        print("  Optional files unavailable: " + ", ".join(summary["missing_optional"]))
    return summary


def load_json(path, raw_dir=DEFAULT_RAW_DIR, required=True):
    full_path = local_path_of(path, raw_dir)
    if not os.path.exists(full_path):
        if required:
            raise FileNotFoundError("missing required source file: " + full_path)
        print("  note: optional file absent -> " + os.path.basename(full_path))
        return {}
    with open(full_path, encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError("corrupt JSON in " + full_path + ": " + str(e)) from e


def _tm(textmap, key, default=""):
    """TextMap lookup by numeric hash, tolerant of unknown hashes."""
    if key is None:
        return default
    return textmap.get(str(key), default)


def prepare_data(raw_dir=DEFAULT_RAW_DIR):
    """Build (node_data, edge_data) from the raw tables in raw_dir."""
    data_raw = {k: load_json(v, raw_dir, required=k in REQUIRED_FILES)
                for k, v in data_path.items()}

    # The "Medium" textmaps are alternate-length variants; merge when present.
    data_raw["textmap_zh"] = {**data_raw.get("textmap_medium_zh", {}), **data_raw["textmap_zh"]}
    data_raw["textmap_en"] = {**data_raw.get("textmap_medium_en", {}), **data_raw["textmap_en"]}

    extra_map = {}
    for node in data_raw.get("node_data_extra") or []:
        avatar_id = node.get("avatarId")
        if avatar_id is None:
            continue
        extra_map[avatar_id] = {
            "element": _tm(data_raw["textmap_zh"], node.get("avatarVisionBeforTextMapHash")),
            "region": node.get("avatarAssocType") or "",
        }

    node_data, skipped_nodes = [], []
    for node_raw in data_raw["node_data"]:
        avatar_id = node_raw.get("id")
        name_zh = _tm(data_raw["textmap_zh"], node_raw.get("nameTextMapHash"))
        name_en = _tm(data_raw["textmap_en"], node_raw.get("nameTextMapHash"))
        if avatar_id is None or not name_zh:
            skipped_nodes.append(avatar_id)
            continue
        extra = extra_map.get(avatar_id, {})
        node_data.append({
            "avatarId": avatar_id,
            "name_zh": name_zh,
            "name_en": name_en or name_zh,
            "rarity": 5 if node_raw.get("qualityType") == "QUALITY_ORANGE" else 4,
            "bodyType": node_raw.get("bodyType", ""),
            "weaponType": node_raw.get("weaponType", ""),
            "element": extra.get("element", ""),
            "region": (extra.get("region", "") or "").split("_")[-1],
        })
    if skipped_nodes:
        print("  Skipped " + str(len(skipped_nodes)) + " avatar rows without a usable name")

    edge_data, empty_edges = [], 0
    for edge_raw in data_raw["edge_data"]:
        title_zh = _tm(data_raw["textmap_zh"], edge_raw.get("voiceTitleTextMapHash"))
        title_en = _tm(data_raw["textmap_en"], edge_raw.get("voiceTitleTextMapHash"))
        if not title_zh and not title_en:
            empty_edges += 1
            continue
        edge_data.append({
            "avatarId": edge_raw.get("avatarId"),
            "fetterId": edge_raw.get("fetterId"),
            "title_zh": title_zh,
            "title_en": title_en,
            "content_zh": _tm(data_raw["textmap_zh"], edge_raw.get("voiceFileTextTextMapHash")),
            "content_en": _tm(data_raw["textmap_en"], edge_raw.get("voiceFileTextTextMapHash")),
        })
    if empty_edges:
        print("  Dropped " + str(empty_edges) + " fetter rows with no resolvable voice title")

    print("  Prepared " + str(len(node_data)) + " avatar nodes, "
          + str(len(edge_data)) + " raw voice lines")
    return node_data, edge_data


if __name__ == "__main__":
    download_data()
    prepare_data()
