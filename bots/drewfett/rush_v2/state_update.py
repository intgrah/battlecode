"""State mutation — single update() entry point called once per turn."""

from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    ETYPE_BUILDING,
    Building,
    BuildingArmouredConveyor,
    BuildingBarrier,
    BuildingBreach,
    BuildingBridge,
    BuildingConveyor,
    BuildingCore,
    BuildingFoundry,
    BuildingGunner,
    BuildingHarvester,
    BuildingLauncher,
    BuildingMarker,
    BuildingSentinel,
    BuildingSplitter,
)
from cambc import Controller, EntityType, Environment, Position
from flow_sim import update_flow
from marker import (
    MarkerChainPlan,
    MarkerClaim,
    MarkerEureka,
    MarkerRole,
    is_stale,
    is_stale_chain,
)
from marker import decode as decode_marker
from util import COST_IMPASSABLE, Role, Symmetry

if TYPE_CHECKING:
    from state import State

__all__ = ["update"]

_REFLECT_BUDGET: int = 25


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def update(state: State, ct: Controller) -> None:
    state.age += 1
    state.pos = ct.get_position()

    _update_core_hp(state, ct)
    _update_ephemeral(state, ct)
    changed = _scan_vision(state, ct)
    _rebuild_danger_zones(state)
    _stamp_unit_tiles(state)
    _update_flow(state, changed)
    _update_infra_staleness(state)


# ---------------------------------------------------------------------------
# Core HP
# ---------------------------------------------------------------------------


def _update_core_hp(state: State, ct: Controller) -> None:
    core = state.my_core
    if not ct.is_in_vision(core):
        return
    bid = ct.get_tile_building_id(core)
    if bid is None:
        return
    state.my_core_hp = ct.get_hp(bid)


# ---------------------------------------------------------------------------
# Ephemeral reset
# ---------------------------------------------------------------------------


def _update_ephemeral(state: State, ct: Controller) -> None:
    rnd = ct.get_current_round()
    w = state.w

    for p in state.unit_tiles:
        state.update_cost(p.y * w + p.x)
    state.unit_tiles.clear()

    my_id = ct.get_id()
    for uid in ct.get_nearby_units():
        if uid == my_id:
            continue
        state.unit_tiles.add(ct.get_position(uid))

    state.claims = {c for c in state.claims if not is_stale(c.turn, rnd)}
    state.chain_claims = {
        c for c in state.chain_claims if not is_stale_chain(c.turn, rnd)
    }


# ---------------------------------------------------------------------------
# Vision scan
# ---------------------------------------------------------------------------


def _make_building(ct: Controller, bid: int, etype: EntityType) -> Building | None:
    team = ct.get_team(bid)
    match etype:
        case EntityType.CONVEYOR | EntityType.ARMOURED_CONVEYOR | EntityType.SPLITTER:
            cls = ETYPE_BUILDING[etype]
            return cls(team, ct.get_direction(bid))
        case EntityType.GUNNER | EntityType.SENTINEL | EntityType.BREACH:
            cls = ETYPE_BUILDING[etype]
            return cls(team, ct.get_direction(bid))
        case EntityType.BRIDGE:
            return BuildingBridge(team, ct.get_bridge_target(bid))
        case EntityType.MARKER:
            if team == ct.get_team():
                return BuildingMarker(team, ct.get_marker_value(bid))
            return BuildingMarker(team, 0)
        case _:
            cls = ETYPE_BUILDING.get(etype)
            if cls is None:
                return None
            return cls(team)


def _scan_vision(state: State, ct: Controller) -> list[int]:
    w = state.w
    changed: list[int] = []
    new_tiles: list[tuple[Position, Environment]] = []
    rnd = ct.get_current_round()
    my_team = state.my_team

    for t in ct.get_nearby_tiles():
        i = t.y * w + t.x
        state.last_seen[i] = rnd

        old_env = state.env[i]
        env = ct.get_tile_env(t)

        if env != old_env:
            state.env[i] = env
            match env:
                case Environment.ORE_TITANIUM:
                    state.ore_ti.add(i)
                case Environment.ORE_AXIONITE:
                    state.ore_ax.add(i)

        bid = ct.get_tile_building_id(t)
        old_bld = state.building[i]
        if bid is not None:
            etype = ct.get_entity_type(bid)
            bld = _make_building(ct, bid, etype)
            if bld != old_bld or env != old_env:
                state.building[i] = bld
                _update_sets(state, i, old_bld, bld)
                changed.append(i)
                state.update_cost(i)

            match bld:
                case BuildingMarker(team) if team == my_team:
                    _process_marker(state, bld.value, rnd)
                case BuildingCore(team) if team != my_team:
                    state.en_core_tiles.add(i)
                    if state.en_core_pos is None:
                        state.en_core_pos = ct.get_position(bid)
        elif old_bld is not None or env != old_env:
            state.building[i] = None
            _update_sets(state, i, old_bld, None)
            changed.append(i)
            state.update_cost(i)

        new_tiles.append((t, env))

    _apply_symmetry(state, new_tiles)
    _drain_reflect_queue(state)
    return changed


def _process_marker(state: State, value: int, rnd: int) -> None:
    msg = decode_marker(value)
    match msg:
        case MarkerRole(role=r, birthday=bday) if (
            state.role == Role.ECON and bday == state.birthday % 2048
        ):
            state.role = Role(r)
        case MarkerClaim(turn=turn) if not is_stale(turn, rnd):
            state.claims.add(msg)
        case MarkerChainPlan(turn=turn) if not is_stale_chain(turn, rnd):
            state.chain_claims.add(msg)
        case MarkerEureka() if state.symmetry is None:
            state.symmetry = Symmetry(msg.symmetry)


# ---------------------------------------------------------------------------
# Set maintenance
# ---------------------------------------------------------------------------


def _classify(bld: Building | None) -> str | None:
    if bld is None:
        return None
    match bld:
        case BuildingHarvester():
            return "harvesters"
        case (
            BuildingConveyor()
            | BuildingArmouredConveyor()
            | BuildingSplitter()
            | BuildingBridge()
        ):
            return "transport"
        case BuildingFoundry():
            return "foundries"
        case (
            BuildingGunner()
            | BuildingSentinel()
            | BuildingBreach()
            | BuildingLauncher()
        ):
            return "turrets"
        case BuildingBarrier():
            return "barriers"
    return None


def _update_sets(
    state: State,
    idx: int,
    old_bld: Building | None,
    new_bld: Building | None,
) -> None:
    my_team = state.my_team
    old_cat = _classify(old_bld)
    new_cat = _classify(new_bld)
    if old_cat == new_cat and (
        old_bld is None or new_bld is None or old_bld.team == new_bld.team
    ):
        return

    if old_cat is not None and old_bld is not None:
        getattr(state, old_cat).discard(idx)
        prefix = "my_" if old_bld.team == my_team else "en_"
        getattr(state, prefix + old_cat).discard(idx)

    if new_cat is not None and new_bld is not None:
        getattr(state, new_cat).add(idx)
        prefix = "my_" if new_bld.team == my_team else "en_"
        getattr(state, prefix + new_cat).add(idx)


# ---------------------------------------------------------------------------
# Danger zones
# ---------------------------------------------------------------------------


def _rebuild_danger_zones(state: State) -> None:
    w, h = state.w, state.h
    state.danger_zones = set()

    for ti in state.en_turrets:
        bld = state.building[ti]
        tx, ty = ti % w, ti // w

        match bld:
            case BuildingLauncher():
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        nx, ny = tx + dx, ty + dy
                        if 0 <= nx < w and 0 <= ny < h:
                            state.cost[ny * w + nx] = COST_IMPASSABLE

            case (
                BuildingGunner(direction=d)
                | BuildingSentinel(direction=d)
                | BuildingBreach(direction=d)
            ):
                ddx, ddy = d.delta()
                r_sq = 32 if isinstance(bld, BuildingSentinel) else 13
                is_sentinel = isinstance(bld, BuildingSentinel)
                x, y = tx + ddx, ty + ddy
                while 0 <= x < w and 0 <= y < h:
                    if (x - tx) ** 2 + (y - ty) ** 2 > r_sq:
                        break
                    state.danger_zones.add(y * w + x)
                    if is_sentinel:
                        for adx in range(-1, 2):
                            for ady in range(-1, 2):
                                ax, ay = x + adx, y + ady
                                if (
                                    0 <= ax < w
                                    and 0 <= ay < h
                                    and (ax - tx) ** 2 + (ay - ty) ** 2 <= r_sq
                                ):
                                    state.danger_zones.add(ay * w + ax)
                    x += ddx
                    y += ddy

    for ti in state.my_turrets:
        bld = state.building[ti]
        match bld:
            case BuildingGunner(direction=d, team=team) if team == state.my_team:
                tx, ty = ti % w, ti // w
                ddx, ddy = d.delta()
                x, y = tx + ddx, ty + ddy
                while 0 <= x < w and 0 <= y < h:
                    if (x - tx) ** 2 + (y - ty) ** 2 > 13:
                        break
                    state.danger_zones.add(y * w + x)
                    x += ddx
                    y += ddy


# ---------------------------------------------------------------------------
# Unit tile stamping
# ---------------------------------------------------------------------------


def _stamp_unit_tiles(state: State) -> None:
    w = state.w
    cost = state.cost
    for p in state.unit_tiles:
        cost[p.y * w + p.x] = COST_IMPASSABLE


# ---------------------------------------------------------------------------
# Flow recompute
# ---------------------------------------------------------------------------


def _update_flow(state: State, changed: list[int]) -> None:
    infra = state.transport | state.harvesters | state.foundries | state.turrets
    if not any(i in infra for i in changed):
        return
    update_flow(state)


# ---------------------------------------------------------------------------
# Infrastructure staleness
# ---------------------------------------------------------------------------


def _update_infra_staleness(state: State) -> None:
    age = state.age
    worst = 0
    for i in state.my_transport:
        s = age - state.last_seen[i]
        worst = max(worst, s)
    for i in state.my_turrets:
        s = age - state.last_seen[i]
        worst = max(worst, s)
    for i in state.my_core_tiles:
        s = age - state.last_seen[i]
        worst = max(worst, s)
    state.infra_max_staleness = worst


# ---------------------------------------------------------------------------
# Symmetry
# ---------------------------------------------------------------------------


def _mirror_pos(state: State, p: Position) -> Position:
    x, y = p
    match state.symmetry:
        case Symmetry.ROT:
            return Position(state.w - 1 - x, state.h - 1 - y)
        case Symmetry.HOR:
            return Position(x, state.h - 1 - y)
        case Symmetry.VER:
            return Position(state.w - 1 - x, y)
        case None:
            return Position(x, y)


def _mirror_xy(sym: Symmetry, w: int, h: int, x: int, y: int) -> tuple[int, int]:
    match sym:
        case Symmetry.ROT:
            return w - 1 - x, h - 1 - y
        case Symmetry.HOR:
            return x, h - 1 - y
        case Symmetry.VER:
            return w - 1 - x, y


def _apply_symmetry(
    state: State,
    new_tiles: list[tuple[Position, Environment]],
) -> None:
    had_symmetry = state.symmetry is not None
    if not had_symmetry:
        _eliminate_symmetries(state, new_tiles)

    if state.symmetry is not None:
        if not state.en_core_tiles:
            correct_pos = _mirror_pos(state, state.my_core)
            if state.en_core_pos != correct_pos:
                state.en_core_pos = correct_pos
    elif state.sym_candidates:
        _infer_enemy_core_from_candidates(state)

    if state.symmetry is None:
        return

    w = state.w
    if had_symmetry:
        source = new_tiles
    else:
        source = [
            (Position(i % w, i // w), e)
            for i, e in enumerate(state.env)
            if e is not None
        ]

    pending = state.reflect_queue
    for t, env in source:
        m = _mirror_pos(state, t)
        mi = m.y * w + m.x
        if state.env[mi] is not None:
            continue
        state.env[mi] = env
        match env:
            case Environment.ORE_TITANIUM:
                state.ore_ti.add(mi)
            case Environment.ORE_AXIONITE:
                state.ore_ax.add(mi)
        pending.append(mi)


def _drain_reflect_queue(state: State) -> None:
    pending = state.reflect_queue
    if not pending:
        return
    n = min(len(pending), _REFLECT_BUDGET)
    for _ in range(n):
        state.update_cost(pending.popleft())


def _eliminate_symmetries(
    state: State,
    new_tiles: list[tuple[Position, Environment]],
) -> None:
    w, h = state.w, state.h
    cx, cy = state.my_core.x, state.my_core.y
    to_remove: set[Symmetry] = set()

    for sym in state.sym_candidates:
        mx, my = _mirror_xy(sym, w, h, cx, cy)
        if (mx, my) == (cx, cy):
            to_remove.add(sym)

    if state.en_core_tiles:
        for sym in state.sym_candidates:
            mx, my = _mirror_xy(sym, w, h, cx, cy)
            if Position(mx, my) not in state.en_core_tiles:
                to_remove.add(sym)

    for t, env in new_tiles:
        for sym in state.sym_candidates - to_remove:
            mx, my = _mirror_xy(sym, w, h, t.x, t.y)
            mi = my * w + mx
            mirror_env = state.env[mi]
            if mirror_env is not None and mirror_env != env:
                to_remove.add(sym)

    state.sym_candidates -= to_remove

    if len(state.sym_candidates) == 1:
        state.symmetry = next(iter(state.sym_candidates))
    elif len(state.sym_candidates) > 1:
        positions: set[tuple[int, int]] = set()
        for sym in state.sym_candidates:
            positions.add(_mirror_xy(sym, w, h, cx, cy))
        if len(positions) == 1:
            state.symmetry = next(iter(state.sym_candidates))


def _infer_enemy_core_from_candidates(state: State) -> None:
    w, h = state.w, state.h
    cx, cy = state.my_core.x, state.my_core.y
    candidates: dict[tuple[int, int], Symmetry] = {}
    for sym in state.sym_candidates:
        candidates[_mirror_xy(sym, w, h, cx, cy)] = sym

    unique_positions = set(candidates.keys())
    if len(unique_positions) == 1:
        pos = next(iter(unique_positions))
        state.en_core_pos = Position(pos[0], pos[1])
    elif Symmetry.ROT in state.sym_candidates:
        state.en_core_pos = Position(w - 1 - cx, h - 1 - cy)
    else:
        sym = next(iter(state.sym_candidates))
        mx, my = _mirror_xy(sym, w, h, cx, cy)
        state.en_core_pos = Position(mx, my)
