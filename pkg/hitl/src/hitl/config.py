"""Runtime configuration for the HITL service."""

from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_ROOT = Path(__file__).resolve().parent.parent.parent / "data"


def data_root() -> Path:
    """Directory containing db + blobs + pngs."""
    return Path(os.environ.get("HITL_DATA", str(_DEFAULT_ROOT)))


def db_path() -> Path:
    return data_root() / "hitl.sqlite"


def blobs_dir() -> Path:
    d = data_root() / "blobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def pngs_dir() -> Path:
    d = data_root() / "pngs"
    d.mkdir(parents=True, exist_ok=True)
    return d
