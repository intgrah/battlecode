from cambc import (
    Controller,
    Direction,
    EntityType,
    Environment,
    GameConstants,
    Position,
)
from map_belief import MapBelief
from marker import Eureka, TaskClaim
from nav_dstar import NavDStar

from .build import Build, BuildKind
from .explore import ExploreMixin
from .fix_excess import FixExcessMixin
from .harvest import HarvestMixin
from .raid import RaidMixin


class Builder(HarvestMixin, FixExcessMixin, RaidMixin, ExploreMixin):
    def __init__(self, ct: Controller) -> None:
        super().__init__(ct)
        core_pos = self._find_core(ct)
        self.belief = MapBelief(
            self.w,
            self.h,
            self.team,
            (core_pos.x, core_pos.y),
        )
        self._last_claim: TaskClaim | None = None
        self._nav = NavDStar(self.belief)

    def run(self, ct: Controller) -> None:
        changed, needs_reflow = self.belief.update(ct)
        if needs_reflow:
            self._flow_search = None
            self._cached_chain_path = None
        for cx, cy in changed:
            self._nav.on_tile_changed(cx, cy)
        print(f"update: {ct.get_cpu_time_elapsed()}us")

        pos = ct.get_position()
        self._debug_target = None
        self._claim: TaskClaim | None = None

        move, build = self._policy(ct, pos)

        if move != Direction.CENTRE:
            if ct.can_move(move):
                ct.move(move)
            elif build is not None and build.kind == BuildKind.ROAD:
                build.execute(ct)
                if ct.can_move(move):
                    ct.move(move)
                build = None
        if build is not None:
            build.execute(ct)

        if self._debug_target is not None:
            target, r, g, b = self._debug_target
            ct.draw_indicator_line(ct.get_position(), target, r, g, b)
        self._write_marker(ct)

    def _policy(self, ct: Controller, pos: Position) -> tuple[Direction, Build | None]:
        result = self._place_harvester(ct, pos)
        if result[1] is not None:
            return result

        result = self._fix_excess(ct, pos)
        if result is not None:
            return result

        result = self._raid(ct, pos)
        if result is not None:
            return result

        result = self._nav_ore(ct, pos)
        if result is not None:
            return result

        result = self._explore(ct, pos)
        if result is not None:
            return result

        return Direction.CENTRE, None

    def _write_marker(self, ct: Controller) -> None:
        marker_val = None
        if self._claim is not None:
            self._last_claim = self._claim
            marker_val = self._claim.encode()
        elif self.belief.symmetry is not None:
            marker_val = Eureka(self.belief.symmetry.value).encode()
        if marker_val is None:
            return
        pos = ct.get_position()
        for t in ct.get_nearby_tiles(GameConstants.ACTION_RADIUS_SQ):
            if t == pos:
                continue
            env = ct.get_tile_env(t)
            if env in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
                continue
            if ct.can_place_marker(t):
                ct.place_marker(t, marker_val)
                return
        for t in ct.get_nearby_tiles(GameConstants.ACTION_RADIUS_SQ):
            if t == pos:
                continue
            bid = ct.get_tile_building_id(t)
            if bid is not None and ct.get_entity_type(bid) == EntityType.MARKER:
                ct.destroy(t)
                ct.place_marker(t, marker_val)
                return

    def _find_core(self, ct: Controller) -> Position:
        my = ct.get_team()
        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) == my and ct.get_entity_type(bid) == EntityType.CORE:
                return ct.get_position(bid)
        raise RuntimeError
