import os
from typing import Final

DEBUG_DUMP: Final[bool] = bool(os.environ.get("DEBUG", ""))
USE_HARDCODED_MAPS: Final[bool] = False

print(f"DEBUG={DEBUG_DUMP}")
