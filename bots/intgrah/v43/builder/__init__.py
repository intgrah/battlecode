from collections.abc import Callable

from cambc import (
    Controller,
    Direction,
    EntityType,
    Environment,
    GameConstants,
    Position,
)
from entity import Entity
from marker import Eureka

from .build import Action, PlaceRoad, Task, execute
from .state import State
from .state_dump import dump
from .state_update import update as state_update
from .task_connect_excess_ax_ti_conv import connect_excess_ax_ti_conv
from .task_connect_excess_ti_rax_core import connect_excess_ti_rax_core
from .task_explore import explore
from .task_harvest_ax import harvest_ax
from .task_harvest_ti import harvest_ti
from .task_nav_enemy_core import nav_enemy_core
from .task_patrol import patrol
from .task_place_foundry_mixed_conv import place_foundry_mixed_conv
from .task_place_splitter_foundry import place_splitter_foundry
from .task_raid import raid

DEBUG_DUMP = False

type TaskFn = Callable[[State, Controller], tuple[Direction, Action | None] | None]

TASK_FNS: dict[Task, TaskFn] = {
    Task.CONNECT_EXCESS_TI_RAX_CORE: connect_excess_ti_rax_core,
    Task.HARVEST_TI: harvest_ti,
    Task.HARVEST_AX: harvest_ax,
    Task.EXPLORE: explore,
    Task.PATROL: patrol,
    Task.NAV_ENEMY_CORE: nav_enemy_core,
    Task.RAID: raid,
    Task.PLACE_FOUNDRY_MIXED_CONV: place_foundry_mixed_conv,
    Task.PLACE_SPLITTER_FOUNDRY: place_splitter_foundry,
    Task.CONNECT_EXCESS_AX_TI_CONV: connect_excess_ax_ti_conv,
}


class Builder(Entity):
    def __init__(self, ct: Controller) -> None:
        core_pos = _find_core(ct)
        self.state = State(ct, (core_pos.x, core_pos.y))

    def run(self, ct: Controller) -> None:
        s = self.state
        state_update(s, ct)

        if DEBUG_DUMP:
            dump(s, ct)
        s.debug_target = None
        s.claim = None

        move, build = self._run_policy(ct)

        if move != Direction.CENTRE:
            if ct.can_move(move):
                ct.move(move)
            elif isinstance(build, PlaceRoad):
                execute(build, ct)
                if ct.can_move(move):
                    ct.move(move)
                build = None
        if build is not None:
            execute(build, ct)

        if s.debug_target is not None:
            ct.draw_indicator_line(ct.get_position(), *s.debug_target)
        self._write_marker(ct)

    def _run_policy(self, ct: Controller) -> tuple[Direction, Action | None]:
        s = self.state
        for _, task in _policy(s):
            fn = TASK_FNS[task]
            result = fn(s, ct)
            if result is not None:
                return result
        return Direction.CENTRE, None

    def _write_marker(self, ct: Controller) -> None:
        s = self.state
        marker_val = None
        if s.claim is not None:
            s.last_claim = s.claim
            marker_val = s.claim.encode()
        elif s.symmetry is not None:
            marker_val = Eureka(s.symmetry.value).encode()
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
            if (
                bid is not None
                and ct.get_entity_type(bid) == EntityType.MARKER
                and ct.get_team(bid) == ct.get_team()
            ):
                ct.destroy(t)
                ct.place_marker(t, marker_val)
                return


def _find_core(ct: Controller) -> Position:
    my = ct.get_team()
    for bid in ct.get_nearby_buildings():
        if ct.get_team(bid) == my and ct.get_entity_type(bid) == EntityType.CORE:
            return ct.get_position(bid)
    raise RuntimeError


def _policy(state: State) -> list[tuple[float, Task]]:
    """Score each task. Higher = more priority."""
    scores: list[tuple[float, Task]] = []
    pos = state.pos

    has_excess = any(
        state.my_flow.excess[i] > 0.01 for i in state.my_harvesters | state.my_transport
    )
    scores.append((100.0 if has_excess else 0.0, Task.CONNECT_EXCESS_TI_RAX_CORE))

    unharvested_ti = state.ore_ti - state.my_harvested - state.en_harvested
    if unharvested_ti:
        nearest_ti_dist = min(
            abs(pos.x - ox) + abs(pos.y - oy) for ox, oy in unharvested_ti
        )
        scores.append((max(1.0, 50.0 - nearest_ti_dist), Task.HARVEST_TI))
    else:
        scores.append((0.0, Task.HARVEST_TI))

    unharvested_ax = state.ore_ax - state.my_harvested - state.en_harvested
    if unharvested_ax:
        nearest_ax_dist = min(
            abs(pos.x - ox) + abs(pos.y - oy) for ox, oy in unharvested_ax
        )
        scores.append((max(1.0, 50.0 - nearest_ax_dist), Task.HARVEST_AX))
    else:
        scores.append((0.0, Task.HARVEST_AX))

    has_mixed_conv = any(
        state.my_flow.ti[i] > 0
        and state.my_flow.ax[i] > 0
        and state.entity[i] is not None
        and state.entity[i][0] in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR)
        for i in state.my_transport
    )
    scores.append((90.0 if has_mixed_conv else 0.0, Task.PLACE_FOUNDRY_MIXED_CONV))

    has_foundry_no_splitter = bool(state.my_foundries) and any(
        state.entity[ni] is not None
        and state.entity[ni][0] in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR)
        and state.entity[ni][1] == state.my_team
        for fi in state.my_foundries
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]
        if state.in_bounds(
            (
                ni := state.idx(
                    (fi % state.w) + dx,
                    (fi // state.w) + dy,
                )
            )
            % state.w,
            ni // state.w,
        )
    )
    scores.append(
        (85.0 if has_foundry_no_splitter else 0.0, Task.PLACE_SPLITTER_FOUNDRY),
    )

    scores.append((0.0, Task.CONNECT_EXCESS_AX_TI_CONV))
    scores.append((20.0, Task.EXPLORE))
    scores.append((5.0, Task.PATROL))
    scores.append((0.0, Task.NAV_ENEMY_CORE))
    scores.append((0.0, Task.RAID))

    scores.sort(key=lambda t: t[0], reverse=True)
    return scores
