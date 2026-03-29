from collections.abc import Callable

from building import BuildingBridge, BuildingLauncher
from cambc import (
    Controller,
    Direction,
    EntityType,
    Environment,
    GameConstants,
    Position,
    Team,
)
from hardcode.known import KnownMap
from hardcode.map import SYMMETRY
from hardcode.opening import Opening, get_opening
from hardcode.opening.compiler import (
    CompiledActionMove,
    CompiledMoveAction,
    CompiledTurn,
    dsl_compile,
)
from hardcode.opening.mirror import mirror_opening
from marker import MarkerEureka, MarkerOpeningBook
from marker import decode as decode_marker
from unit import Unit
from util import DIR8_DELTA

from .build import (
    Action,
    PlaceBarrier,
    PlaceBridge,
    PlaceConveyor,
    PlaceFoundry,
    PlaceGunner,
    PlaceHarvester,
    PlaceLauncher,
    PlaceRoad,
    PlaceSentinel,
    PlaceSplitter,
    Task,
    execute,
)
from .state import State
from .state_dump import dump
from .state_update import update as state_update
from .task_barrier_ore import _best_denied_ore, barrier_ore
from .task_connect_excess import ExcessKind, SearchKind, connect_excess
from .task_explore import explore
from .task_fire_enemy_transport import fire_enemy_transport
from .task_harvest_ax import harvest_ax
from .task_harvest_ti import harvest_ti
from .task_heal_core import heal_core
from .task_nav_enemy_core import nav_enemy_core
from .task_patrol import patrol
from .task_place_foundry_mixed_conv import place_foundry_mixed_conv
from .task_place_launcher import place_launcher
from .task_place_sentinel import _find_target as _find_sentinel_target
from .task_place_sentinel import place_sentinel
from .task_place_splitter_foundry import place_splitter_foundry
from .task_repair_bridge import _find_broken_bridge, repair_bridge
from .task_secure_ore import _best_ore as _secure_best_ore
from .task_secure_ore import secure_ore
from .task_self_destruct import self_destruct

DEBUG_DUMP = False

type TaskFn = Callable[[State, Controller], tuple[Direction, Action | None] | None]

TASK_FNS: dict[Task, TaskFn] = {
    Task.CONNECT_EXCESS_TI: lambda s, c: connect_excess(
        s,
        c,
        ExcessKind.TI_RAX,
        SearchKind.MIXED,
    ),
    Task.CONNECT_EXCESS_TI_BRIDGE: lambda s, c: connect_excess(
        s,
        c,
        ExcessKind.TI_RAX,
        SearchKind.BRIDGE,
    ),
    Task.CONNECT_EXCESS_AX: lambda s, c: connect_excess(
        s,
        c,
        ExcessKind.AX,
        SearchKind.AX_CHAIN,
    ),
    Task.HARVEST_TI: harvest_ti,
    Task.HARVEST_AX: harvest_ax,
    Task.EXPLORE: explore,
    Task.PATROL: patrol,
    Task.NAV_ENEMY_CORE: nav_enemy_core,
    Task.SELF_DESTRUCT: self_destruct,
    Task.PLACE_FOUNDRY_MIXED_CONV: place_foundry_mixed_conv,
    Task.PLACE_SPLITTER_FOUNDRY: place_splitter_foundry,
    Task.HEAL_CORE: heal_core,
    Task.SECURE_ORE: secure_ore,
    Task.PLACE_LAUNCHER: place_launcher,
    Task.REPAIR_BRIDGE: repair_bridge,
    Task.BARRIER_ORE: barrier_ore,
    Task.FIRE_ENEMY_TRANSPORT: fire_enemy_transport,
    Task.PLACE_SENTINEL: place_sentinel,
}


def _destroy_friendly(ct: Controller, pos: Position) -> None:
    bid = ct.get_tile_building_id(pos)
    if bid is not None and ct.get_team(bid) == ct.get_team() and ct.can_destroy(pos):
        ct.destroy(pos)


def _exec_build(ct: Controller, action: Action) -> None:
    match action:
        case PlaceRoad(pos):
            _destroy_friendly(ct, pos)
            if ct.can_build_road(pos):
                ct.build_road(pos)
        case PlaceHarvester(pos):
            _destroy_friendly(ct, pos)
            if ct.can_build_harvester(pos):
                ct.build_harvester(pos)
        case PlaceConveyor(pos, direction):
            _destroy_friendly(ct, pos)
            if ct.can_build_conveyor(pos, direction):
                ct.build_conveyor(pos, direction)
        case PlaceSplitter(pos, direction):
            _destroy_friendly(ct, pos)
            if ct.can_build_splitter(pos, direction):
                ct.build_splitter(pos, direction)
        case PlaceBridge(pos, target):
            _destroy_friendly(ct, pos)
            if ct.can_build_bridge(pos, target):
                ct.build_bridge(pos, target)
        case PlaceBarrier(pos):
            _destroy_friendly(ct, pos)
            if ct.can_build_barrier(pos):
                ct.build_barrier(pos)
        case PlaceLauncher(pos):
            _destroy_friendly(ct, pos)
            if ct.can_build_launcher(pos):
                ct.build_launcher(pos)
        case PlaceGunner(pos, direction):
            _destroy_friendly(ct, pos)
            if ct.can_build_gunner(pos, direction):
                ct.build_gunner(pos, direction)
        case PlaceSentinel(pos, direction):
            _destroy_friendly(ct, pos)
            if ct.can_build_sentinel(pos, direction):
                ct.build_sentinel(pos, direction)
        case PlaceFoundry(pos):
            _destroy_friendly(ct, pos)
            if ct.can_build_foundry(pos):
                ct.build_foundry(pos)


class Builder(Unit):
    def __init__(self, ct: Controller) -> None:
        core_pos = _find_core(ct)
        self.state = State(ct, core_pos)
        self._compiled: list[CompiledTurn] | None = None
        self._script_idx: int = 0
        self._off_script: bool = False

        opening, km = _read_opening(ct, core_pos)
        if opening is not None and km is not None:
            if ct.get_team() == Team.B:
                opening = mirror_opening(opening, SYMMETRY[km])
            spawn_turn = self.state.birthday - 1
            spawn_order = sum(
                1 for s in opening.core_spawns[:spawn_turn] if s is not None
            )
            if 0 <= spawn_order < len(opening.builder_scripts):
                self._compiled = dsl_compile(
                    ct.get_position(),
                    opening.builder_scripts[spawn_order],
                )

    def run(self, ct: Controller) -> None:
        s = self.state
        state_update(s, ct)

        if DEBUG_DUMP:
            dump(s, ct)
        s.claim = None

        if self._compiled is not None and not self._off_script:
            self._run_script(ct)
            return

        if self._compiled is not None:
            return

        move, build = self._run_policy(ct)
        self._execute(ct, move, build)

    def _run_script(self, ct: Controller) -> None:
        assert self._compiled is not None
        if self._script_idx >= len(self._compiled):
            self._off_script = True
            return

        turn = self._compiled[self._script_idx]
        self._script_idx += 1
        pos = ct.get_position()

        match turn:
            case CompiledActionMove(action, move):
                if action is not None:
                    _exec_build(ct, action)
                if move is not None:
                    if ct.can_move(move):
                        ct.move(move)
                    else:
                        ct.draw_indicator_dot(pos, 255, 0, 0)
                        self._off_script = True
            case CompiledMoveAction(move, action):
                if move is not None:
                    if ct.can_move(move):
                        ct.move(move)
                    else:
                        ct.draw_indicator_dot(pos, 255, 0, 0)
                        self._off_script = True
                        return
                if action is not None:
                    _exec_build(ct, action)

        if self._script_idx >= len(self._compiled):
            ct.draw_indicator_dot(ct.get_position(), 0, 255, 0)
            self._off_script = True

    def _run_policy(self, ct: Controller) -> tuple[Direction, Action | None]:
        s = self.state
        for _, task in _policy(s):
            fn = TASK_FNS[task]
            result = fn(s, ct)
            if result is not None:
                return result
        return Direction.CENTRE, None

    def _execute(self, ct: Controller, move: Direction, build: Action | None) -> None:
        s = self.state
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
        s.debug_target = None
        self._write_marker(ct)

    def _write_marker(self, ct: Controller) -> None:
        s = self.state
        marker_val = None
        if s.claim is not None:
            s.last_claim = s.claim
            marker_val = s.claim.encode()
        elif s.symmetry is not None:
            marker_val = MarkerEureka(s.symmetry.value).encode()
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


_MARKER_OFFSETS = ((2, 2), (-2, -2), (2, -2), (-2, 2), (0, 2), (0, -2), (2, 0), (-2, 0))


def _read_opening(
    ct: Controller,
    core_pos: Position,
) -> tuple[Opening | None, KnownMap | None]:
    w, h = ct.get_map_width(), ct.get_map_height()
    for odx, ody in _MARKER_OFFSETS:
        mx, my = core_pos.x + odx, core_pos.y + ody
        if not (0 <= mx < w and 0 <= my < h):
            continue
        mp = Position(mx, my)
        bid = ct.get_tile_building_id(mp)
        if bid is None:
            continue
        if ct.get_entity_type(bid) != EntityType.MARKER:
            continue
        if ct.get_team(bid) != ct.get_team():
            continue
        marker_val = ct.get_marker_value(bid)
        msg = decode_marker(marker_val)
        if isinstance(msg, MarkerOpeningBook):
            km_list = list(KnownMap)
            idx = msg.map_index
            if 0 <= idx < len(km_list):
                km = km_list[idx]
                return get_opening(km), km
    return None, None


def _has_undefended_bridge(state: State) -> bool:
    for p in state.my_transport:
        i = state.idx(p.x, p.y)
        bld = state.building[i]
        match bld:
            case BuildingBridge():
                pass
            case _:
                continue
        if any(
            state.in_bounds(p.x + dx, p.y + dy)
            and isinstance(
                state.building[state.idx(p.x + dx, p.y + dy)],
                BuildingLauncher,
            )
            and state.building[state.idx(p.x + dx, p.y + dy)].team == state.my_team
            for dx, dy in DIR8_DELTA
        ):
            continue
        return True
    return False


def _policy(state: State) -> list[tuple[float, Task]]:
    scores: list[tuple[float, Task]] = []

    core_damaged = state.my_core_hp < GameConstants.CORE_MAX_HP
    scores.append((999.0 if core_damaged else 0.0, Task.HEAL_CORE))

    has_ud_bridge = _has_undefended_bridge(state)
    scores.append((200.0 if has_ud_bridge else 0.0, Task.PLACE_LAUNCHER))

    has_broken = _find_broken_bridge(state) is not None
    scores.append((175.0 if has_broken else 0.0, Task.REPAIR_BRIDGE))

    has_excess = any(
        state.my_flow.excess[state.idx(p.x, p.y)] > 0.01
        for p in state.my_harvesters | state.my_transport
    )
    scores.append((150.0 if has_excess else 0.0, Task.CONNECT_EXCESS_TI_BRIDGE))

    has_denied_ore = _best_denied_ore(state) is not None
    scores.append((110.0 if has_denied_ore else 0.0, Task.BARRIER_ORE))

    visible_ore = _secure_best_ore(state)
    scores.append((100.0 if visible_ore is not None else 0.0, Task.SECURE_ORE))

    has_fire_target = len(state.en_transport) > 0
    scores.append((75.0 if has_fire_target else 0.0, Task.FIRE_ENEMY_TRANSPORT))

    has_sentinel_target = _find_sentinel_target(state) is not None
    scores.append((70.0 if has_sentinel_target else 0.0, Task.PLACE_SENTINEL))

    scores.append((20.0, Task.EXPLORE))
    scores.append((5.0, Task.PATROL))

    scores.sort(key=lambda t: t[0], reverse=True)
    return scores
