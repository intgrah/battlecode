"""Builder bot logic — explore until ore is found, then pathfind to ore."""

from __future__ import annotations

from astar import BuildInstruction, ChainAstar
from bfs import NavBfs
from cambc import Controller, Direction, EntityType, Environment, Position
from explore import ExploreGrid
from symmetry import Symmetry, SymmetryDetector
from tile_codec import UNSEEN, _ET_INT, encode_tile, tile_building_type, tile_is_allied
from env_tracker import EnvTracker
from unit import Unit
from utils import try_move_away

_BUILDABLE = frozenset((EntityType.ROAD, EntityType.MARKER, None))

def _update_nearby_tiles(
    nav: NavBfs,
    sym: Symmetry,
    ct: Controller,
    tile_cache: list[int],
    env_trackers: list[EnvTracker],
    chain: ChainAstar,
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
        key = encode_tile(env, building_type, is_allied)
        if tile_cache[i] == key:
            continue
        tile_cache[i] = key
        nav.update_tile(i, env, building_type, is_allied, sym)
        for tracker in env_trackers:
            tracker.update_tile(i, env, building_type, is_allied, sym)
        chain.update_tile(tile.x, tile.y, env, building_type, is_allied)


class Builder(Unit):
    def __init__(self, ct: Controller) -> None:
        w = ct.get_map_width()
        h = ct.get_map_height()
        self.nav = NavBfs(w, h)
        self.sym: SymmetryDetector | None = None
        self.core_pos: Position | None = None
        self.w = w
        self.h = h
        self._tile_cache: list[int] = [0xFF] * (w * h)
        self._mirrored = False
        self.explore = ExploreGrid(w, h)
        self.ti_ore = EnvTracker(w, h, Environment.ORE_TITANIUM, entity_types=_BUILDABLE)
        self.ax_ore = EnvTracker(w, h, Environment.ORE_AXIONITE, entity_types=_BUILDABLE)
        self.env_trackers: list[EnvTracker] = [self.ti_ore, self.ax_ore]
        self.chain = ChainAstar(w, h)
        self._chain_plan: list[BuildInstruction] | None = None
        self._plan_progress: int = 0

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
                    self.sym = SymmetryDetector(self.w, self.h, self.core_pos)
                    break
            assert self.core_pos is not None

        # Run symmetry detection
        if self.sym.resolved is Symmetry.UNKNOWN:
            for tile in ct.get_nearby_tiles():
                self.sym.update(tile.y * self.w + tile.x, tile, ct.get_tile_env(tile))

        # Once symmetry is resolved, mirror all known tiles to the BFS grid
        if not self._mirrored and self.sym.resolved is not Symmetry.UNKNOWN:
            self.nav.mirror_known(self.sym.resolved, self.sym.known_env)
            for tracker in self.env_trackers:
                tracker.mirror_known(self.sym.resolved)
            self._mirrored = True

        resolved = self.sym.resolved

        _update_nearby_tiles(
            self.nav, resolved, ct, self._tile_cache, self.env_trackers, self.chain
        )
        self.explore.update(ct, pos, self.core_pos)

        print(f"sym {resolved.name}")

        new_pos = ct.get_position()

        if self._chain_plan:
            print(self._chain_plan[self._plan_progress:])

        # Plan execution takes precedence over normal navigation. The plan
        # itself sets the nav goal each turn.
        if self.plan_ok(ct) == -1:
            self._execute_plan(ct)
        else:
            has_ore = self.ti_ore.any_positions()
            # No active plan — fall back to ore harvesting / exploring.
            if has_ore and (self.ti_ore.take_changed() or not self.nav._gis):
                self.nav.set_goals(self.ti_ore.as_positions())
            elif not has_ore:
                self.nav.set_goal(self.explore.target)

            if has_ore:
                self._handle_ore(ct)
            else:
                self._handle_explore(ct, new_pos)

        if self._chain_plan is not None:
            self.chain.draw_path(ct, self._chain_plan)
            self.chain.emit_vis()

        self.nav.step(ct)
        self.nav.emit_vis()


    def _handle_ore(self, ct: Controller) -> None:
        """No active plan — generate one for the nearest reachable ore so
        the next turn (or this turn's later draw) can execute it.
        """
        self.ti_ore.draw_tracked(ct, 0, 255, 255)

        nearest_ore = self.nav.nearest_goal(ct)
        if nearest_ore is None:
            return

        ct.draw_indicator_dot(nearest_ore, 0, 255, 0)
        self._chain_plan = self._chain_plan_for(ct, nearest_ore)
        self._plan_progress = 0

    def _execute_plan(self, ct: Controller) -> None:
        """Pathfind to the next instruction's tile and try to place its
        building. On a successful build, advance `_plan_progress`. When
        we run off the end of the plan, clear it.
        """
        entity, pos, extra = self._chain_plan[self._plan_progress]

        if self._try_place(ct, entity, pos, extra):
            self._plan_progress += 1
        
        if self._plan_progress >= len(self._chain_plan):
            self._chain_plan = None
            self._plan_progress = 0
            return
        
        _, pos, _ = self._chain_plan[self._plan_progress]
        self.nav.set_goal(pos)

    def _try_place(
        self,
        ct: Controller,
        entity: EntityType,
        pos: Position,
        extra: object,
    ) -> bool:
        # Clear any road sitting on the target tile first. We only act if
        # we've actually observed the tile (not UNSEEN). Allied roads are
        # destroyed; enemy roads are fired upon.
        
        cached = self._tile_cache[pos.y * self.w + pos.x]
        if cached != UNSEEN and tile_building_type(cached) == EntityType.ROAD:
            if tile_is_allied(cached):
                if ct.can_destroy(pos):
                    ct.destroy(pos)
            else:
                if ct.can_fire(pos):
                    ct.fire(pos)

        if entity == EntityType.HARVESTER:
            if ct.get_position() == pos:
                try_move_away(ct, pos)
            if not ct.can_build_harvester(pos):
                return False
            ct.build_harvester(pos)
            return True
        if entity == EntityType.CONVEYOR:
            if not ct.can_build_conveyor(pos, extra):
                return False
            ct.build_conveyor(pos, extra)
            return True
        if entity == EntityType.BRIDGE:
            if not ct.can_build_bridge(pos, extra):
                return False
            ct.build_bridge(pos, extra)
            return True
        return False

    def _chain_plan_for(
        self, ct: Controller, nearest_ore: Position
    ) -> list[BuildInstruction] | None:
        """Plan a fresh chain from the core area to `nearest_ore`. Prepends
        a harvester instruction at the ore tile if it isn't already
        harvested.
        """
        cx, cy = self.core_pos.x, self.core_pos.y
        self.chain.set_starts(
            (cx + dx, cy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
        )
        # force impassible for pathfinding (as it will be once we place the harvester)
        self.chain.update_tile(nearest_ore.x, nearest_ore.y, Environment.WALL, None, True)
        self.chain.set_goal(nearest_ore.x, nearest_ore.y)
        self.chain.offset_goal()
        plan = self.chain.plan()
        if plan is None:
            return None

        cached = self._tile_cache[nearest_ore.y * self.w + nearest_ore.x]
        if cached == UNSEEN or tile_building_type(cached) != EntityType.HARVESTER:
            plan.insert(0, (EntityType.HARVESTER, nearest_ore, None))
        return plan

    def plan_ok(self, ct: Controller) -> int:
        """Return the index of the first plan entry whose tile is not
        buildable (anything other than empty, marker, or road), or -1 if
        every entry is fine (or there is no plan). Unobserved tiles are
        treated as possible.
        """
        if self._chain_plan is None:
            return 0
        i = 0
        for _entity, pos, _extra in self._chain_plan[self._plan_progress:]:
            cached = self._tile_cache[pos.y * self.w + pos.x]
            if cached == UNSEEN:
                i += 1
                continue
            bt = tile_building_type(cached)
            if bt in _BUILDABLE:
                i += 1
                continue
            return i
        return -1

    def _handle_explore(self, ct: Controller, new_pos: Position) -> None:
        if self.explore.target is not None:
            ct.draw_indicator_line(new_pos, self.explore.target, 0, 128, 0)
            self.explore.draw_unvisited(ct, 255, 0, 0)
