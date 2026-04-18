from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

from blueprint import DIRECTIONAL, BlueprintEntry, Entity

if TYPE_CHECKING:
    from blueprint.editor.sequencing import Scored

__all__ = ["BLUEPRINTS_DIR", "load_blueprint", "write_blueprint"]

BLUEPRINTS_DIR = Path(__file__).resolve().parents[3] / "blueprints"
"""`pkg/blueprint/blueprints/`. Bots vendor this directory via a
symlink at `<bot>/hardcode/blueprints`."""


def _render_entry(entry: BlueprintEntry) -> str:
    parts = [
        f"({entry.pos[0]}, {entry.pos[1]})",
        f"Entity.{entry.kind.name}",
    ]
    if entry.kind in DIRECTIONAL and entry.direction is not None:
        parts.append(f"direction=Direction.{entry.direction.name}")
    if entry.kind == Entity.BRIDGE and entry.bridge_target is not None:
        bx, by = entry.bridge_target
        parts.append(f"bridge_target=({bx}, {by})")
    return f"    BlueprintEntry({', '.join(parts)}),"


def load_blueprint(map_name: str) -> tuple[BlueprintEntry, ...] | None:
    """Load a previously saved blueprint by map name.

    Returns None if no blueprint exists for this map. Otherwise imports
    the module and returns its BLUEPRINT tuple. Import is by path so we
    don't depend on the bot's `hardcode` import path being set up.
    """
    path = BLUEPRINTS_DIR / f"{map_name}.py"
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(
        f"blueprint._loaded_{map_name}",
        path,
    )
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    entries = getattr(module, "BLUEPRINT", None)
    if not isinstance(entries, tuple):
        return None
    return entries


def write_blueprint(map_name: str, scored: list[Scored]) -> Path:
    BLUEPRINTS_DIR.mkdir(parents=True, exist_ok=True)
    out = BLUEPRINTS_DIR / f"{map_name}.py"
    lines = [
        "from blueprint import BlueprintEntry, Direction, Entity",
        "",
        "BLUEPRINT: tuple[BlueprintEntry, ...] = (",
    ]
    lines.extend(_render_entry(s.entry) for s in scored)
    lines.append(")")
    out.write_text("\n".join(lines) + "\n")
    _update_index()
    return out


def _update_index() -> None:
    """Regenerate blueprints/__init__.py to expose every per-map file."""
    files = sorted(
        p.stem for p in BLUEPRINTS_DIR.glob("*.py") if p.stem != "__init__"
    )
    idx = BLUEPRINTS_DIR / "__init__.py"
    lines = [
        "from __future__ import annotations",
        "",
        "from blueprint import BlueprintEntry",
    ]
    if files:
        lines.append("")
        lines.extend(
            f"from hardcode.blueprints import {name} as _{name}" for name in files
        )
    lines += [
        "",
        '__all__ = ["BLUEPRINTS", "BlueprintEntry"]',
        "",
        "BLUEPRINTS: dict[str, tuple[BlueprintEntry, ...]] = {",
    ]
    lines.extend(f'    "{name}": _{name}.BLUEPRINT,' for name in files)
    lines.append("}")
    idx.write_text("\n".join(lines) + "\n")
