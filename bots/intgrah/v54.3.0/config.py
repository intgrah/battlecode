import os
from typing import Final

DEBUG_DUMP: Final[bool] = bool(os.getenv("DEBUG_DUMP"))
DEBUG_TIMING: Final[bool] = bool(os.getenv("DEBUG_TIMING"))
