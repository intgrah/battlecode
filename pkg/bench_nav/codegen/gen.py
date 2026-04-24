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
)


def main() -> None:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
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
