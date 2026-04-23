"""Generate astar_jps.py and astar_jps_dial.py from Jinja templates.

Run via `uv run --with jinja2 python pkg/bench_nav/codegen/gen.py`
or `just gen` (see justfile).
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

HERE = Path(__file__).parent
TEMPLATES = HERE / "templates"
OUT_DIR = HERE.parent / "src" / "bench_nav" / "spsp"

TARGETS = [
    ("astar_jps.py.j2", "astar_jps.py"),
    ("astar_jps_dial.py.j2", "astar_jps_dial.py"),
]


def main() -> None:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    for template_name, out_name in TARGETS:
        tmpl = env.get_template(template_name)
        rendered = tmpl.render()
        out = OUT_DIR / out_name
        out.write_text(rendered)
        print(f"generated {out.relative_to(OUT_DIR.parent.parent.parent)}")


if __name__ == "__main__":
    main()
