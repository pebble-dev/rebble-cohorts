"""Background fetcher for coredevices/PebbleOS firmware releases.

Maintains the authoritative in-memory firmware config: seeded from the
committed config.json (rebble baseline), then rebuilt on each refresh by
layering the GitHub Releases API on top. Every hardware entry ends up
with a ready-to-serve `url` — coredevices entries point at the GitHub
release CDN, rebble entries at the configured firmware_root.
"""
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO = "coredevices/PebbleOS"
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.json"
REFRESH_INTERVAL = 6 * 60 * 60  # 6 hours
RETRY_INTERVAL = 10 * 60        # 10 minutes after a failed fetch

ASSET_RE = re.compile(r"^(normal|recovery)_([A-Za-z0-9_]+?)_v([0-9][0-9A-Za-z.\-]*)\.pbz$")

logger = logging.getLogger(__name__)


def load_baseline():
    with open(CONFIG_PATH) as fp:
        return json.load(fp)


class FirmwareConfig:
    """Thread-safe holder for the merged firmware config dict."""

    def __init__(self, firmware_root):
        self._lock = threading.Lock()
        self._firmware_root = firmware_root
        self._current = _populate_rebble_urls(load_baseline(), firmware_root)

    @property
    def firmware_root(self):
        return self._firmware_root

    def get(self):
        with self._lock:
            return self._current

    def set(self, new_config):
        with self._lock:
            self._current = new_config


def _fetch_releases():
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    releases = []

    response = requests.get(
        f"https://api.github.com/repos/{REPO}/releases",
        params={"per_page": 10},
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    releases.extend(data)
    return releases


def _parse_ts(iso):
    return int(datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")
               .replace(tzinfo=timezone.utc).timestamp())


def _populate_rebble_urls(config, firmware_root):
    for hardware, kinds in config.get("hardware", {}).items():
        for kind, info in kinds.items():
            info.setdefault(
                "url",
                "{root}/{hw}/Pebble-{version}-{hw}.pbz".format(
                    root=firmware_root, hw=hardware, version=info["version"]
                ),
            )
    return config


def build_config(firmware_root):
    """Return a fresh config dict: baseline with GH releases layered on top."""
    config = load_baseline()
    config.setdefault("hardware", {})
    config.setdefault("timestamps", {})

    releases = _fetch_releases()
    releases.sort(key=lambda rel: rel["published_at"], reverse=True)

    # Iterate newest-first: first write wins per (hw,kind), later writes
    # overwrite per version-timestamp (so we keep the earliest release ts
    # that contained a given version).
    seen = set()
    for release in releases:
        timestamp = _parse_ts(release["published_at"])
        for asset in release.get("assets", []):
            match = ASSET_RE.match(asset["name"])
            if not match:
                continue
            kind, hardware, version = match.group(1), match.group(2), match.group(3)
            digest = asset.get("digest") or ""
            if not digest.startswith("sha256:"):
                continue
            config["timestamps"][version] = timestamp
            if (hardware, kind) in seen:
                continue
            seen.add((hardware, kind))
            config["hardware"].setdefault(hardware, {})[kind] = {
                "version": version,
                "sha-256": digest.split(":", 1)[1],
                "url": asset["browser_download_url"],
            }
    return _populate_rebble_urls(config, firmware_root)


def start(holder):
    def loop():
        while True:
            try:
                holder.set(build_config(holder.firmware_root))
                hw_count = len(holder.get().get("hardware", {}))
                logger.info("refreshed firmware config (%d hardware entries)", hw_count)
                sleep = REFRESH_INTERVAL
            except Exception:
                logger.exception("firmware fetch failed; will retry")
                sleep = RETRY_INTERVAL
            time.sleep(sleep)

    thread = threading.Thread(target=loop, name="firmware-fetcher", daemon=True)
    thread.start()
    return thread
