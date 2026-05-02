"""Render dp_step.py from the local Jinja template.

Run via `uv run --with jinja2 python bots/intgrah/v54.7.9/templates/dp_step_gen.py`.
After rendering, runs `ruff format` so output matches the canonical
formatting the rest of the codebase uses.
"""

import shutil
import subprocess
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

HERE = Path(__file__).parent
BOT_ROOT = HERE.parent
OUT = BOT_ROOT / "builder" / "algorithms" / "dp_step.py"


def add_const(var: str, k: int) -> str:
    if k == 0:
        return var
    if k > 0:
        return f"{var} + {k}"
    return f"{var} - {-k}"


def cell_offset(dx: int, dy: int) -> str:
    out = "pos"
    if dy == 1:
        out += " + w"
    elif dy == -1:
        out += " - w"
    elif dy == 2:
        out += " + w2"
    elif dy == -2:
        out += " - w2"
    elif dy == 3:
        out += " + w3"
    elif dy == -3:
        out += " - w3"
    elif dy == 4:
        out += " + w4"
    elif dy == -4:
        out += " - w4"
    elif dy > 0:
        out += f" + {dy} * w"
    elif dy < 0:
        out += f" - {-dy} * w"
    if dx > 0:
        out += f" + {dx}"
    elif dx < 0:
        out += f" - {-dx}"
    return out


def main() -> None:
    env = Environment(
        loader=FileSystemLoader(HERE),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    env.globals["add_const"] = add_const
    env.globals["cell_offset"] = cell_offset
    rendered = env.get_template("dp_step.py.j2").render()
    OUT.write_text(rendered)
    print(f"generated {OUT}")

    ruff = shutil.which("ruff")
    if ruff is not None:
        subprocess.run([ruff, "format", "--quiet", str(OUT)], check=True)
        print("formatted")
    else:
        print("ruff not found; skipping format")


if __name__ == "__main__":
    main()
