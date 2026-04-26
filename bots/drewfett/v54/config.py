import os
from typing import Final

DEBUG_DUMP: Final[bool] = bool(os.getenv("DEBUG_DUMP"))
DEBUG_TIMING: Final[bool] = bool(os.getenv("DEBUG_TIMING"))
# DEBUG_DUMP implies DEBUG_LOG: the dump pipeline rides the per-turn
# tree machinery, so dumping with logging off would emit nothing.
DEBUG_LOG: Final[bool] = bool(os.getenv("DEBUG_LOG")) or DEBUG_DUMP
