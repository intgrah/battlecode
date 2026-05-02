"""Translate a Rust pyrust bot into a standalone Python bot.

Usage:
    uv run python scripts/translate_rs.py v55
    uv run python scripts/translate_rs.py rs/v55
    uv run python scripts/translate_rs.py rs/v55 -o bots/build/v55
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_BOTS = _ROOT / "bots"
_BUILD = _BOTS / "build"
_TRANSLATOR = _ROOT / "target" / "debug" / "pyrust-translate"

_PYPROJECT = """[project]
name = "{name}"
version = "0.0.0"
requires-python = ">=3.12,<3.14"
dependencies = ["cambc", "visualiser"]

[tool.ty.environment]
root = ["."]
"""


def _resolve_src(bot_arg: str) -> Path:
    p = Path(bot_arg)
    candidates = [p, _BOTS / bot_arg, _BOTS / "rs" / bot_arg]
    for c in candidates:
        if (c / "src" / "lib.rs").is_file():
            return c
    msg = f"Rust bot not found (need <dir>/src/lib.rs): {bot_arg}"
    raise FileNotFoundError(msg)


def _build_translator() -> None:
    subprocess.run(
        ["cargo", "build", "-p", "pyrust-translate", "--bin", "pyrust-translate"],
        cwd=_ROOT,
        check=True,
    )


def translate(src_dir: Path, out_dir: Path) -> Path:
    if not _TRANSLATOR.is_file():
        _build_translator()
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [str(_TRANSLATOR), "--dir", str(src_dir / "src"), "-o", str(out_dir)],
        check=True,
    )
    py_name = f"bot-{out_dir.name.replace('.', '-')}"
    (out_dir / "pyproject.toml").write_text(_PYPROJECT.format(name=py_name))
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser(description="Translate a Rust pyrust bot to Python.")
    ap.add_argument("bot", help="Rust bot dir, e.g. v55 or rs/v55")
    ap.add_argument(
        "-o",
        "--output",
        help="Output dir (default: bots/build/<bot_name>)",
    )
    args = ap.parse_args()
    src = _resolve_src(args.bot)
    out = Path(args.output) if args.output else _BUILD / src.name
    out_path = translate(src, out)
    print(out_path)


if __name__ == "__main__":
    sys.exit(main())
