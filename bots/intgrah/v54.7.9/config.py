import os
from typing import Final

DEBUG_RESIGN: Final[bool] = bool(os.getenv("DEBUG_RESIGN"))
"""Resign upon error."""

DEBUG_DUMP: Final[bool] = bool(os.getenv("DEBUG_DUMP"))
"""Dump using rich debugging. This slows down the bot a lot."""

DEBUG_LOG: Final[bool] = bool(os.getenv("DEBUG_LOG")) or DEBUG_DUMP
"""
DEBUG_DUMP implies DEBUG_LOG: the dump pipeline rides the per-turn
tree machinery, so dumping with logging off would emit nothing.
"""

HARDCODE: Final[bool] = False
"""Use hardcoding."""

DEBUG_INVARIANTS: Final[bool] = bool(os.getenv("DEBUG_INVARIANTS"))
"""Run oracle recomputations for incrementally-maintained sets
(ti_upstream / ax_upstream / dangling_set / counters) and assert
equality each turn. Slow — for debugging incremental maintenance only."""
