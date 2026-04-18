"""Build a submittable bot zip with symlinks dereferenced.

Usage:
    uv run build <bot_path>
    uv run build intgrah/v54.5.0
    uv run build bots/intgrah/v54.5.0

Produces bots/build/<owner>/<name>.zip (directory created if missing).
"""

from __future__ import annotations

import argparse
import os
import zipfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_BOTS = _ROOT / "bots"
_BUILD = _BOTS / "build"

_JUNK_DIRS = {"__pycache__", ".venv", ".git", "build", "dist"}
_JUNK_SUFFIXES = {".pyc", ".pyo", ".zip"}


def _should_skip(name: str) -> bool:
    return name in _JUNK_DIRS or any(name.endswith(s) for s in _JUNK_SUFFIXES)


def _resolve_bot(bot_arg: str) -> Path:
    p = Path(bot_arg)
    if p.is_absolute():
        return p
    cand = _BOTS / bot_arg
    if cand.is_dir():
        return cand
    if p.is_dir():
        return p.resolve()
    msg = f"Bot not found: {bot_arg}"
    raise FileNotFoundError(msg)


def build(bot_dir: Path) -> Path:
    if not (bot_dir / "main.py").is_file():
        msg = f"{bot_dir} has no main.py"
        raise FileNotFoundError(msg)
    rel = bot_dir.relative_to(_BOTS)
    out = _BUILD / f"{rel}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    seen: set[Path] = set()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(bot_dir, followlinks=True):
            root_path = Path(root)
            real = root_path.resolve()
            if real in seen:
                dirs[:] = []
                continue
            seen.add(real)
            dirs[:] = sorted(d for d in dirs if not _should_skip(d))
            for f in sorted(files):
                if _should_skip(f):
                    continue
                src = root_path / f
                arc = src.relative_to(bot_dir)
                zf.write(src.resolve(), arcname=str(arc))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a submittable bot zip.")
    ap.add_argument("bot", help="Bot path, e.g. intgrah/v54.5.0")
    args = ap.parse_args()
    bot_dir = _resolve_bot(args.bot)
    out = build(bot_dir)
    print(out)


if __name__ == "__main__":
    main()
