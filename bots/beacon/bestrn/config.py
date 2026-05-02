"""
Translation of `bots/intgrah/v54.7.9/config.py`.

Debug flags. Python reads these from environment variables; Rust reads them
once via `option_env!` at compile time so they're zero-overhead in release
builds. Set `DEBUG_DUMP=1`, `DEBUG_LOG=1`, etc. as build-time env vars.
"""
from __future__ import annotations

from typing import Final

DEBUG_RESIGN: Final[bool] = (__import__('os').environ.get("DEBUG_RESIGN") is not None)
"""Resign upon error."""
DEBUG_DUMP: Final[bool] = (__import__('os').environ.get("DEBUG_DUMP") is not None)
"""Dump using rich debugging. This slows down the bot a lot."""
DEBUG_LOG: Final[bool] = (__import__('os').environ.get("DEBUG_LOG") is not None) or DEBUG_DUMP
"""
`DEBUG_DUMP` implies `DEBUG_LOG`: the dump pipeline rides the per-turn
tree machinery, so dumping with logging off would emit nothing.
"""
HARDCODE: Final[bool] = False
"""Use hardcoding."""
DEBUG_INVARIANTS: Final[bool] = (__import__('os').environ.get("DEBUG_INVARIANTS") is not None)
"""
Run oracle recomputations for incrementally-maintained sets
(`ti_upstream` / `ax_upstream` / `dangling_set` / counters) and assert
equality each turn. Slow — for debugging incremental maintenance only.
"""
