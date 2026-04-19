import os
from typing import Final

DEBUG_RESIGN: Final[bool] = bool(os.getenv("DEBUG_RESIGN"))
DEBUG_DUMP: Final[bool] = bool(os.getenv("DEBUG_DUMP"))
DEBUG_TIMING: Final[bool] = bool(os.getenv("DEBUG_TIMING"))
HARDCODE: Final[bool] = False
