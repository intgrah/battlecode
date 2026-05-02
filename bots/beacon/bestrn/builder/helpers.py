"""Translation of `bots/intgrah/v54.7.9/builder/helpers.py`."""
from __future__ import annotations

from typing import Final

from cambc import Direction, EntityType, Environment, ResourceType
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cambc import Controller, ControllerApi, Position
if TYPE_CHECKING:
    from builder import Builder
from util.constants import MAX_WIDTH, base_cost
from util.debug import Scope, debug as log
from util.directions import DIR4, DIR8, delta_to_dir
from util.metrics import chebyshev, claims_by_proximity, manhattan
from util.visualiser import auto_wrap_position

def make_move(builder, ct, target):
    """
    Return True iff this call actually issued a move. 'Already at target'
    and 'no plan' both return False — neither advances the builder, so the
    caller shouldn't treat the turn as productive.
    """
    if builder.state.my_pos == target:
        args = {}
        args[str("target")] = auto_wrap_position(target)
        log("make_move: already on target {target}", args)
        return False
    next_move = builder.bugnav_step(target)
    next_move = next_move
    if next_move is None:
        if move_random(builder, ct):
            args = {}
            args[str("start")] = auto_wrap_position(builder.state.my_pos)
            args[str("target")] = auto_wrap_position(target)
            log("make_move: bugnav stuck, took random step {start}->{target}", args)
            return True
        args = {}
        args[str("start")] = auto_wrap_position(builder.state.my_pos)
        args[str("target")] = auto_wrap_position(target)
        log("make_move: FAILED {start}->{target} (bugnav: no plan, random step also blocked)", args)
        return False
    args = {}
    args[str("start")] = auto_wrap_position(builder.state.my_pos)
    args[str("target")] = auto_wrap_position(target)
    args[str("next")] = auto_wrap_position(next_move)
    log("make_move: bugnav {start}->{target} step {next}", args)
    return try_move_with_road(builder, ct, next_move)

def make_move_or_adjacent(builder, ct, target):
    """
    Like `make_move`, but if `target` itself is impassable, routes to the
    closest passable cardinal of `target` instead.
    """
    if builder.cost_grid[builder.idx(target)] != 1000000:
        return make_move(builder, ct, target)
    best: Position | None = None
    best_d: int = 1 << 30
    for d in DIR4:
        c = target.add(d)
        if not builder.in_bounds(c) or not builder.cost_grid[builder.idx(c)] != 1000000:
            continue
        cd = chebyshev(builder.state.my_pos, c)
        if cd < best_d:
            best_d = cd
            best = c
    best = best
    if best is None:
        args = {}
        args[str("target")] = auto_wrap_position(target)
        log("make_move_or_adjacent: {target} impassable AND no passable cardinal", args)
        return False
    if builder.state.my_pos == best:
        args = {}
        args[str("target")] = auto_wrap_position(target)
        args[str("pos")] = auto_wrap_position(builder.state.my_pos)
        log("make_move_or_adjacent: already adjacent to {target} (at {pos})", args)
        return False
    args = {}
    args[str("target")] = auto_wrap_position(target)
    args[str("adj")] = auto_wrap_position(best)
    log("make_move_or_adjacent: {target} impassable, routing to cardinal {adj}", args)
    return make_move(builder, ct, best)

def try_move_dir(ct, d):
    if ct.can_move(d):
        args = {}
        args[str("dir")] = f"{d}"
        log("try_move_dir: moving {dir}", args)
        ct.move(d)
        return True
    return False

def try_move_to(builder, ct, target_pos):
    dx = target_pos.x - builder.state.my_pos.x
    dy = target_pos.y - builder.state.my_pos.y
    d = delta_to_dir(dx, dy)
    if d is None:
        return False
    if ct.can_move(d):
        args = {}
        args[str("start")] = auto_wrap_position(builder.state.my_pos)
        args[str("target")] = auto_wrap_position(target_pos)
        args[str("dir")] = f"{d}"
        log("try_move_to: {start}->{target} dir {dir}", args)
        hx = int(dx > 0) - int(dx < 0)
        hy = int(dy > 0) - int(dy < 0)
        builder.explore_heading = (hx, hy)
        ct.move(d)
        return True
    return False

def try_move_with_road(builder, ct, target_pos):
    if builder.cost_grid[builder.idx(target_pos)] > 1 and ct.can_build_road(target_pos):
        args = {}
        args[str("target")] = auto_wrap_position(target_pos)
        args[str("cost")] = builder.cost_grid[builder.idx(target_pos)]
        log("try_move_with_road: paving road at {target} (cost={cost} > 1)", args)
        ct.build_road(target_pos)
    return try_move_to(builder, ct, target_pos)

def try_attack(ct, pos):
    if ct.can_fire(pos):
        args = {}
        args[str("pos")] = auto_wrap_position(pos)
        log("try_attack: firing on {pos}", args)
        ct.fire(pos)
        return True
    return False

def ti_needed(builder, etype):
    base = c[0] if ((c := base_cost(etype)) is not None) else 0
    scale = builder.state.scale
    foundry = int(float(base_cost(EntityType.FOUNDRY)[0]) * scale) if builder.state.round >= 500 and not (not builder.ax_harvester_adjacent) else 0
    match etype:
        case EntityType.FOUNDRY:
            return int(float(base) * scale)
        case EntityType.HARVESTER:
            reserve = 10 if builder.state.round < 35 else 20
            return int(float(base + reserve) * (1.0 + scale)) + foundry
        case EntityType.LAUNCHER:
            return int(float(base + 15) * (1.0 + scale)) + foundry
        case EntityType.SENTINEL | EntityType.GUNNER:
            return int(float(base) * (1.0 + scale)) + foundry
        case _:
            return int(float(base) * scale) + foundry

def can_afford(builder, etype):
    return builder.state.ti >= ti_needed(builder, etype)

def required_ti_for_ore_claim(builder, ore_pos, sink_pos):
    """
    Heuristic Ti cost to walk to `ore_pos`, place a harvester, ring
    it inward (worst case 3 sides), and route the chain back to
    `sink_pos`.
    """
    s = builder.state.scale
    h_cost = int(float(base_cost(EntityType.HARVESTER)[0]) * (1.0 + s))
    c_cost = int(float(base_cost(EntityType.CONVEYOR)[0]) * s)
    b_cost = int(float(base_cost(EntityType.BRIDGE)[0]) * s)
    r_cost = max(int(float(base_cost(EntityType.ROAD)[0]) * s), 1)
    d_pos = manhattan(builder.state.my_pos, ore_pos)
    d_sink = manhattan(ore_pos, sink_pos)
    walk_cost = d_pos * r_cost
    ring_cost = 3 * c_cost
    chain_cost = int(float(d_sink) * (0.7 * float(c_cost) + 0.3 * float(b_cost) / 3.0))
    return h_cost + ring_cost + chain_cost + walk_cost

def ore_claim_leniency(builder):
    """
    Leniency multiplier on `required_ti_for_ore_claim`. Decaying
    exponential in friendly harvester count: starts at 0.65, asymptotes to 1.60.
    """
    n = float(len(builder.my_harvesters))
    return (0.95 * (1.0 - ((0.958) ** (n))) + 0.65)

def can_afford_ore_claim(builder, ore_pos, sink_pos):
    return builder.state.ti >= int(float(required_ti_for_ore_claim(builder, ore_pos, sink_pos)) * ore_claim_leniency(builder))
type TryPlaceExtra = BuildExtra

def try_place(builder, ct, etype, pos, extra, destroy):
    if not can_afford(builder, etype):
        args = {}
        args[str("etype")] = f"{etype!r}"
        args[str("pos")] = auto_wrap_position(pos)
        args[str("have")] = builder.state.ti
        args[str("need")] = ti_needed(builder, etype)
        match base_cost(etype):
            case None:
                base_for_log = 0
            case c if c is not None:
                base_for_log = c[0]
        args[str("base")] = base_for_log
        args[str("scale")] = builder.state.scale
        log("try_place: cannot afford {etype} at {pos} (have {have}, need {need}; base {base}, scale {scale:.2f})", args)
        return False
    if destroy and ct.can_destroy(pos):
        args = {}
        args[str("pos")] = auto_wrap_position(pos)
        args[str("etype")] = f"{etype!r}"
        log("try_place: destroying existing building at {pos} for {etype}", args)
        ct.destroy(pos)
        builder.apply_local_destroy(pos)
    if ct.can_build(etype, pos, extra):
        args = {}
        args[str("etype")] = f"{etype!r}"
        args[str("pos")] = auto_wrap_position(pos)
        args[str("extra")] = f"{extra!r}"
        args[str("ti")] = builder.state.ti
        args[str("scale")] = builder.state.scale
        log("try_place: built {etype} at {pos} extra={extra} (ti={ti}, scale={scale:.2f})", args)
        ct.build(etype, pos, extra)
        return True
    args = {}
    args[str("etype")] = f"{etype!r}"
    args[str("pos")] = auto_wrap_position(pos)
    args[str("extra")] = f"{extra!r}"
    log("try_place: controller rejected {etype} at {pos} extra={extra} (can_build False)", args)
    return False

def trace_downstream(builder, start_pos, target_head):
    path: list[Position] = []
    _trace_downstream_inner(builder, start_pos, target_head, path)
    return path

def _trace_downstream_inner(builder, start_pos, target_head, path):
    current_pos = start_pos
    while True:
        path.append(current_pos)
        i = builder.idx(current_pos)
        kind = builder.building_kind[i]
        match kind:
            case EntityType.CONVEYOR | EntityType.ARMOURED_CONVEYOR | EntityType.BRIDGE:
                if (not builder.out_edges[i]):
                    break
                current_pos = builder.out_edges[i][0]
            case EntityType.SPLITTER:
                outs: list[Position] = list(builder.out_edges[i])
                for new_pos in outs:
                    target_head = target_head
                    if target_head is not None:
                        new_path = list(path)
                        _trace_downstream_inner(builder, new_pos, target_head, new_path)
                        if not (not new_path) and (target_head in new_path):
                            path = new_path
                            return
                    elif (builder.get_building(new_pos) is None):
                        path.append(new_pos)
                        return
            case _:
                break
        if (current_pos in path):
            break

def try_heal(builder, ct, position, conserve_ti):
    repair_pos = builder.repair_pos
    if (conserve_ti) and repair_pos is not None:
        i = builder.idx(repair_pos)
        if (builder.building_kind[i] is None) or builder.hp[i] > builder.max_hp[i] - 4:
            return False
    if ct.can_heal(position):
        args = {}
        args[str("pos")] = auto_wrap_position(position)
        log("try_heal: healing {pos}", args)
        ct.heal(position)
        return True
    return False

def move_random(builder, ct):
    dir8: list[Direction] = list(DIR8)
    builder.state.rng.shuffle(dir8)
    for direction in dir8:
        if ct.can_move(direction):
            ct.move(direction)
            return True
    return False

def trace_upstream(builder, position):
    path: list[Position] = []
    feeders: list[Position] = [position]
    while not (not feeders):
        position = feeders[0]
        feeders = builder.get_in_edges(position)
        if (position in path):
            break
        path.append(position)
    return path

def ore_available(builder, pos):
    __opt_kind__team = builder.get_building(pos)
    kind = __opt_kind__team[0] if __opt_kind__team is not None else None
    _team = __opt_kind__team[1] if __opt_kind__team is not None else None
    if __opt_kind__team is not None:
        allowed = (kind == EntityType.ROAD or kind == EntityType.MARKER or kind == EntityType.BARRIER) or (kind == EntityType.CONVEYOR or kind == EntityType.ARMOURED_CONVEYOR) and is_inward_guard(builder, pos)
        if not allowed:
            return False
    uid = builder.state.all_bots.get(pos)
    if uid is not None and (uid != builder.state.my_id):
        return False
    return True

def harvester_feed_cardinal(builder, ore_pos):
    """The cardinal of `ore_pos` chosen as the future flow-feed slot."""
    sink: Position | None = (builder.en_core_guess if (builder.symmetry is not None) else None) if on_enemy_side(builder, ore_pos) else (t if ((t := builder.ti_sink) is not None) else builder.my_core)
    sink = sink
    if sink is None:
        args = {}
        args[str("ore")] = auto_wrap_position(ore_pos)
        log("harvester_feed_cardinal({ore}): no sink — symmetry unresolved", args)
        return None
    tier1: list[Position] = []
    tier2: list[Position] = []
    classification: list[tuple[Position, str]] = []
    for d in DIR4:
        c = ore_pos.add(d)
        if not builder.in_bounds(c):
            continue
        if c == builder.state.my_pos:
            classification.append((c, "my_pos"))
            continue
        if builder.env[builder.idx(c)] == Environment.WALL:
            classification.append((c, "wall"))
            continue
        ci = builder.idx(c)
        kind = builder.building_kind[ci]
        team = builder.building_team[ci]
        if ((kind is not None) and (kind == EntityType.BRIDGE or kind == EntityType.CONVEYOR or kind == EntityType.ARMOURED_CONVEYOR or kind == EntityType.SPLITTER)) and team != builder.state.my_team:
            classification.append((c, "enemy_transport"))
            continue
        match kind:
            case EntityType.BRIDGE:
                target = ((builder.out_edges[ci][0] if builder.out_edges[ci] else None) if (builder.out_edges[ci][0] if builder.out_edges[ci] else None) is not None else c)
                if target == ore_pos:
                    classification.append((c, "inward_guard: bridge target == ore"))
                else:
                    tier1.append(c)
                    classification.append((c, "tier1: bridge"))
                continue
            case EntityType.CONVEYOR | EntityType.ARMOURED_CONVEYOR:
                target = ((builder.out_edges[ci][0] if builder.out_edges[ci] else None) if (builder.out_edges[ci][0] if builder.out_edges[ci] else None) is not None else c)
                if target == ore_pos:
                    classification.append((c, "inward_guard: conveyor output -> ore"))
                else:
                    tier1.append(c)
                    classification.append((c, "tier1: outward conveyor"))
                continue
            case EntityType.SPLITTER:
                outs = builder.out_edges[ci]
                if len(outs) == 3:
                    back = splitter_back_input(c, outs)
                    if back == ore_pos:
                        tier1.append(c)
                        classification.append((c, "tier1: outward splitter"))
                    else:
                        classification.append((c, "inward_guard: splitter back not -> ore"))
                continue
            case EntityType.CORE if team == builder.state.my_team:
                tier1.append(c)
                classification.append((c, "tier1: my_core"))
                continue
            case EntityType.FOUNDRY | EntityType.CORE | EntityType.HARVESTER | EntityType.BARRIER:
                classification.append((c, "blocking_building"))
                continue
            case _:
                pass
        dx = c.x - ore_pos.x
        dy = c.y - ore_pos.y
        d_away = delta_to_dir(dx, dy)
        if d_away is None:
            continue
        u_shape = [c.add(d_away), c.add(rotate_left(rotate_left(d_away))), c.add(rotate_right(rotate_right(d_away))), c.add(rotate_left(d_away)), c.add(rotate_right(d_away))]
        has_escape = any(builder.in_bounds(p) and builder.cost_grid[builder.idx(p)] != 1000000 for p in u_shape)
        if not has_escape:
            classification.append((c, "no_escape"))
            continue
        tier2.append(c)
        classification.append((c, "tier2"))
    chosen: Position | None = (min(tier1, key=lambda c: c.distance_squared(sink)) if tier1 else None) if not (not tier1) else ((min(tier2, key=lambda c: c.distance_squared(sink)) if tier2 else None) if not (not tier2) else None)
    if (chosen is None):
        label = f"feed_pick_{ore_pos.x}_{ore_pos.y}"
        with Scope(label) as _g:
            args = {}
            args[str("ore")] = auto_wrap_position(ore_pos)
            log("feed_pick({ore}): NONE", args)
            for d in DIR4:
                c = ore_pos.add(d)
                if not builder.in_bounds(c):
                    continue
                status = (next((__v for t in classification if (__v := t[1] if t[0] == c else None) is not None), None) if next((__v for t in classification if (__v := t[1] if t[0] == c else None) is not None), None) is not None else "?")
                args = {}
                args[str("c")] = auto_wrap_position(c)
                args[str("status")] = str(status)
                log("  {c}: {status}", args)
    return chosen

def harvester_io_cardinals(builder, ore_pos):
    """Cardinals of `ore_pos` that must NOT be barriered."""
    cardinals: list[Position] = list((p for p in (ore_pos.add(d) for d in DIR4) if builder.in_bounds(p)))
    reserved: set[Position] = set()
    for c in cardinals:
        if c == builder.state.my_pos:
            reserved.add(c)
            continue
        if ((builder.building_kind[builder.idx(c)] is not None) and (builder.building_kind[builder.idx(c)] == EntityType.CONVEYOR or builder.building_kind[builder.idx(c)] == EntityType.ARMOURED_CONVEYOR or builder.building_kind[builder.idx(c)] == EntityType.SPLITTER or builder.building_kind[builder.idx(c)] == EntityType.BRIDGE or builder.building_kind[builder.idx(c)] == EntityType.FOUNDRY or builder.building_kind[builder.idx(c)] == EntityType.CORE or builder.building_kind[builder.idx(c)] == EntityType.HARVESTER)):
            reserved.add(c)
    feed = harvester_feed_cardinal(builder, ore_pos)
    if feed is not None:
        reserved.add(feed)
    return reserved

def harvester_barrier_saturated(builder, ore_pos):
    """True iff at least 3 of `ore_pos`'s 4 in-bounds cardinals already host a barrier."""
    barriers = 0
    for d in DIR4:
        c = ore_pos.add(d)
        if not builder.in_bounds(c):
            continue
        if builder.building_kind[builder.idx(c)] == EntityType.BARRIER:
            barriers += 1
    return barriers >= 3

def pick_ore_target(builder):
    return _pick_ore(builder, Environment.ORE_TITANIUM)

def pick_ax_ore_target(builder):
    return _pick_ore(builder, Environment.ORE_AXIONITE)

def pick_offensive_ti_ore_target(builder):
    """Pick a Ti ore tile outside our econ disc for an offensive harvester."""
    econ_radius_sq = builder.econ_radius_sq
    my_pos = builder.state.my_pos
    my_core = builder.my_core
    friendlies: list[tuple[Position, int]] = list((__v for t in builder.state.all_bots.items() if (__v := (t[0], t[1]) if t[1] != builder.state.my_id and (t[0] in builder.state.friendly_bots) else None) is not None))
    best_target: Position | None = None
    min_dist = 9223372036854775807
    for pos in sorted(builder.visible_ti_ores):
        if not builder.is_reachable(pos):
            continue
        if pos.distance_squared(my_core) <= econ_radius_sq:
            continue
        if not ore_available(builder, pos):
            continue
        d = my_pos.distance_squared(pos)
        if d >= min_dist:
            continue
        match builder.building_kind[builder.idx(pos)]:
            case None | EntityType.ROAD | EntityType.MARKER | EntityType.BARRIER:
                pass
            case EntityType.CONVEYOR | EntityType.ARMOURED_CONVEYOR:
                if not is_inward_guard(builder, pos):
                    continue
            case _:
                continue
        if not claims_by_proximity(my_pos, builder.state.my_id, pos, friendlies):
            continue
        if harvester_would_contaminate(builder, pos):
            continue
        min_dist = d
        best_target = pos
    return best_target

def harvester_would_contaminate(builder, pos):
    ore_env = builder.env[builder.idx(pos)]
    if ore_env == Environment.ORE_TITANIUM:
        bad_upstream, bad_flows = (builder.ax_upstream, [ResourceType.RAW_AXIONITE, ResourceType.REFINED_AXIONITE])
    else:
        if ore_env == Environment.ORE_AXIONITE:
            bad_upstream, bad_flows = (builder.ti_upstream, [ResourceType.TITANIUM])
        else:
            return False
    pure_ti_conveyor_count = 0
    heavy_hostile_count = 0
    hostile_found = False
    for d in DIR4:
        n = pos.add(d)
        if not builder.in_bounds(n):
            continue
        __opt_tuple = builder.get_building(n)
        if __opt_tuple is None:
            continue
        kind, team = __opt_tuple
        if not (kind == EntityType.CONVEYOR or kind == EntityType.ARMOURED_CONVEYOR or kind == EntityType.SPLITTER or kind == EntityType.BRIDGE):
            continue
        if team != builder.state.my_team:
            continue
        ni = int(n.y) * 50 + int(n.x)
        is_bad = (n in bad_upstream) or any((t[0] is not None and (lambda res: (res in bad_flows))(t[0])) for t in builder.flow_history[ni])
        if not is_bad:
            continue
        hostile_found = True
        if ore_env == Environment.ORE_AXIONITE:
            if kind == EntityType.CONVEYOR:
                pure_ti_conveyor_count += 1
            else:
                heavy_hostile_count += 1
    if not hostile_found:
        return False
    return not (ore_env == Environment.ORE_AXIONITE and heavy_hostile_count == 0 and pure_ti_conveyor_count == 1)

def on_enemy_side(builder, pos):
    """
    True if `pos` is outside our econ disc — i.e. more than
    `sqrt(econ_radius_sq)` (= 0.7·max(w,h)) from our core.
    """
    return pos.distance_squared(builder.my_core) > builder.econ_radius_sq

def is_inward_guard(builder, pos):
    """
    True if `pos` hosts a friendly conveyor whose flow direction
    points at an adjacent friendly harvester.
    """
    i = builder.idx(pos)
    kind = builder.building_kind[i]
    team = builder.building_team[i]
    if not ((kind is not None) and (kind == EntityType.CONVEYOR or kind == EntityType.ARMOURED_CONVEYOR)):
        return False
    if team != builder.state.my_team:
        return False
    if (not builder.out_edges[i]):
        return False
    target = builder.out_edges[i][0]
    if not builder.in_bounds(target):
        return False
    return builder.building_kind[builder.idx(target)] == EntityType.HARVESTER and builder.building_team[builder.idx(target)] == builder.state.my_team

def _pick_ore(builder, wanted):
    ore_set = builder.visible_ti_ores if wanted == Environment.ORE_TITANIUM else builder.visible_ax_ores
    econ_radius_sq = builder.econ_radius_sq
    my_pos = builder.state.my_pos
    my_core = builder.my_core
    friendlies: list[tuple[Position, int]] = list((__v for t in builder.state.all_bots.items() if (__v := (t[0], t[1]) if t[1] != builder.state.my_id and (t[0] in builder.state.friendly_bots) else None) is not None))
    best_target: Position | None = None
    min_dist = 9223372036854775807
    for pos in sorted(ore_set):
        if not builder.is_reachable(pos):
            continue
        if pos.distance_squared(my_core) > econ_radius_sq:
            continue
        if not ore_available(builder, pos):
            continue
        d = my_pos.distance_squared(pos)
        if d >= min_dist:
            continue
        match builder.building_kind[builder.idx(pos)]:
            case None | EntityType.ROAD | EntityType.MARKER | EntityType.BARRIER:
                pass
            case EntityType.CONVEYOR | EntityType.ARMOURED_CONVEYOR:
                if not is_inward_guard(builder, pos):
                    continue
            case _:
                continue
        if not claims_by_proximity(my_pos, builder.state.my_id, pos, friendlies):
            continue
        if harvester_would_contaminate(builder, pos):
            continue
        if (harvester_feed_cardinal(builder, pos) is None):
            continue
        min_dist = d
        best_target = pos
    return best_target
_UPSTREAM_MAX_NODES: Final[int] = 80
_DOWNSTREAM_MAX_NODES: Final[int] = 80

def upstream_tree(builder, start):
    """
    BFS backwards via `in_edges` — all friendly transport tiles whose
    output structurally reaches `start`.
    """
    visited: set[Position] = set()
    visited.add(start)
    queue: list[Position] = [start]
    while (pos := (queue.pop() if queue else None)) is not None:
        if len(visited) >= 80:
            break
        for u in builder.in_edges[int(pos.y) * 50 + int(pos.x)]:
            if (u in visited):
                continue
            visited.add(u)
            queue.append(u)
    return visited

def downstream_tree(builder, start):
    """BFS forwards via `out_edges`."""
    visited: set[Position] = set()
    visited.add(start)
    queue: list[Position] = [start]
    while (pos := (queue.pop() if queue else None)) is not None:
        if len(visited) >= 80:
            break
        for out in builder.out_edges[int(pos.y) * 50 + int(pos.x)]:
            if (out in visited):
                continue
            visited.add(out)
            queue.append(out)
    return visited

def chain_has_foundry(builder, start):
    my_team = builder.state.my_team
    for pos in upstream_tree(builder, start):
        if builder.building_kind[builder.idx(pos)] == EntityType.FOUNDRY and builder.building_team[builder.idx(pos)] == my_team:
            return True
    for pos in downstream_tree(builder, start):
        if builder.building_kind[builder.idx(pos)] == EntityType.FOUNDRY and builder.building_team[builder.idx(pos)] == my_team:
            return True
    return False

def ax_feeds_target(builder, target):
    for feeder in builder.in_edges[int(target.y) * 50 + int(target.x)]:
        if (feeder in builder.ax_upstream):
            return True
    for d in DIR4:
        n = target.add(d)
        if not builder.in_bounds(n):
            continue
        ni = int(n.y) * 50 + int(n.x)
        if builder.building_kind[ni] == EntityType.HARVESTER and builder.building_team[ni] == builder.state.my_team and builder.env[ni] == Environment.ORE_AXIONITE:
            return True
    return False

def tile_has_ax_flow(builder, pos):
    for r, _rid in builder.flow_history[int(pos.y) * 50 + int(pos.x)]:
        if ((r is not None) and (r == ResourceType.RAW_AXIONITE or r == ResourceType.REFINED_AXIONITE)):
            return True
    return False

def rotate_right(d):
    match d:
        case Direction.NORTH:
            return Direction.NORTHEAST
        case Direction.NORTHEAST:
            return Direction.EAST
        case Direction.EAST:
            return Direction.SOUTHEAST
        case Direction.SOUTHEAST:
            return Direction.SOUTH
        case Direction.SOUTH:
            return Direction.SOUTHWEST
        case Direction.SOUTHWEST:
            return Direction.WEST
        case Direction.WEST:
            return Direction.NORTHWEST
        case Direction.NORTHWEST:
            return Direction.NORTH
        case Direction.CENTRE:
            return Direction.CENTRE

def rotate_left(d):
    match d:
        case Direction.NORTH:
            return Direction.NORTHWEST
        case Direction.NORTHEAST:
            return Direction.NORTH
        case Direction.EAST:
            return Direction.NORTHEAST
        case Direction.SOUTHEAST:
            return Direction.EAST
        case Direction.SOUTH:
            return Direction.SOUTHEAST
        case Direction.SOUTHWEST:
            return Direction.SOUTH
        case Direction.WEST:
            return Direction.SOUTHWEST
        case Direction.NORTHWEST:
            return Direction.WEST
        case Direction.CENTRE:
            return Direction.CENTRE
