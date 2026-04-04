"""Builder bot logic — BFS pathfind to random targets."""

from __future__ import annotations

import random

from bfs import INF, NavBfs
from cambc import Controller, Direction, EntityType, Environment, Position
from explore import ExploreGrid
from grid import PassableGrid
from symmetry import Symmetry, SymmetryDetector
from unit import Unit

# Direction order matching grid.offsets: NE, SE, SW, NW, N, E, S, W
_DIRECTIONS: tuple[Direction, ...] = (
    Direction.NORTHEAST,
    Direction.SOUTHEAST,
    Direction.SOUTHWEST,
    Direction.NORTHWEST,
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
)

_ENV_INT: dict[Environment, int] = {e: i for i, e in enumerate(Environment)}
_ET_INT: dict[EntityType, int] = {e: i + 1 for i, e in enumerate(EntityType)}


def _encode_tile(
    env: Environment, building_type: EntityType | None, is_allied: bool
) -> int:
    """Encode tile state as a byte: env (2 bits) | building (4 bits) | allied (1 bit)."""
    bt = _ET_INT[building_type] if building_type is not None else 0
    return _ENV_INT[env] | (bt << 2) | (int(is_allied) << 6)


def _update_nearby_tiles(
    grid: PassableGrid,
    sym: Symmetry,
    ct: Controller,
    tile_cache: bytearray,
) -> None:
    """Read nearby tiles from the controller and feed raw data to grid."""
    w = grid.w
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
        grid.update_tile(i, env, building_type, is_allied, sym)


class Builder(Unit):
    def __init__(self, ct: Controller) -> None:
        w = ct.get_map_width()
        h = ct.get_map_height()
        self.grid = PassableGrid(w, h)
        nav = NavBfs(self.grid)
        self.explore = ExploreGrid(w, h)
        self.grid.navs.append(nav)
        self.sym: SymmetryDetector | None = None
        self.core_pos: Position | None = None
        self.target: Position | None = None
        self.w = w
        self.h = h
        self._tile_cache: bytearray = bytearray(b"\xff" * (w * h))
        self._mirrored = False
        random.seed(1)

    def _move(
        self,
        ct: Controller,
        pos: Position,
        weights: tuple[int, ...],
    ) -> bool:
        """Move toward the lowest-weight neighbor. Builds a road if needed.

        Among equally weighted directions, prefer ones where we can move
        without building a road first.
        """
        # Group direction indices by weight
        groups: dict[int, list[int]] = {}
        for i in range(8):
            w = weights[i]
            if w < INF:
                groups.setdefault(w, []).append(i)

        for w in sorted(groups):
            indices = groups[w]
            # First pass: try moving without building
            for i in indices:
                if ct.can_move(_DIRECTIONS[i]):
                    ct.move(_DIRECTIONS[i])
                    return True
            # Second pass: build road then move
            for i in indices:
                d = _DIRECTIONS[i]
                next_pos = pos.add(d)
                if ct.can_build_road(next_pos):
                    ct.build_road(next_pos)
                if ct.can_move(d):
                    ct.move(d)
                    return True
        return False

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

        # Once symmetry is resolved, mirror all known tiles to the grid
        if not self._mirrored and self.sym.resolved is not Symmetry.UNKNOWN:
            self.grid.mirror_known(self.sym.resolved, self.sym.known_env)
            for nav in self.grid.navs:
                nav.mark_dirty()
            self._mirrored = True

        # Pick a new random target when needed
        self.explore.update(ct)
        self.target = self.explore.select_next_target(pos, self.core_pos)
        if self.target is None:
            return

        self.grid.navs[0].set_goal(self.target)

        resolved = self.sym.resolved if self.sym is not None else Symmetry.UNKNOWN
        t0 = ct.get_cpu_time_elapsed()
        _update_nearby_tiles(self.grid, resolved, ct, self._tile_cache)
        t1 = ct.get_cpu_time_elapsed()
        weights = self.grid.navs[0].step(pos)
        t2 = ct.get_cpu_time_elapsed()
        self._move(ct, pos, weights)

        print(f"sym={resolved.name} enemy={self.sym.enemy_core}")
        print(f"update={t1 - t0}us step={t2 - t1}us total={t2 - t0}us")

        ct.draw_indicator_line(ct.get_position(), self.target, 0, 128, 0)
        self.grid.navs[0].emit_vis()
        self.explore.draw_unvisited(ct)
