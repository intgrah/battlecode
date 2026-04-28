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
