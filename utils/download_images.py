"""Download character icons into data/image/.

Fixes vs. the previous revision
  * works from any CWD (absolute paths derived from the repo root)
  * tolerates a missing/None img_url instead of raising KeyError
  * always stores the icon as <name_zh>.png because page/script.js hardcodes
    the ".png" suffix; the actual bytes are sniffed by the browser anyway
  * validates the downloaded bytes (non-empty, image magic) and retries
  * --force re-downloads (use after an icon URL changed upstream); the old
    "skip if the file exists" rule silently kept stale icons forever
"""

import json
import os
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA = os.path.join(REPO_ROOT, "data", "char_data.json")
DEFAULT_IMAGE_DIR = os.path.join(REPO_ROOT, "data", "image")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

MAGIC = (b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"RIFF", b"<svg", b"<?xml")


def _session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    s.mount("https://", HTTPAdapter(max_retries=Retry(
        total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])))
    return s


def _looks_like_image(path):
    try:
        with open(path, "rb") as f:
            head = f.read(16)
    except OSError:
        return False
    if len(head) < 16:
        return False
    return any(head.startswith(m) for m in MAGIC)


def download_images(char_data_path=DEFAULT_DATA, image_dir=DEFAULT_IMAGE_DIR, force=False):
    with open(char_data_path, encoding="utf-8") as f:
        char_data = json.load(f)
    os.makedirs(image_dir, exist_ok=True)

    session = _session()
    stats = {"downloaded": 0, "skipped": 0, "failed": 0, "no_url": 0}
    for char in char_data:
        url = (char.get("img_url") or "").strip()
        name = char["name_zh"]
        filepath = os.path.join(image_dir, name + ".png")
        if not url:
            print("  no icon url for " + name)
            stats["no_url"] += 1
            continue
        if not force and os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            stats["skipped"] += 1
            continue
        try:
            response = session.get(url, stream=True, timeout=20)
            response.raise_for_status()
            tmp = filepath + ".part"
            with open(tmp, "wb") as f:
                for chunk in response.iter_content(chunk_size=65536):
                    f.write(chunk)
            if not _looks_like_image(tmp):
                os.remove(tmp)
                raise ValueError("response is not an image")
            os.replace(tmp, filepath)
            print("  Downloaded " + os.path.basename(filepath) + " <- " + urlparse(url).netloc)
            stats["downloaded"] += 1
        except Exception as e:
            print("  Error downloading " + name + ": " + type(e).__name__ + " " + str(e)[:100])
            stats["failed"] += 1
    print("  Icons: " + str(stats["downloaded"]) + " downloaded, "
          + str(stats["skipped"]) + " already present, "
          + str(stats["failed"]) + " failed, " + str(stats["no_url"]) + " without url")
    return stats


if __name__ == "__main__":
    download_images()
