import sys
from pathlib import Path

# Ensure proto package is importable (project root contains proto/).
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
