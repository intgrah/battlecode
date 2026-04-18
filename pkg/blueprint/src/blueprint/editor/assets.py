"""Sprite asset loader. PNGs vendored under `_assets/`.

The conveyor and armoured-conveyor base sprites face west; we rotate
them in-memory to produce N/E/S variants instead of shipping four
variants per team (matches the Rust viewer's approach).

Team colours:
    gold   = team A (P1, the half we edit)
    silver = team B (P2, mirrored half)
"""

from __future__ import annotations

from pathlib import Path

import pygame

from blueprint import Direction, Entity

__all__ = [
    "BG_COLOUR",
    "EMPTY_COLOUR",
    "WALL_TINT",
    "Assets",
    "load_assets",
]

ASSETS_DIR = Path(__file__).resolve().parent / "_assets"

# Matches the Rust viewer (map.rs:10-11).
BG_COLOUR = (0x1D, 0x15, 0x0F)
EMPTY_COLOUR = (0x2A, 0x20, 0x18)
WALL_TINT = (0x30, 0x0C, 0x08)

_DIR_SUFFIX: dict[Direction, str] = {
    Direction.NORTH: "n",
    Direction.NORTHEAST: "ne",
    Direction.EAST: "e",
    Direction.SOUTHEAST: "se",
    Direction.SOUTH: "s",
    Direction.SOUTHWEST: "sw",
    Direction.WEST: "w",
    Direction.NORTHWEST: "nw",
}

# Rotation (counter-clockwise degrees, pygame convention) to apply to a
# west-facing base sprite to produce each cardinal direction.
_CCW_FROM_WEST: dict[Direction, int] = {
    Direction.WEST: 0,
    Direction.SOUTH: 90,
    Direction.EAST: 180,
    Direction.NORTH: 270,
}


class Assets:
    """Sprite cache. Base PNGs loaded once; rotations / tints are
    memoised per (name, key)."""

    __slots__ = ("_base", "_cache", "_tile_px")

    def __init__(self, tile_px: int) -> None:
        self._tile_px = tile_px
        self._base: dict[str, pygame.Surface] = {}
        self._cache: dict[str, pygame.Surface] = {}

    def _raw(self, filename: str) -> pygame.Surface | None:
        if filename in self._base:
            return self._base[filename]
        path = ASSETS_DIR / filename
        if not path.exists():
            return None
        img = pygame.image.load(str(path)).convert_alpha()
        self._base[filename] = img
        return img

    def _scaled(self, filename: str, size: int | None = None) -> pygame.Surface | None:
        px = size or self._tile_px
        key = f"{filename}@{px}"
        if key in self._cache:
            return self._cache[key]
        raw = self._raw(filename)
        if raw is None:
            return None
        scaled = pygame.transform.smoothscale(raw, (px, px))
        self._cache[key] = scaled
        return scaled

    def _rotated(self, filename: str, ccw_deg: int) -> pygame.Surface | None:
        key = f"{filename}@{self._tile_px}@{ccw_deg}"
        if key in self._cache:
            return self._cache[key]
        raw = self._raw(filename)
        if raw is None:
            return None
        rotated = pygame.transform.rotate(raw, ccw_deg)
        scaled = pygame.transform.smoothscale(
            rotated,
            (self._tile_px, self._tile_px),
        )
        self._cache[key] = scaled
        return scaled

    def wall(self) -> pygame.Surface | None:
        """Natural wall sprite multiplied by WALL_TINT (matches Rust viewer)."""
        key = f"wall@{self._tile_px}"
        if key in self._cache:
            return self._cache[key]
        raw = self._raw("natural_wall.jpg")
        if raw is None:
            return None
        scaled = pygame.transform.smoothscale(
            raw,
            (self._tile_px, self._tile_px),
        ).copy()
        tint = pygame.Surface(scaled.get_size())
        tint.fill(WALL_TINT)
        scaled.blit(tint, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        self._cache[key] = scaled
        return scaled

    def ore(self, *, axionite: bool) -> pygame.Surface | None:
        return self._scaled("axionite_ore.png" if axionite else "titanium_ore.png")

    def core(self, *, team_a: bool, size: int) -> pygame.Surface | None:
        return self._scaled(
            "base_gold.png" if team_a else "base_silver.png",
            size=size,
        )

    def entity(
        self,
        kind: Entity,
        direction: Direction | None,
        *,
        team_a: bool,
    ) -> pygame.Surface | None:
        suffix = "gold" if team_a else "silver"
        match kind:
            case Entity.HARVESTER:
                return self._scaled(f"harvester_{suffix}.png")
            case Entity.FOUNDRY:
                return self._scaled(f"foundry_{suffix}.png")
            case Entity.LAUNCHER:
                return self._scaled(f"launcher_{suffix}.png")
            case Entity.ROAD:
                return self._scaled(f"road_{suffix}.png")
            case Entity.BARRIER:
                return self._scaled(f"barrier_{suffix}.png")
            case Entity.BRIDGE:
                return self._scaled(f"bridge_stand_{suffix}.png")
            case Entity.SPLITTER:
                d = _DIR_SUFFIX.get(direction or Direction.NORTH, "n")
                return self._scaled(f"splitter_{d}_{suffix}.png")
            case Entity.CONVEYOR:
                ccw = _CCW_FROM_WEST.get(direction or Direction.WEST, 0)
                return self._rotated(f"conveyor_{suffix}.png", ccw)
            case Entity.ARMOURED_CONVEYOR:
                ccw = _CCW_FROM_WEST.get(direction or Direction.WEST, 0)
                return self._rotated(f"armoured_conveyor_{suffix}.png", ccw)
            case Entity.GUNNER:
                d = _DIR_SUFFIX.get(direction or Direction.NORTH, "n")
                return self._scaled(f"gunner_{d}_{suffix}.png")
            case Entity.SENTINEL:
                d = _DIR_SUFFIX.get(direction or Direction.NORTH, "n")
                return self._scaled(f"sentinel_{d}_{suffix}.png")
            case Entity.BREACH:
                d = _DIR_SUFFIX.get(direction or Direction.NORTH, "n")
                return self._scaled(f"breach_{d}_{suffix}.png")
            case _:
                return None


def load_assets(tile_px: int) -> Assets:
    return Assets(tile_px)
