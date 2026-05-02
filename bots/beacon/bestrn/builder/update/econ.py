from __future__ import annotations

from typing import Final

from cambc import EntityType, Environment, Position, ResourceType
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cambc import Controller, ControllerApi
if TYPE_CHECKING:
    from builder import Builder
from builder.algorithms.reachability import find
from builder.helpers import ax_feeds_target, can_afford_ore_claim, harvester_would_contaminate, is_inward_guard, ore_available, pick_ax_ore_target, pick_offensive_ti_ore_target, pick_ore_target
from util.constants import FLOW_HISTORY_LEN, INF, MAX_WIDTH, base_cost
from util.debug import Scope
from util.debug import debug as log
from util.directions import DIR4
from util.metrics import chebyshev, claims_by_proximity
from util.visualiser import auto_wrap_position

def can_place_junction(builder, pos):
    my_team = builder.state.my_team
    kind = builder.building_kind[builder.idx(pos)]
    team = builder.building_team[builder.idx(pos)]
    match kind:
        case None:
            ok = True
        case EntityType.CONVEYOR | EntityType.ROAD:
            ok = team == my_team
        case _:
            ok = False
    if not ok:
        return False
    conv = builder.get_in_edges(pos)
    conv_adj: list[Position] = list((c for c in conv if c.distance_squared(pos) <= 2))
    if len(conv_adj) >= 2 or (not conv):
        return False
    buildable_count = 0
    for d in DIR4:
        new_pos = pos.add(d)
        if not builder.in_bounds(new_pos):
            continue
        if builder.env[builder.idx(new_pos)] != Environment.EMPTY:
            continue
        nk = builder.building_kind[builder.idx(new_pos)]
        nt = builder.building_team[builder.idx(new_pos)]
        match nk:
            case None:
                buildable_count += 1
            case EntityType.CONVEYOR | EntityType.BRIDGE | EntityType.SPLITTER:
                pass
            case _ if nt == my_team:
                buildable_count += 1
            case _:
                pass
    return buildable_count >= 1

def update_map_econ(builder, ct):
    prev_unconn = set(builder.adjacent_to_unconnected_harvester)
    builder.adjacent_to_unconnected_harvester = set((p for p in builder.adjacent_to_unconnected_harvester if not ct.is_in_vision(p)))
    builder.adjacent_to_harvester = set((p for p in builder.adjacent_to_harvester if not ct.is_in_vision(p)))
    nearby = list(builder.state.nearby_tiles)
    my_team = builder.state.my_team
    for pos in nearby:
        pos = pos
        if builder.building_kind[builder.idx(pos)] != EntityType.HARVESTER:
            continue
        adjacent_conveyor = False
        for d in DIR4:
            n = pos.add(d)
            if not builder.in_bounds(n):
                continue
            ni = builder.idx(n)
            nk = builder.building_kind[ni]
            nt = builder.building_team[ni]
            match nk:
                case EntityType.CONVEYOR | EntityType.ARMOURED_CONVEYOR if nt == my_team:
                    out = (builder.out_edges[ni][0] if builder.out_edges[ni] else None)
                    if out is not None and (out != pos):
                        if not (builder.in_bounds(out) and builder.building_kind[builder.idx(out)] == EntityType.HARVESTER):
                            adjacent_conveyor = True
                            break
                case EntityType.BRIDGE | EntityType.SPLITTER | EntityType.FOUNDRY | EntityType.CORE | EntityType.GUNNER | EntityType.SENTINEL | EntityType.BREACH | EntityType.LAUNCHER if nt == my_team:
                    adjacent_conveyor = True
                    break
                case _:
                    pass
        if not adjacent_conveyor:
            for d in DIR4:
                n = pos.add(d)
                if builder.in_bounds(n):
                    builder.adjacent_to_unconnected_harvester.add(n)
        for d in DIR4:
            n = pos.add(d)
            if builder.in_bounds(n):
                builder.adjacent_to_harvester.add(n)
    for pos in nearby:
        i = int(pos.y) * 50 + int(pos.x)
        if builder.cost_grid[i] != 1000000:
            if (pos in builder.adjacent_to_enemy_launcher):
                builder.cost_grid[i] += 20
            if (pos in builder.enemy_turret_ray_tiles):
                builder.cost_grid[i] += 15
    changed: list[Position] = list(prev_unconn.symmetric_difference(builder.adjacent_to_unconnected_harvester))
    changed.sort(key=lambda p: (p.y, p.x))
    for p in changed:
        builder._check_dangling(p, "unconn_flip")

def update_unreachable_dangling(builder):
    """
    Migrate tiles between `dangling_set` and `unreachable_dangling`
    according to map-level reachability (incremental UF, not BFS).
    """
    my_i = int(builder.state.my_pos.y) * 50 + int(builder.state.my_pos.x)
    if builder.reach_parent[my_i] == -1:
        return
    my_root = find(builder.reach_parent, int(my_i))
    dangling: list[Position] = list(builder.dangling_set)
    dangling.sort(key=lambda p: (p.y, p.x))
    for t in dangling:
        i = int(t.y) * 50 + int(t.x)
        if builder.reach_parent[i] == -1 or find(builder.reach_parent, int(i)) != my_root:
            args = {}
            args[str("t")] = auto_wrap_position(t)
            log("DANGLING discard(unreachable) t={t}", args)
            builder.dangling_set.discard(t)
            builder.unreachable_dangling.add(t)
    unreach: list[Position] = list(builder.unreachable_dangling)
    unreach.sort(key=lambda p: (p.y, p.x))
    for t in unreach:
        i = int(t.y) * 50 + int(t.x)
        if builder.reach_parent[i] != -1 and find(builder.reach_parent, int(i)) == my_root:
            args = {}
            args[str("t")] = auto_wrap_position(t)
            log("DANGLING add(reachable-migrate) t={t}", args)
            builder.unreachable_dangling.discard(t)
            builder.dangling_set.add(t)

def update_dangling(builder):
    """
    Refresh the cached `dangling_output` once per turn — no
    stickiness. Tasks (`extend_chain_*`, `push_extend`) and update
    helpers (`update_foundry_target`, `update_ti_sink`) read the cached
    value rather than re-running the selection.
    """
    result = pick_dangling_output(builder, None)
    builder.dangling_output = result

def flood_forward(out_edges, seeds):
    """
    Pick the dangling end this builder should work on right now —
    no commitment, recomputed on demand. The proximity gate
    (`claims_by_proximity`) ensures at most one builder claims each end
    even though every builder runs the same selection independently.

    If `ct` is provided, candidates are filtered to currently-visible
    tiles (used by `extend_chain_in_range`). Without `ct`, all dangling
    tiles are considered.
    Forward flood from seed tiles through `out_edges`. Helper for the
    debug-only `check_invariants` oracle. Pulled out of an inline closure
    so the translator's single-expr-lambda restriction doesn't apply.
    """
    target: set[Position] = set()
    stack: list[Position] = []
    for s in seeds:
        if (s in target):
            continue
        if (not out_edges[int(s.y) * 50 + int(s.x)]):
            continue
        target.add(s)
        stack.append(s)
    while (p := (stack.pop() if stack else None)) is not None:
        for out in out_edges[int(p.y) * 50 + int(p.x)]:
            if (out in target):
                continue
            target.add(out)
            stack.append(out)
    return target

def chebyshev_to_nearest_core_edge(builder, pos):
    """
    Chebyshev distance from `pos` to its nearest `core_edge` (or `my_core`
    if `core_edges` is empty — shouldn't happen post-init).
    """
    best_d = 1000000
    for e in builder.core_edges:
        d = chebyshev(pos, e)
        if d < best_d:
            best_d = d
    return chebyshev(pos, builder.my_core) if best_d == 1000000 else best_d

def pick_dangling_output(builder, ct):
    friendly: list[tuple[Position, int]] = list(((t[0], t[1]) for t in (t for t in builder.state.all_bots.items() if t[1] != builder.state.my_id and (t[0] in builder.state.friendly_bots))))
    en_core = builder.en_core_guess if (builder.symmetry is not None) else None
    best: Position | None = None
    best_score: tuple[int, int, int, int] = (1 << 30, 1 << 30, 1 << 30, 1 << 30)
    dangling_iter: list[Position] = list(builder.dangling_set)
    for pos in dangling_iter:
        c = ct
        if c is not None and (not c.is_in_vision(pos)):
            continue
        if not claims_by_proximity(builder.state.my_pos, builder.state.my_id, pos, friendly):
            continue
        my_d = chebyshev(builder.state.my_pos, pos)
        match en_core:
            case ec if ec is not None and (pos.distance_squared(ec) < pos.distance_squared(builder.my_core)):
                chain_d = chebyshev(pos, ec)
            case _:
                chain_d = chebyshev_to_nearest_core_edge(builder, pos)
        score = (my_d, chain_d, pos.y, pos.x)
        if score < best_score:
            best_score = score
            best = pos
    return best

def update_ti_ore_target(builder):
    candidate_ore = pick_ore_target(builder)
    needs_pick = (builder.ore_target is None) or (builder.ore_target is not None and (lambda t: not ore_available(builder, t))(builder.ore_target)) or (builder.ore_target is not None and (lambda t: not builder.is_reachable(t))(builder.ore_target)) or (builder.ore_target is not None and (lambda t: harvester_would_contaminate(builder, t))(builder.ore_target)) or (candidate_ore is not None) and candidate_ore.distance_squared(builder.state.my_pos) <= 2 and (builder.ore_target is not None and (lambda t: t.distance_squared(builder.state.my_pos) > 2)(builder.ore_target))
    if needs_pick:
        sink = (builder.ti_sink if builder.ti_sink is not None else builder.my_core)
        c = candidate_ore
        if c is not None and (not can_afford_ore_claim(builder, c, sink)):
            candidate_ore = None
        builder.ore_target = candidate_ore

def update_offensive_ore_target(builder):
    """
    Enemy-side Ti ore claim. Same re-evaluation semantics as
    `update_ore_target`: keep the current pick if still valid and not
    trivially beaten by a much-closer alternative.
    """
    candidate = pick_offensive_ti_ore_target(builder)
    needs_pick = (builder.offensive_ore_target is None) or (builder.offensive_ore_target is not None and (lambda t: not ore_available(builder, t))(builder.offensive_ore_target)) or (builder.offensive_ore_target is not None and (lambda t: not builder.is_reachable(t))(builder.offensive_ore_target)) or (builder.offensive_ore_target is not None and (lambda t: harvester_would_contaminate(builder, t))(builder.offensive_ore_target)) or (candidate is not None) and candidate.distance_squared(builder.state.my_pos) <= 2 and (builder.offensive_ore_target is not None and (lambda t: t.distance_squared(builder.state.my_pos) > 2)(builder.offensive_ore_target))
    if needs_pick:
        sink = builder.en_core_guess if (builder.symmetry is not None) else None
        c = candidate
        s = sink
        if c is not None and s is not None and (not can_afford_ore_claim(builder, c, s)):
            candidate = None
        builder.offensive_ore_target = candidate
_AX_HARVESTER_ROUND_GATE: Final[int] = 500
"""Derived from Blue Dragon / Kessoku Band: no Ax harvester before turn 500."""

def _is_zero_length_foundry_spot(builder, pos):
    """
    Pure friendly `BuildingConveyor` with exactly one cardinal friendly
    Ax harvester. This is the designated foundry spot for a zero-length
    Ax chain — `harvester_would_contaminate` has already admitted the Ax
    harvester under the same geometric rule.
    """
    i = int(pos.y) * 50 + int(pos.x)
    if builder.building_kind[i] != EntityType.CONVEYOR:
        return False
    if builder.building_team[i] != builder.state.my_team:
        return False
    ax_harv_count = 0
    for d in DIR4:
        n = pos.add(d)
        if not builder.in_bounds(n):
            continue
        ni = int(n.y) * 50 + int(n.x)
        if builder.building_kind[ni] == EntityType.HARVESTER and builder.building_team[ni] == builder.state.my_team and builder.env[ni] == Environment.ORE_AXIONITE:
            ax_harv_count += 1
            if ax_harv_count > 1:
                return False
    return ax_harv_count == 1

def _foundry_local_ok(builder, pos):
    """
    Foundry candidate: friendly Ti conveyor that reaches the core, is NOT
    on a chain already feeding a foundry, and is NOT structurally downstream
    of any known Ax harvester.
    """
    i = int(pos.y) * 50 + int(pos.x)
    kind = builder.building_kind[i]
    team = builder.building_team[i]
    is_conv = ((kind is not None) and (kind == EntityType.CONVEYOR or kind == EntityType.ARMOURED_CONVEYOR))
    if not is_conv:
        return False
    if team != builder.state.my_team:
        return False
    if (pos in builder.upstream_of_dangling):
        return False
    if (pos in builder.reaches_foundry):
        return False
    is_foundry_spot = _is_zero_length_foundry_spot(builder, pos)
    if not is_foundry_spot:
        if (pos in builder.ax_harvester_adjacent):
            return False
        if (pos in builder.ax_upstream):
            return False
    hist = builder.flow_history[i]
    saw_ti = False
    has_ax = False
    for r, _rid in hist:
        r = r
        if r is None:
            continue
        match r:
            case ResourceType.RAW_AXIONITE | ResourceType.REFINED_AXIONITE:
                has_ax = True
            case ResourceType.TITANIUM:
                saw_ti = True
    if has_ax and not is_foundry_spot and not ax_feeds_target(builder, pos):
        return False
    return saw_ti

def _tile_volume(builder, pos):
    """Occupancy count: non-None entries in the tile's `flow_history`."""
    return sum(1 for _ in (t for t in builder.flow_history[int(pos.y) * 50 + int(pos.x)] if (t[0] is not None)))

def _pure_ax_merge_ok(builder, pos):
    """`pos` is a pure-Ax transport tile worth merging a new Ax chain into."""
    if _tile_volume(builder, pos) >= 8:
        return False
    return (pos in builder.ax_upstream) and not (pos in builder.ti_upstream) and not (pos in builder.upstream_of_dangling)
_FOUNDRY_REUSE_THRESHOLD: Final[int] = 10
"""
Manhattan-distance threshold: a pre-existing foundry or Ax chain is only
preferred over building a new foundry on a nearby Ti conveyor if the pre-
existing option isn't more than this many tiles further. Otherwise creating
a new foundry locally is the better choice.
"""

def _manhattan(a, b):
    return abs(a.x - b.x) + abs(a.y - b.y)

def _detect_congested_junctions(builder):
    """
    Find junctions (multi-feeder tiles) where the feeders' total
    observed inflow exceeds the junction's `FLOW_HISTORY_LEN` window — i.e.
    stacks arrive faster than a single-tile pass-through can forward.
    """
    result: list[Position] = []
    for t in builder.nearby_buildings:
        i = int(t.y) * 50 + int(t.x)
        if not ((builder.building_kind[i] is not None) and (builder.building_kind[i] == EntityType.CONVEYOR or builder.building_kind[i] == EntityType.ARMOURED_CONVEYOR or builder.building_kind[i] == EntityType.BRIDGE)):
            continue
        feeders = builder.in_edges[i]
        if len(feeders) < 2:
            continue
        hist = builder.flow_history[i]
        if len(hist) < 8:
            continue
        if sum(1 for _ in (t for t in hist if (t[0] is not None))) < 8:
            continue
        total: int = 0
        complete = True
        for f in feeders:
            fh = builder.flow_history[int(f.y) * 50 + int(f.x)]
            if len(fh) < 8:
                complete = False
                break
            total += sum(1 for _ in (t for t in fh if (t[0] is not None)))
        if complete and total > 8:
            result.append(t)
    return result

def _detect_saturated_tiles(builder):
    """Transport tiles running empirically at full throughput."""
    result: list[Position] = []
    for t in builder.nearby_buildings:
        i = int(t.y) * 50 + int(t.x)
        if not ((builder.building_kind[i] is not None) and (builder.building_kind[i] == EntityType.CONVEYOR or builder.building_kind[i] == EntityType.ARMOURED_CONVEYOR or builder.building_kind[i] == EntityType.BRIDGE)):
            continue
        hist = builder.flow_history[i]
        if len(hist) < 8:
            continue
        if sum(1 for _ in (t for t in hist if (t[0] is not None))) >= 8:
            result.append(t)
    return result

def update_economy_reachability(builder):
    """
    Per-turn backward flood over the structural transport graph.
    Marks `reaches_core`, `reaches_foundry`, `upstream_of_dangling`,
    `upstream_of_congestion` (backward over `in_edges`).
    """
    builder.reaches_core = set()
    builder.reaches_foundry = set()
    builder.upstream_of_dangling = set()
    builder.upstream_of_congestion = set()
    my_core = builder.my_core
    roots: list[Position] = [my_core]
    roots.extend(builder.core_edges)
    flood_back(builder.in_edges, roots, builder.reaches_core)
    if not (not builder.my_foundries):
        roots: list[Position] = list(builder.my_foundries)
        flood_back(builder.in_edges, roots, builder.reaches_foundry)
    dangling_roots: list[Position] = list((p for p in builder.dangling_set if not (not builder.in_edges[int(p.y) * 50 + int(p.x)])))
    flood_back(builder.in_edges, dangling_roots, builder.upstream_of_dangling)
    builder.congested_junctions = list(_detect_congested_junctions(builder))
    cong_roots: list[Position] = list(builder.congested_junctions)
    flood_back(builder.in_edges, cong_roots, builder.upstream_of_congestion)

def flood_back(in_edges, roots, target):
    stack: list[Position] = []
    for r in roots:
        if not (r in target):
            target.add(r)
            stack.append(r)
    while (p := (stack.pop() if stack else None)) is not None:
        i = int(p.y) * 50 + int(p.x)
        for u in in_edges[i]:
            if (u in target):
                continue
            target.add(u)
            stack.append(u)

def check_invariants(builder):
    """
    Oracle: recompute the incrementally-maintained sets from scratch
    using the current `in_edges` / `out_edges` / harvester-adjacent state,
    and assert equality with the live values.
    """
    out_edges = builder.out_edges
    in_edges = builder.in_edges
    expected_ti_adj: set[Position] = list((__v for t in enumerate(builder._ti_harv_at) if (__v := Position(x=int(t[0] % 50), y=int(t[0] // 50)) if t[1] > 0 else None) is not None))
    expected_ax_adj: set[Position] = list((__v for t in enumerate(builder._ax_harv_at) if (__v := Position(x=int(t[0] % 50), y=int(t[0] // 50)) if t[1] > 0 else None) is not None))
    if expected_ti_adj != builder.ti_harvester_adjacent:
        args = {}
        missing: list[Position] = list(expected_ti_adj.difference(builder.ti_harvester_adjacent))
        missing.sort()
        extra: list[Position] = list(builder.ti_harvester_adjacent.difference(expected_ti_adj))
        extra.sort()
        args[str("missing")] = f"{missing!r}"
        args[str("extra")] = f"{extra!r}"
        log("INVARIANT_FAIL ti_harvester_adjacent missing={missing} extra={extra}", args)
    if expected_ax_adj != builder.ax_harvester_adjacent:
        args = {}
        missing: list[Position] = list(expected_ax_adj.difference(builder.ax_harvester_adjacent))
        missing.sort()
        extra: list[Position] = list(builder.ax_harvester_adjacent.difference(expected_ax_adj))
        extra.sort()
        args[str("missing")] = f"{missing!r}"
        args[str("extra")] = f"{extra!r}"
        log("INVARIANT_FAIL ax_harvester_adjacent missing={missing} extra={extra}", args)
    oracle_ti = flood_forward(out_edges, builder.ti_harvester_adjacent)
    oracle_ax = flood_forward(out_edges, builder.ax_harvester_adjacent)
    if oracle_ti != builder.ti_upstream:
        miss: list[Position] = list(oracle_ti.difference(builder.ti_upstream))
        miss.sort()
        del miss[8:]
        extra: list[Position] = list(builder.ti_upstream.difference(oracle_ti))
        extra.sort()
        del extra[8:]
        args = {}
        args[str("missing")] = f"{miss!r}"
        args[str("extra")] = f"{extra!r}"
        log("INVARIANT_FAIL ti_upstream missing={missing} extra={extra}", args)
        for t in itertools.islice(miss, 4):
            i = int(t.y) * 50 + int(t.x)
            feeders: list[tuple[Position, bool, bool]] = list(((f, (f in builder.ti_upstream), (f in oracle_ti)) for f in in_edges[i]))
            args = {}
            args[str("t")] = f"{t!r}"
            args[str("ti_in_count")] = builder._ti_in_count[i]
            args[str("ti_harv_at")] = builder._ti_harv_at[i]
            args[str("feeders")] = f"{feeders!r}"
            log("  miss t={t} ti_in_count={ti_in_count} ti_harv_at={ti_harv_at} feeders={feeders}", args)
    if oracle_ax != builder.ax_upstream:
        miss: list[Position] = list(oracle_ax.difference(builder.ax_upstream))
        miss.sort()
        del miss[8:]
        extra: list[Position] = list(builder.ax_upstream.difference(oracle_ax))
        extra.sort()
        del extra[8:]
        args = {}
        args[str("missing")] = f"{miss!r}"
        args[str("extra")] = f"{extra!r}"
        log("INVARIANT_FAIL ax_upstream missing={missing} extra={extra}", args)
        for t in itertools.islice(miss, 4):
            i = int(t.y) * 50 + int(t.x)
            feeders: list[tuple[Position, bool, bool]] = list(((f, (f in builder.ax_upstream), (f in oracle_ax)) for f in in_edges[i]))
            args = {}
            args[str("t")] = f"{t!r}"
            args[str("ax_in_count")] = builder._ax_in_count[i]
            args[str("ax_harv_at")] = builder._ax_harv_at[i]
            args[str("feeders")] = f"{feeders!r}"
            log("  miss t={t} ax_in_count={ax_in_count} ax_harv_at={ax_harv_at} feeders={feeders}", args)
    for i in range(0, len(in_edges)):
        if (not in_edges[i]):
            if builder._ti_in_count[i] != 0 or builder._ax_in_count[i] != 0:
                t = Position(x=int(i % 50), y=int(i // 50))
                args = {}
                args[str("t")] = f"{t!r}"
                args[str("ti")] = builder._ti_in_count[i]
                args[str("ax")] = builder._ax_in_count[i]
                log("INVARIANT_FAIL in_count nonzero with empty in_edges t={t} ti={ti} ax={ax}", args)
            continue
        ti_expected = int(sum(1 for _ in (f for f in in_edges[i] if (f in builder.ti_upstream))))
        ax_expected = int(sum(1 for _ in (f for f in in_edges[i] if (f in builder.ax_upstream))))
        if ti_expected != builder._ti_in_count[i]:
            t = Position(x=int(i % 50), y=int(i // 50))
            args = {}
            args[str("t")] = f"{t!r}"
            args[str("have")] = builder._ti_in_count[i]
            args[str("expected")] = ti_expected
            args[str("in_edges")] = f"{in_edges[i]!r}"
            log("INVARIANT_FAIL ti_in_count drift t={t} have={have} expected={expected} in_edges={in_edges}", args)
        if ax_expected != builder._ax_in_count[i]:
            t = Position(x=int(i % 50), y=int(i // 50))
            args = {}
            args[str("t")] = f"{t!r}"
            args[str("have")] = builder._ax_in_count[i]
            args[str("expected")] = ax_expected
            args[str("in_edges")] = f"{in_edges[i]!r}"
            log("INVARIANT_FAIL ax_in_count drift t={t} have={have} expected={expected} in_edges={in_edges}", args)

def _feeder_flow_kind(builder, f):
    """
    Classify a feeder tile by its observed flow-history: 'ti' if only
    Ti stacks seen, 'ax' if only Ax stacks seen, None if no flow observed
    or mixed.
    """
    i = int(f.y) * 50 + int(f.x)
    seen_ti = False
    seen_ax = False
    for r, _rid in builder.flow_history[i]:
        r = r
        if r is None:
            continue
        match r:
            case ResourceType.TITANIUM:
                seen_ti = True
            case ResourceType.RAW_AXIONITE | ResourceType.REFINED_AXIONITE:
                seen_ax = True
    if seen_ti and not seen_ax:
        return "ti"
    if seen_ax and not seen_ti:
        return "ax"
    return None

def _is_junction(builder, pos):
    """
    True iff `pos` is a viable foundry site: a friendly conveyor or
    armoured conveyor with >= 1 feeder delivering Ti only AND >= 1 feeder
    delivering Ax only.
    """
    i = int(pos.y) * 50 + int(pos.x)
    kind = builder.building_kind[i]
    team = builder.building_team[i]
    is_conv = ((kind is not None) and (kind == EntityType.CONVEYOR or kind == EntityType.ARMOURED_CONVEYOR))
    if not is_conv:
        return False
    if team != builder.state.my_team:
        return False
    feeders = builder.in_edges[i]
    if len(feeders) < 2:
        return False
    has_ti = False
    has_ax = False
    for f in feeders:
        in_ti = (f in builder.ti_upstream)
        in_ax = (f in builder.ax_upstream)
        if in_ti and not in_ax:
            has_ti = True
        elif in_ax and not in_ti:
            has_ax = True
    if has_ti and has_ax:
        return True
    for f in feeders:
        match _feeder_flow_kind(builder, f):
            case "ti":
                has_ti = True
            case "ax":
                has_ax = True
            case _:
                pass
    return has_ti and has_ax

def update_junctions(builder):
    """Derive `self.junctions` from `is_multi_input` using `_is_junction`."""
    builder.junctions.clear()
    candidates: list[Position] = list(builder.is_multi_input)
    for pos in candidates:
        if _is_junction(builder, pos):
            builder.junctions.add(pos)

def update_foundry_target(builder):
    """Re-derive `ax_sink` every turn from three option classes."""
    if (builder.ax_ore_target is None) and (not builder.ax_harvester_adjacent):
        builder.ax_sink = None
        builder.foundry_target = None
        return
    origin = (builder.dangling_output if builder.dangling_output is not None else builder.state.my_pos)
    junction_best: Position | None = None
    junction_d: int = 1 << 30
    ax_chain_best: Position | None = None
    ax_chain_d: int = 1 << 30
    foundry_best: Position | None = None
    foundry_d: int = 1 << 30
    ti_cand_best: Position | None = None
    ti_cand_d: int = 1 << 30
    with Scope.new_timed("junctions") as _g:
        for pos in builder.junctions:
            key = (_manhattan(origin, pos), pos.y, pos.x)
            best_key = ((lambda p: (junction_d, p.y, p.x))(junction_best) if junction_best is not None else None)
            if (best_key is None or (lambda bk: key < bk)(best_key)):
                junction_d = key[0]
                junction_best = pos
    with Scope.new_timed("foundries") as _g:
        for pos in builder.my_foundries:
            key = (_manhattan(origin, pos), pos.y, pos.x)
            best_key = ((lambda p: (foundry_d, p.y, p.x))(foundry_best) if foundry_best is not None else None)
            if (best_key is None or (lambda bk: key < bk)(best_key)):
                foundry_d = key[0]
                foundry_best = pos
    with Scope.new_timed("ax_upstream") as _g:
        for pos in builder.ax_upstream:
            if not _pure_ax_merge_ok(builder, pos):
                continue
            key = (_manhattan(origin, pos), pos.y, pos.x)
            best_key = ((lambda p: (ax_chain_d, p.y, p.x))(ax_chain_best) if ax_chain_best is not None else None)
            if (best_key is None or (lambda bk: key < bk)(best_key)):
                ax_chain_d = key[0]
                ax_chain_best = pos
    with Scope.new_timed("ti_candidates") as _g:
        for pos in builder.reaches_core.difference(builder.reaches_foundry):
            if not _foundry_local_ok(builder, pos):
                continue
            key = (_manhattan(origin, pos), pos.y, pos.x)
            best_key = ((lambda p: (ti_cand_d, p.y, p.x))(ti_cand_best) if ti_cand_best is not None else None)
            if (best_key is None or (lambda bk: key < bk)(best_key)):
                ti_cand_d = key[0]
                ti_cand_best = pos
    options: list[tuple[int, Position, str]] = []
    p = junction_best
    if p is not None:
        options.append((junction_d, p, "junction"))
    p = ax_chain_best
    if p is not None:
        options.append((ax_chain_d, p, "ax_chain"))
    p = foundry_best
    if p is not None:
        options.append((foundry_d, p, "foundry"))
    p = ti_cand_best
    if p is not None:
        options.append((ti_cand_d + 10, p, "ti_candidate"))
    if (not options):
        builder.ax_sink = None
    else:
        options.sort(key=lambda o: o[0])
        builder.ax_sink = options[0][1]
    ft = builder.foundry_target
    ft = ft
    if ft is not None:
        fi = int(ft.y) * 50 + int(ft.x)
        is_transport = ((builder.building_kind[fi] is not None) and (builder.building_kind[fi] == EntityType.CONVEYOR or builder.building_kind[fi] == EntityType.ARMOURED_CONVEYOR)) and builder.building_team[fi] == builder.state.my_team
        still_valid_junction = is_transport and (ft in builder.junctions)
        still_valid_kind_c = is_transport and (ft in builder.reaches_core) and not (ft in builder.reaches_foundry)
        if not (still_valid_junction or still_valid_kind_c):
            builder.foundry_target = None
    chosen = builder.ax_sink
    if ((builder.foundry_target is None)) and chosen is not None and ((chosen in builder.junctions) or _foundry_local_ok(builder, chosen) and ax_feeds_target(builder, chosen)):
        builder.foundry_target = chosen

def _ti_sink_ok(builder, pos):
    """Empirical Ti-sink candidate."""
    i = int(pos.y) * 50 + int(pos.x)
    kind = builder.building_kind[i]
    team = builder.building_team[i]
    is_conv = ((kind is not None) and (kind == EntityType.CONVEYOR or kind == EntityType.ARMOURED_CONVEYOR))
    if not is_conv:
        return False
    if team != builder.state.my_team:
        return False
    if is_inward_guard(builder, pos):
        return False
    if (pos in builder.upstream_of_dangling) and (pos in builder.ti_upstream):
        return False
    if (pos in builder.upstream_of_congestion):
        return False
    if (pos in builder.ax_harvester_adjacent):
        return False
    if _tile_volume(builder, pos) >= 8:
        return False
    hist = builder.flow_history[i]
    saw_ti = False
    for r, _rid in hist:
        match r:
            case ResourceType.RAW_AXIONITE | ResourceType.REFINED_AXIONITE:
                return False
            case ResourceType.TITANIUM:
                saw_ti = True
            case _:
                pass
    return saw_ti

def _near_core_saving_threshold(builder):
    """
    Tier-1 (branch merge) requires this many Manhattan tiles saved vs.
    routing to core.
    """
    r = builder.state.round
    return 1 + r // 20 if r < 100 else 6 + (r - 100) // 100

def update_ti_sink(builder):
    """Pick where new Ti chains should terminate. Three-tier preference."""
    anchor = (builder.dangling_output if builder.dangling_output is not None else builder.state.my_pos)
    c = builder.my_core
    d_builder_to_core = abs(builder.state.my_pos.x - c.x) + abs(builder.state.my_pos.y - c.y)
    saving_threshold = _near_core_saving_threshold(builder)
    tier1_best: Position | None = None
    tier1_d: int = 1 << 30
    tier3_best: Position | None = None
    tier3_d: int = 1 << 30
    nearby = list(builder.state.nearby_tiles)
    for pos in nearby:
        if not _ti_sink_ok(builder, pos):
            continue
        d_anchor_sq = anchor.distance_squared(pos)
        d_builder_to_cand = abs(builder.state.my_pos.x - pos.x) + abs(builder.state.my_pos.y - pos.y)
        saving = d_builder_to_core - d_builder_to_cand
        if saving <= saving_threshold:
            if d_anchor_sq < tier3_d:
                tier3_d = d_anchor_sq
                tier3_best = pos
        elif d_anchor_sq < tier1_d:
            tier1_d = d_anchor_sq
            tier1_best = pos
    tier2_best: Position | None = None
    tier2_d: int = 1 << 30
    for edge in builder.core_edges:
        d = anchor.distance_squared(edge)
        if d < tier2_d:
            tier2_d = d
            tier2_best = edge
    best, best_d, tier = (p, tier1_d, 1) if ((p := tier1_best) is not None) else ((p, tier2_d, 2) if ((p := tier2_best) is not None) else (tier3_best, tier3_d, 3))
    if best != builder.ti_sink:
        args = {}
        args[str("from")] = f"{builder.ti_sink!r}"
        args[str("to")] = f"{best!r}"
        args[str("tier")] = tier
        args[str("anchor")] = f"{anchor!r}"
        args[str("dist_sq")] = best_d
        log("update_ti_sink: ti_sink changed from {from} to {to} (tier {tier}, anchor={anchor}, dist_sq={dist_sq})", args)
    builder.ti_sink = best

def update_ax_ore_target(builder):
    """Pick the nearest unclaimed Ax-ore tile, gated on round AND Ti buffer."""
    if builder.state.round < 500:
        builder.ax_ore_target = None
        return
    __opt_tuple = base_cost(EntityType.HARVESTER)
    if __opt_tuple is None:
        builder.ax_ore_target = None
        return
    ti_base, _ax_base = __opt_tuple
    if builder.state.ti < 2 * int(float(ti_base) * builder.state.scale):
        builder.ax_ore_target = None
        return
    candidate = pick_ax_ore_target(builder)
    needs_pick = (builder.ax_ore_target is None) or (builder.ax_ore_target is not None and (lambda t: not ore_available(builder, t))(builder.ax_ore_target)) or (builder.ax_ore_target is not None and (lambda t: not builder.is_reachable(t))(builder.ax_ore_target)) or (builder.ax_ore_target is not None and (lambda t: harvester_would_contaminate(builder, t))(builder.ax_ore_target)) or (candidate is not None) and candidate.distance_squared(builder.state.my_pos) <= 2 and (builder.ax_ore_target is not None and (lambda t: t.distance_squared(builder.state.my_pos) > 2)(builder.ax_ore_target))
    if needs_pick:
        sink = (builder.ax_sink if builder.ax_sink is not None else builder.my_core)
        c = candidate
        if c is not None and (not can_afford_ore_claim(builder, c, sink)):
            candidate = None
        builder.ax_ore_target = candidate
