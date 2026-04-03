import json
import time
import urllib.request
from pathlib import Path

from cambc import __version__

PYPI_PACKAGE = "cambc"
CACHE_DIR = Path.home() / ".cambc"
CACHE_FILE = CACHE_DIR / "version_cache.json"
CHECK_INTERVAL = 300  # seconds between PyPI checks


def check_for_update() -> str | None:
    """Return latest version string if newer than current, else None.

    Caches the result to avoid hitting PyPI on every invocation.
    Never raises — silently returns None on any failure.
    """
    try:
        latest = _cached_latest_version()
        if latest and latest != __version__ and _is_newer(latest, __version__):
            return latest
    except Exception:
        pass
    return None


def _cached_latest_version() -> str | None:
    now = time.time()

    # Try reading cache
    if CACHE_FILE.exists():
        try:
            data = json.loads(CACHE_FILE.read_text())
            if now - data.get("ts", 0) < CHECK_INTERVAL:
                return data.get("version")
        except Exception:
            pass

    # Fetch from PyPI
    version = _fetch_latest_version()
    if version:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            CACHE_FILE.write_text(json.dumps({"version": version, "ts": now}))
        except Exception:
            pass
    return version


def _fetch_latest_version() -> str | None:
    try:
        req = urllib.request.Request(
            f"https://pypi.org/pypi/{PYPI_PACKAGE}/json",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
            return data["info"]["version"]
    except Exception:
        return None


def _is_newer(latest: str, current: str) -> bool:
    """Simple version comparison (major.minor.patch)."""
    try:
        def parts(v: str) -> tuple[int, ...]:
            return tuple(int(x) for x in v.split("."))
        return parts(latest) > parts(current)
    except Exception:
        return False
