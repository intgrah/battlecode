"""Render each blueprint to a PNG preview.

Outputs to pkg/blueprint/previews/<map>.png.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from blueprint import BlueprintEntry, Entity, mirror_entry, mirror_pos
from blueprint.editor.assets import BG_COLOUR, EMPTY_COLOUR, load_assets
from blueprint.editor.map_io import MapData, Tile, load_map


def _detect_symmetry(m: MapData) -> str:
    w, h = m.w, m.h
    for sym in ("hor", "ver", "rot"):
        if mirror_pos(m.core_a, w, h, sym) != m.core_b:
            continue
        ok = True
        for y in range(h):
            for x in range(w):
                mx, my = mirror_pos((x, y), w, h, sym)
                if m.tile(x, y) != m.tile(mx, my):
                    ok = False
                    break
            if not ok:
                break
        if ok:
            return sym
    msg = f"no symmetry for {m.name}"
    raise ValueError(msg)


_BLUEPRINTS_DIR = Path(__file__).resolve().parents[1] / "pkg" / "blueprint" / "blueprints"


def _load_blueprints() -> dict[str, tuple[BlueprintEntry, ...]]:
    import importlib.util

    out: dict[str, tuple[BlueprintEntry, ...]] = {}
    for p in sorted(_BLUEPRINTS_DIR.glob("*.py")):
        if p.stem == "__init__":
            continue
        spec = importlib.util.spec_from_file_location(f"_bp_{p.stem}", p)
        if spec is None or spec.loader is None:
            continue
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        entries = getattr(mod, "BLUEPRINT", None)
        if isinstance(entries, tuple):
            out[p.stem] = entries
    return out

_ROOT = Path(__file__).resolve().parents[1]
_MAPS_DIR = _ROOT / "maps"
_OUT = _ROOT / "pkg" / "blueprint" / "previews"
_TILE_PX = 24


def _render(map_name: str, entries: tuple[BlueprintEntry, ...]) -> pygame.Surface:
    mdata = load_map(_MAPS_DIR / f"{map_name}.map26")
    assets = load_assets(_TILE_PX)
    sym = _detect_symmetry(mdata)

    surf = pygame.Surface((mdata.w * _TILE_PX, mdata.h * _TILE_PX))
    surf.fill(BG_COLOUR)

    for y in range(mdata.h):
        for x in range(mdata.w):
            rect = pygame.Rect(x * _TILE_PX, y * _TILE_PX, _TILE_PX, _TILE_PX)
            tile = mdata.tile(x, y)
            if tile == Tile.WALL:
                spr = assets.wall()
                if spr is not None:
                    surf.blit(spr, rect.topleft)
            elif tile in (Tile.ORE_TITANIUM, Tile.ORE_AXIONITE):
                pygame.draw.rect(surf, EMPTY_COLOUR, rect)
                spr = assets.ore(axionite=tile == Tile.ORE_AXIONITE)
                if spr is not None:
                    surf.blit(spr, rect.topleft)
            else:
                pygame.draw.rect(surf, EMPTY_COLOUR, rect)

    for core, team_a in ((mdata.core_a, True), (mdata.core_b, False)):
        cx, cy = core
        size = _TILE_PX * 3
        spr = assets.core(team_a=team_a, size=size)
        if spr is not None:
            surf.blit(spr, ((cx - 1) * _TILE_PX, (cy - 1) * _TILE_PX))

    def _draw_entry(e: BlueprintEntry, *, team_a: bool) -> None:
        spr = assets.entity(e.kind, e.direction, team_a=team_a)
        if spr is not None:
            surf.blit(spr, (e.pos[0] * _TILE_PX, e.pos[1] * _TILE_PX))
        if e.kind == Entity.BRIDGE and e.bridge_target is not None:
            ax, ay = e.pos
            bx, by = e.bridge_target
            pygame.draw.line(
                surf,
                (140, 140, 40) if team_a else (120, 120, 160),
                (ax * _TILE_PX + _TILE_PX // 2, ay * _TILE_PX + _TILE_PX // 2),
                (bx * _TILE_PX + _TILE_PX // 2, by * _TILE_PX + _TILE_PX // 2),
                2,
            )

    for e in entries:
        _draw_entry(e, team_a=True)
    for e in entries:
        me = mirror_entry(e, mdata.w, mdata.h, sym)
        _draw_entry(me, team_a=False)

    return surf


def main() -> None:
    pygame.init()
    pygame.display.set_mode((1, 1))
    _OUT.mkdir(parents=True, exist_ok=True)
    bps = _load_blueprints()
    for name in sorted(bps.keys()):
        try:
            surf = _render(name, bps[name])
        except (FileNotFoundError, ValueError, KeyError) as exc:
            print(f"skip {name}: {exc}", file=sys.stderr)
            continue
        out = _OUT / f"{name}.png"
        pygame.image.save(surf, str(out))
        print(out)


if __name__ == "__main__":
    main()
