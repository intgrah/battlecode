"""Generate astar_jps*.py from Jinja templates.

Run via `uv run --with jinja2 python pkg/bench_nav/codegen/gen.py`
or `just gen` (see justfile). After rendering each file, runs
`ruff format` on it so regenerated output matches the canonical
formatting the rest of the codebase uses.
"""

import shutil
import subprocess
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

HERE = Path(__file__).parent
TEMPLATES = HERE / "templates"
SRC_ROOT = HERE.parent / "src" / "bench_nav"

TARGETS: tuple[tuple[str, str, str], ...] = (
    ("astar_jps.py.j2", "spsp/astar", "jps.py"),
    ("astar_jps_dial.py.j2", "spsp/astar", "jps_dial.py"),
    ("astar_jps_precomp.py.j2", "spsp/astar", "jps_precomp.py"),
    ("astar_jps_mpsp.py.j2", "mpsp", "astar_jps_mpsp.py"),
    ("astar_jps_stepped.py.j2", "stepped", "jps.py"),
    ("dp_step.py.j2", "stepped", "dp_step.py"),
)


def add_const(var: str, k: int) -> str:
    """`var + k` simplified: drop +0, write +(-k) as -k."""
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
        loader=FileSystemLoader(TEMPLATES),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    env.globals["add_const"] = add_const
    env.globals["cell_offset"] = cell_offset
    outs: list[Path] = []
    for template_name, subdir, out_name in TARGETS:
        tmpl = env.get_template(template_name)
        rendered = tmpl.render()
        out = SRC_ROOT / subdir / out_name
        out.write_text(rendered)
        outs.append(out)
        print(f"generated {out.relative_to(SRC_ROOT.parent.parent)}")

    ruff = shutil.which("ruff")
    if ruff is not None and outs:
        subprocess.run(
            [ruff, "format", "--quiet", *map(str, outs)],
            check=True,
        )
        print(f"formatted {len(outs)} file(s)")
    else:
        print("ruff not found; skipping format")


if __name__ == "__main__":
    main()
