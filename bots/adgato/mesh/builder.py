"""Builder bot logic — BFS pathfind to random targets."""

from __future__ import annotations

import random

from bfs import INF, NavBfs
from cambc import Controller, Direction, EntityType, Environment, Position
from grid import PassableGrid
from symmetry import Symmetry, SymmetryDetector
from tracker import Tracker
from bbot_tracker import BbotTracker
from unit import Unit
from explore import ExploreGrid

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
    trackers: list[Tracker],
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
        for tracker in trackers:
            tracker.update_tile(i, env, building_type, is_allied, sym)

def _combine_weights(*weighted: tuple[tuple[int, ...], int]) -> tuple[int, ...]:
    """Linear combination of weight tuples. INF in any input produces INF."""
    result = [0] * 8
    for weights, scale in weighted:
        for i in range(8):
            result[i] += weights[i] * scale
    return tuple(v if v < INF else INF for v in result)

NV_EXPLORE = 0
NV_TI_ORE = 1
NV_BBOTS = 2
NV_CORE = 3

TK_TI_ORE = 0

class Builder(Unit):
    def __init__(self, ct: Controller) -> None:
        w = ct.get_map_width()
        h = ct.get_map_height()
        self.grid = PassableGrid(w, h)
        self.explore = ExploreGrid(w, h)
        self.sym: SymmetryDetector | None = None
        self.core_pos: Position | None = None
        self.w = w
        self.h = h
        self._mirrored = False
        self._tile_cache: bytearray = bytearray(b"\xff" * (w * h))
        self.grid.navs = [
            NavBfs(self.grid), # NV_EXPLORE = 0
            NavBfs(self.grid, range=20), # NV_TI_ORE = 1
            NavBfs(self.grid, target_dist=5, range=10), # NV_BBOTS = 2
            NavBfs(self.grid, target_dist=5) # NV_CORE = 3
        ]
        self.trackers: list[Tracker] = [
            Tracker(w, h, environment=Environment.ORE_TITANIUM) # TK_TI_ORE = 0
        ]
        self.friend_tracker: BbotTracker = BbotTracker(w, friendly=True)

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
                    self.core_pos = ct.get_position(bid)
                    self.sym = SymmetryDetector(self.w, self.h, tile)
                    break
            self.grid.navs[NV_CORE].change_goal([self.core_pos])

        # Run symmetry detection
        if self.sym.resolved is Symmetry.UNKNOWN:
            for tile in ct.get_nearby_tiles():
                self.sym.update(tile.y * self.w + tile.x, tile, ct.get_tile_env(tile))

        # Once symmetry is resolved, mirror all known tiles to the grid
        if not self._mirrored and self.sym.resolved is not Symmetry.UNKNOWN:
            self.grid.mirror_known(self.sym.resolved, self.sym.known_env)
            for tracker in self.trackers:
                tracker.mirror_known(self.sym.resolved)
            self._mirrored = True

        resolved = self.sym.resolved if self.sym is not None else Symmetry.UNKNOWN
        t0 = ct.get_cpu_time_elapsed()
        _update_nearby_tiles(self.grid, resolved, ct, self._tile_cache, self.trackers)
        self.friend_tracker.update(ct)
        self.explore.update(ct, pos, self.core_pos)
        t1 = ct.get_cpu_time_elapsed()

        # Update goals: ore tracker -> NV_TI_ORE, explore -> NV_EXPLORE
        ti_ore = self.trackers[TK_TI_ORE]
        use_ore = bool(ti_ore.positions)
        if use_ore and ti_ore.take_changed():
            self.grid.navs[NV_TI_ORE].change_goal(ti_ore.as_positions())
        if not use_ore and self.explore.take_changed():
            self.grid.navs[NV_EXPLORE].change_goal([self.explore.target])
        if self.friend_tracker.take_changed():
            self.grid.navs[NV_BBOTS].change_goal(self.friend_tracker.as_positions())

        # Step the preferred nav: ore if available, else explore
        active_nav = NV_TI_ORE if use_ore else NV_EXPLORE

        weights = _combine_weights(
            (self.grid.navs[active_nav].step(pos), 3),
            (self.grid.navs[NV_BBOTS].step(pos), 2),
            (self.grid.navs[NV_CORE].step(pos), 2),
        )

        t2 = ct.get_cpu_time_elapsed()
        print(f"sym={resolved.name} enemy={self.sym.enemy_core}")
        print(f"update={t1 - t0}us step={t2 - t1}us total={t2 - t0}us")
        
        self._move(ct, pos, weights)

        nav = self.grid.navs[active_nav]
        pw = self.grid.pw
        new_pos = ct.get_position()
        for gi in nav._goals:
            ct.draw_indicator_line(new_pos, Position(gi % pw - 1, gi // pw - 1), 0, 128, 0)
        self.grid.navs[NV_CORE].emit_vis()
        if use_ore:
            self.trackers[TK_TI_ORE].draw_tracked(ct, 0, 255, 255)
        else:
            self.explore.draw_unvisited(ct, 255, 0, 0)
        self.friend_tracker.draw_tracked(ct, 0, 0, 128)
