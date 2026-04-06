"""Builder bot logic — BFS pathfind to random targets."""

from __future__ import annotations

import random

from bfs import NavBfs
from cambc import Controller, EntityType, Environment, Position
from symmetry import Symmetry, SymmetryDetector
from unit import Unit

_ENV_INT: dict[Environment, int] = {e: i for i, e in enumerate(Environment)}
_ET_INT: dict[EntityType, int] = {e: i + 1 for i, e in enumerate(EntityType)}


def _encode_tile(
    env: Environment, building_type: EntityType | None, is_allied: bool
) -> int:
    """Encode tile state as a byte: env (2 bits) | building (4 bits) | allied (1 bit)."""
    bt = _ET_INT[building_type] if building_type is not None else 0
    return _ENV_INT[env] | (bt << 2) | (int(is_allied) << 6)


def _update_nearby_tiles(
    nav: NavBfs,
    sym: Symmetry,
    ct: Controller,
    tile_cache: list[int],
) -> None:
    """Read nearby tiles from the controller and feed raw data to nav."""
    w = nav.w
    my_team = ct.get_team()
    for tile in ct.get_nearby_tiles():
        i = tile.y * w + tile.x
        env = ct.get_tile_env(tile)
        bid = ct.get_tile_building_id(tile)
        building_type = ct.get_entity_type(bid) if bid is not None else None
        is_allied = bid is not None and ct.get_team(bid) == my_team
        key = _encode_tile(env, building_type, is_allied)
        if tile_cache[i] == key:
            continue
        tile_cache[i] = key
        nav.update_tile(i, env, building_type, is_allied, sym)


class Builder(Unit):
    def __init__(self, ct: Controller) -> None:
        w = ct.get_map_width()
        h = ct.get_map_height()
        self.nav = NavBfs(w, h)
        self.sym: SymmetryDetector | None = None
        self.core_pos: Position | None = None
        self.target: Position | None = None
        self.w = w
        self.h = h
        self._tile_cache: list[int] = [0xFF] * (w * h)
        self._mirrored = False
        random.seed(1)

    def run(self, ct: Controller) -> None:
        pos = ct.get_position()

        # Initialize symmetry detector once we know our core position
        if self.core_pos is None:
            my_team = ct.get_team()
            for tile in ct.get_nearby_tiles():
                bid = ct.get_tile_building_id(tile)
                if (
                    bid is not None
                    and ct.get_entity_type(bid) == EntityType.CORE
                    and ct.get_team(bid) == my_team
                ):
                    self.core_pos = tile
                    self.sym = SymmetryDetector(self.w, self.h, tile)
                    break
            assert self.core_pos is not None

        # Run symmetry detection
        if self.sym.resolved is Symmetry.UNKNOWN:
            for tile in ct.get_nearby_tiles():
                self.sym.update(tile.y * self.w + tile.x, tile, ct.get_tile_env(tile))

        # Once symmetry is resolved, mirror all known tiles to the BFS grid
        if not self._mirrored and self.sym.resolved is not Symmetry.UNKNOWN:
            self.nav.mirror_known(self.sym.resolved, self.sym.known_env)
            self._mirrored = True

        # Pick a new random target when needed
        if self.target is None or pos == self.target:
            self.target = Position(
                random.randint(0, self.w - 1),
                random.randint(0, self.h - 1),
            )
        # Re-pick if target is impassable
        if not self.nav.get_passable(self.target):
            self.target = Position(
                random.randint(0, self.w - 1),
                random.randint(0, self.h - 1),
            )

        self.nav.set_goal(self.target)

        resolved = self.sym.resolved if self.sym is not None else Symmetry.UNKNOWN
        t0 = ct.get_cpu_time_elapsed()
        _update_nearby_tiles(self.nav, resolved, ct, self._tile_cache)
        t1 = ct.get_cpu_time_elapsed()
        self.nav.step(ct)
        t2 = ct.get_cpu_time_elapsed()

        print(f"sym={resolved.name} enemy={self.sym.enemy_core}")
        print(f"update={t1 - t0}us step={t2 - t1}us total={t2 - t0}us")

        ct.draw_indicator_line(ct.get_position(), self.target, 0, 128, 0)
        #self.nav.emit_vis()
