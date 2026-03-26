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
from .state import Role, State
from .state_dump import dump
from .state_update import update as state_update
from .task_connect_excess_ax_ti_conv import connect_excess_ax_ti_conv
from .task_connect_excess_ti_bridge_core import connect_excess_ti_bridge_core
from .task_connect_excess_ti_rax_core import connect_excess_ti_rax_core
from .task_deny_enemy_harvester import _best_deny_target as _deny_best_target
from .task_deny_enemy_harvester import deny_enemy_harvester
from .task_explore import explore
from .task_harvest_ax import harvest_ax
from .task_harvest_ti import harvest_ti
from .task_heal_core import heal_core
from .task_nav_enemy_core import nav_enemy_core
from .task_patrol import patrol
from .task_place_foundry_mixed_conv import place_foundry_mixed_conv
from .task_place_launcher import place_launcher
from .task_place_splitter_foundry import place_splitter_foundry
from .task_raid import raid
from .task_secure_ore import _best_ore as _secure_best_ore
from .task_secure_ore import _needs_barrier as _secure_needs_barrier
from .task_secure_ore import secure_ore

DEBUG_DUMP = False

type TaskFn = Callable[[State, Controller], tuple[Direction, Action | None] | None]

TASK_FNS: dict[Task, TaskFn] = {
    Task.CONNECT_EXCESS_TI_RAX_CORE: connect_excess_ti_rax_core,
    Task.CONNECT_EXCESS_TI_BRIDGE_CORE: connect_excess_ti_bridge_core,
    Task.HARVEST_TI: harvest_ti,
    Task.HARVEST_AX: harvest_ax,
    Task.EXPLORE: explore,
    Task.PATROL: patrol,
    Task.NAV_ENEMY_CORE: nav_enemy_core,
    Task.RAID: raid,
    Task.PLACE_FOUNDRY_MIXED_CONV: place_foundry_mixed_conv,
    Task.PLACE_SPLITTER_FOUNDRY: place_splitter_foundry,
    Task.CONNECT_EXCESS_AX_TI_CONV: connect_excess_ax_ti_conv,
    Task.HEAL_CORE: heal_core,
    Task.SECURE_ORE: secure_ore,
    Task.PLACE_LAUNCHER: place_launcher,
    Task.DENY_ENEMY_HARVESTER: deny_enemy_harvester,
}


class Builder(Entity):
    def __init__(self, ct: Controller) -> None:
        core_pos = _find_core(ct)
        self.state = State(ct, (core_pos.x, core_pos.y))
        rnd = ct.get_current_round()
        if rnd <= 1:
            self.state.role = Role.ADVANCE
        elif rnd == 2:
            self.state.role = Role.SECURE
        else:
            self.state.role = Role.ADVANCE

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


_NEIGHBOR_DELTAS = [
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
]


def _has_undefended_bridge(state: State) -> bool:
    w = state.w
    for bi in state.my_transport:
        ent = state.entity[bi]
        if ent is None or ent[0] != EntityType.BRIDGE:
            continue
        if any(
            state.in_bounds((bi % w) + dx, (bi // w) + dy)
            and state.entity[ni := state.idx((bi % w) + dx, (bi // w) + dy)] is not None
            and state.entity[ni][0] == EntityType.LAUNCHER
            and state.entity[ni][1] == state.my_team
            for dx, dy in _NEIGHBOR_DELTAS
        ):
            continue
        return True
    return False


def _policy(state: State) -> list[tuple[float, Task]]:
    scores: list[tuple[float, Task]] = []
    pos = state.pos

    core_damaged = state.my_core_hp < state.my_core_max_hp
    scores.append((999.0 if core_damaged else 0.0, Task.HEAL_CORE))

    if state.role == Role.SECURE:
        return _policy_secure(state, scores, pos)
    return _policy_advance(state, scores, pos)


def _policy_secure(
    state: State,
    scores: list[tuple[float, Task]],
    pos: Position,
) -> list[tuple[float, Task]]:
    has_excess = any(
        state.my_flow.excess[i] > 0.01 for i in state.my_harvesters | state.my_transport
    )
    scores.append(
        (200.0 if has_excess else 0.0, Task.CONNECT_EXCESS_TI_BRIDGE_CORE),
    )

    visible_ore = _secure_best_ore(state, pos)
    if visible_ore is not None:
        ox, oy = visible_ore
        needs = _secure_needs_barrier(state, ox, oy)
        oi = state.idx(ox, oy)
        harvester_placed = (
            state.entity[oi] is not None
            and state.entity[oi][0] == EntityType.HARVESTER
            and state.entity[oi][1] == state.my_team
        )
        mid_sequence = len(needs) < 3 and not harvester_placed
        if mid_sequence:
            scores.append((500.0, Task.SECURE_ORE))
        else:
            cx, cy = state.my_core
            core_dist = abs(cx - ox) + abs(cy - oy)
            scores.append((max(60.0, 120.0 - core_dist), Task.SECURE_ORE))
    else:
        scores.append((0.0, Task.SECURE_ORE))

    scores.append(
        (45.0 if _has_undefended_bridge(state) else 0.0, Task.PLACE_LAUNCHER),
    )
    scores.append((20.0, Task.EXPLORE))
    scores.append((5.0, Task.PATROL))

    scores.sort(key=lambda t: t[0], reverse=True)
    return scores


def _policy_advance(
    state: State,
    scores: list[tuple[float, Task]],
    pos: Position,
) -> list[tuple[float, Task]]:
    visible_ore = _secure_best_ore(state, pos)
    has_deny_target = _deny_best_target(state, exclude=visible_ore) is not None
    scores.append((55.0 if has_deny_target else 0.0, Task.DENY_ENEMY_HARVESTER))

    scores.append((20.0, Task.EXPLORE))
    scores.append((5.0, Task.PATROL))

    scores.sort(key=lambda t: t[0], reverse=True)
    return scores
