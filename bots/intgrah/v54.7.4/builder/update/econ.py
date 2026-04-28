from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingArmouredConveyor,
    BuildingBreach,
    BuildingBridge,
    BuildingConveyor,
    BuildingCore,
    BuildingFoundry,
    BuildingGunner,
    BuildingHarvester,
    BuildingLauncher,
    BuildingRoad,
    BuildingSentinel,
    BuildingSplitter,
)
from cambc import Controller, EntityType, Environment, Position, ResourceType
from util.constants import BASE_COST, FLOW_HISTORY_LEN, INF, MAX_WIDTH
from util.debug import Scope
from util.debug import debug as log
from util.directions import DIR4
from util.metrics import chebyshev, claims_by_proximity

from builder.algorithms.reachability import find
from builder.helpers import (
    ax_feeds_target,
    harvester_would_contaminate,
    ore_available,
    pick_ax_ore_target,
    pick_offensive_ti_ore_target,
    pick_ore_target,
)

if TYPE_CHECKING:
    from builder import Builder


def can_place_junction(self: Builder, pos: Position) -> bool:
    match self.get_building(pos):
        case (
            None | BuildingConveyor(team=self.my_team) | BuildingRoad(team=self.my_team)
        ):
            pass
        case _:
            return False

    conv = self.get_in_edges(pos)
    conv_adj = [c for c in conv if c.distance_squared(pos) <= 2]
    if len(conv_adj) >= 2 or len(conv) == 0:
        return False
    buildable_count = 0
    for d in DIR4:
        new_pos = pos.add(d)
        if not self.in_bounds(new_pos):
            continue
        if self.get_env(new_pos) != Environment.EMPTY:
            continue
        match self.get_building(new_pos):
            case None:
                buildable_count += 1
            case BuildingConveyor() | BuildingBridge() | BuildingSplitter():
                pass
            case b if b.team == self.my_team:
                buildable_count += 1

    return buildable_count >= 1


def update_map_econ(self: Builder, ct: Controller) -> None:
    prev_unconn = self.adjacent_to_unconnected_harvester
    self.adjacent_to_unconnected_harvester = {
        p for p in self.adjacent_to_unconnected_harvester if not ct.is_in_vision(p)
    }
    self.adjacent_to_harvester = {
        p for p in self.adjacent_to_harvester if not ct.is_in_vision(p)
    }
    self.ti_harvester_adjacent = {
        p for p in self.ti_harvester_adjacent if not ct.is_in_vision(p)
    }
    self.ax_harvester_adjacent = {
        p for p in self.ax_harvester_adjacent if not ct.is_in_vision(p)
    }
    # Pass 1: populate the harvester-adjacent sets and the
    # adjacent_to_unconnected_harvester set based on every harvester in
    # current vision. Must finish before pass 2 so iteration order doesn't
    # cause a neighbour tile to miss its leakage mask.
    for pos in self.nearby_tiles:
        bld = self.get_building(pos)
        if isinstance(bld, BuildingHarvester):
            # A harvester is "connected" if any cardinal neighbour already
            # consumes its output: a friendly conveyor / armoured conveyor
            # / splitter / bridge forwards the flow, and a foundry / core
            # / turret consume directly (no conveyor needed at all).
            adjacent_conveyor = False
            for d in DIR4:
                n = pos.add(d)
                if not self.in_bounds(n):
                    continue
                match self.get_building(n):
                    case (
                        BuildingConveyor(team=self.my_team)
                        | BuildingBridge(team=self.my_team)
                        | BuildingSplitter(team=self.my_team)
                        | BuildingArmouredConveyor(team=self.my_team)
                        | BuildingFoundry(team=self.my_team)
                        | BuildingCore(team=self.my_team)
                        | BuildingGunner(team=self.my_team)
                        | BuildingSentinel(team=self.my_team)
                        | BuildingBreach(team=self.my_team)
                        | BuildingLauncher(team=self.my_team)
                    ):
                        adjacent_conveyor = True
                        break
            if not adjacent_conveyor:
                for d in DIR4:
                    n = pos.add(d)
                    if self.in_bounds(n):
                        self.adjacent_to_unconnected_harvester.add(n)
            is_ax = self.get_env(pos) == Environment.ORE_AXIONITE
            for d in DIR4:
                n = pos.add(d)
                if self.in_bounds(n):
                    self.adjacent_to_harvester.add(n)
                    if is_ax:
                        self.ax_harvester_adjacent.add(n)
                    else:
                        self.ti_harvester_adjacent.add(n)

    # Pass 2: movement cost_grid per-turn penalties for enemy turret rays
    # and launcher adjacency. Leakage and core-routability are now handled
    # by ti_routable / ax_routable + bfs_dist in A*, not cost grids.
    for pos in self.nearby_tiles:
        i = pos.y * MAX_WIDTH + pos.x
        if self.cost_grid[i] is not INF:
            if pos in self.adjacent_to_enemy_launcher:
                self.cost_grid[i] += 20
            if pos in self.enemy_turret_ray_tiles:
                self.cost_grid[i] += 15

    # Reconcile dangling_set with harvester-adjacency changes: any tile
    # that entered or left adjacent_to_unconnected_harvester this turn
    # may have changed its dangling status.
    changed = prev_unconn ^ self.adjacent_to_unconnected_harvester
    for p in changed:
        self._check_dangling(p)


def update_unreachable_dangling(self: Builder) -> None:
    """Migrate tiles between `dangling_set` and `unreachable_dangling`
    according to map-level reachability (incremental UF, not BFS).

    A tile is reachable iff it's been admitted to the union-find AND
    its component is the same as my_pos's component. The check uses
    path-compressing `find`, which doubles as the algorithm's
    convergence work — every consumer query compresses the chains it
    touches.

    Reach is monotonic, so a tile only ever moves from
    `unreachable_dangling` into `dangling_set` (never the other way).
    """
    parent = self.reach_parent
    my_i = self.my_pos.y * MAX_WIDTH + self.my_pos.x
    if parent[my_i] == -1:
        # Builder's own tile not yet admitted (shouldn't happen — the
        # builder is a building observation by virtue of being on the
        # tile — but bail safely if so).
        return
    my_root = find(parent, my_i)
    for t in list(self.dangling_set):
        i = t.y * MAX_WIDTH + t.x
        if parent[i] == -1 or find(parent, i) != my_root:
            self.dangling_set.discard(t)
            self.unreachable_dangling.add(t)
    for t in list(self.unreachable_dangling):
        i = t.y * MAX_WIDTH + t.x
        if parent[i] != -1 and find(parent, i) == my_root:
            self.unreachable_dangling.discard(t)
            self.dangling_set.add(t)


def update_dangling(self: Builder) -> None:
    # Preserve commitment if still in the set, regardless of whether a
    # closer friendly builder has since come into vision.
    if self.dangling_output in self.dangling_set:
        return
    # Eligibility: only candidates for which no visible friendly builder
    # is strictly closer (tiebreak by lower builder id) — ensures exactly
    # one builder claims each dangling end.
    # Ranking among eligible candidates: chain length from the dangling
    # tile to the nearest core_edge (proxy for the sink the existing
    # ti_sink / foundry_target algorithm will pick), tiebroken by the
    # builder's own distance to the tile. This picks the harvester-
    # cardinal on the core-side so the subsequent chain is as short as
    # the geometry allows.
    friendly = [
        (pos, uid)
        for pos, uid in self.all_bots.items()
        if uid != self.my_id and pos in self.friendly_bots
    ]
    # Per-tile bisector: a dangling tile closer (Euclidean) to the enemy
    # core than to ours is an offensive end, so score by distance-to-enemy
    # (push forward). Otherwise score by distance to our core-edge ring
    # (pull back toward our sinks). Needs symmetry to know enemy core; if
    # unknown, default to the classic my-core score for all tiles.
    en_core = self.en_core_guess if self.symmetry is not None else None
    best: Position | None = None
    best_score = (1 << 30, 1 << 30)
    for pos in self.dangling_set:
        if not claims_by_proximity(self.my_pos, self.my_id, pos, friendly):
            continue
        my_d = chebyshev(self.my_pos, pos)
        if en_core is not None and pos.distance_squared(en_core) < pos.distance_squared(
            self.my_core,
        ):
            chain_d = chebyshev(pos, en_core)
        else:
            chain_d = min(
                (chebyshev(pos, e) for e in self.core_edges),
                default=chebyshev(pos, self.my_core) if self.my_core is not None else 0,
            )
        score = (chain_d, my_d)
        if score < best_score:
            best_score = score
            best = pos
    self.dangling_output = best


def update_ore_target(self: Builder) -> None:
    candidate_ore = pick_ore_target(self)
    if (
        not self.ore_target
        or not ore_available(self, self.ore_target)
        or not self.is_reachable(self.ore_target)
        or harvester_would_contaminate(self, self.ore_target)
        or (
            candidate_ore
            and candidate_ore.distance_squared(self.my_pos) <= 2
            and self.ore_target.distance_squared(self.my_pos) > 2
        )
    ):
        self.ore_target = candidate_ore


def update_offensive_ore_target(self: Builder) -> None:
    """Enemy-side Ti ore claim. Same re-evaluation semantics as
    `update_ore_target`: keep the current pick if still valid and not
    trivially beaten by a much-closer alternative.
    """
    candidate = pick_offensive_ti_ore_target(self)
    if (
        not self.offensive_ore_target
        or not ore_available(self, self.offensive_ore_target)
        or not self.is_reachable(self.offensive_ore_target)
        or harvester_would_contaminate(self, self.offensive_ore_target)
        or (
            candidate
            and candidate.distance_squared(self.my_pos) <= 2
            and self.offensive_ore_target.distance_squared(self.my_pos) > 2
        )
    ):
        self.offensive_ore_target = candidate


_AX_HARVESTER_ROUND_GATE = 500
"""Derived from Blue Dragon / Kessoku Band: no Ax harvester before turn 500."""


def _is_zero_length_foundry_spot(self: Builder, pos: Position) -> bool:
    """Pure friendly `BuildingConveyor` with exactly one cardinal friendly
    Ax harvester. This is the designated foundry spot for a zero-length
    Ax chain — `harvester_would_contaminate` has already admitted the Ax
    harvester under the same geometric rule.
    """
    bld = self.buildings[pos.y * MAX_WIDTH + pos.x]
    if not isinstance(bld, BuildingConveyor):
        return False
    if bld.team != self.my_team:
        return False
    ax_harv_count = 0
    for d in DIR4:
        n = pos.add(d)
        if not self.in_bounds(n):
            continue
        nb = self.buildings[n.y * MAX_WIDTH + n.x]
        if (
            isinstance(nb, BuildingHarvester)
            and nb.team == self.my_team
            and self.env[n.y * MAX_WIDTH + n.x] == Environment.ORE_AXIONITE
        ):
            ax_harv_count += 1
            if ax_harv_count > 1:
                return False
    return ax_harv_count == 1


def _foundry_local_ok(self: Builder, pos: Position) -> bool:
    """Foundry candidate: friendly Ti conveyor that reaches the core, is NOT
    on a chain already feeding a foundry, and is NOT structurally downstream
    of any known Ax harvester (`ax_upstream`). The `ax_upstream` gate catches
    mixed-flow trunks whose periodic Ax stacks happen to sit outside the
    8-turn flow window at pick time. Flow history must show Ti and no Ax as
    the empirical corroboration.

    Zero-length Ax chain exception: a pure `BuildingConveyor` cardinal to
    exactly one friendly Ax harvester bypasses the `ax_harvester_adjacent`,
    `ax_upstream`, and `has_ax` gates — those gates would reject the
    designated foundry spot the moment the Ax harvester is visible, but
    that's exactly where we WANT the foundry.
    """
    i = pos.y * MAX_WIDTH + pos.x
    bld = self.buildings[i]
    if not isinstance(bld, BuildingConveyor | BuildingArmouredConveyor):
        return False
    if bld.team != self.my_team:
        return False
    if pos in self.upstream_of_dangling:
        return False
    if pos in self.reaches_foundry:
        return False
    is_foundry_spot = _is_zero_length_foundry_spot(self, pos)
    if not is_foundry_spot:
        if pos in self.ax_harvester_adjacent:
            return False
        if pos in self.ax_upstream:
            return False
    hist = self.flow_history[i]
    saw_ti = False
    has_ax = False
    for r, _rid in hist:
        if r is None:
            continue
        if r in (ResourceType.RAW_AXIONITE, ResourceType.REFINED_AXIONITE):
            has_ax = True
        elif r == ResourceType.TITANIUM:
            saw_ti = True
    if has_ax and not is_foundry_spot and not ax_feeds_target(self, pos):
        return False
    return saw_ti


def _tile_volume(self: Builder, pos: Position) -> int:
    """Occupancy count: non-None entries in the tile's flow_history.
    Equals `FLOW_HISTORY_LEN` iff the tile was observed occupied on every
    one of the last `FLOW_HISTORY_LEN` ticks — the empirical
    "running at 1.00" signal.
    """
    return sum(
        1 for r, _ in self.flow_history[pos.y * MAX_WIDTH + pos.x] if r is not None
    )


def _pure_ax_merge_ok(self: Builder, pos: Position) -> bool:
    """`pos` is a pure-Ax transport tile worth merging a new Ax chain into:
    downstream of an Ax harvester, not downstream of a Ti harvester, not
    upstream of a dangling end, and not currently saturated (empirical
    volume < FLOW_HISTORY_LEN). The saturation check prevents a fresh merge
    from tipping an already-busy tile into over-capacity, which in turn
    keeps the destroy-and-rebuild cycle from ever forming.
    """
    if _tile_volume(self, pos) >= FLOW_HISTORY_LEN:
        return False
    return (
        pos in self.ax_upstream
        and pos not in self.ti_upstream
        and pos not in self.upstream_of_dangling
    )


_FOUNDRY_REUSE_THRESHOLD = 10
"""Manhattan-distance threshold: a pre-existing foundry or Ax chain is only
preferred over building a new foundry on a nearby Ti conveyor if the pre-
existing option isn't more than this many tiles further. Otherwise creating
a new foundry locally is the better choice."""


def _manhattan(a: Position, b: Position) -> int:
    return abs(a.x - b.x) + abs(a.y - b.y)


def _detect_congested_junctions(self: Builder) -> list[Position]:
    """Find junctions (multi-feeder tiles) where the feeders' total
    observed inflow exceeds the junction's FLOW_HISTORY_LEN window — i.e.
    stacks arrive faster than a single-tile pass-through can forward.
    These are the root-cause congestion points; everything upstream
    back-pressures from here.

    Excludes foundries: they are designed to consume 1.00 Ti + 1.00 Ax
    simultaneously (producing 1.00 RAx), so a foundry's feeder sum of
    2.00 is operating-as-intended, not congestion.
    """
    result: list[Position] = []
    for t in self.nearby_buildings:
        i = t.y * MAX_WIDTH + t.x
        bld = self.buildings[i]
        if not isinstance(
            bld,
            BuildingConveyor | BuildingArmouredConveyor | BuildingBridge,
        ):
            continue
        feeders = self.in_edges[i]
        if len(feeders) < 2:
            continue
        hist = self.flow_history[i]
        if len(hist) < FLOW_HISTORY_LEN:
            continue
        if sum(1 for r, _ in hist if r is not None) < FLOW_HISTORY_LEN:
            continue
        total = 0
        complete = True
        for f in feeders:
            fh = self.flow_history[f.y * MAX_WIDTH + f.x]
            if len(fh) < FLOW_HISTORY_LEN:
                complete = False
                break
            total += sum(1 for r, _ in fh if r is not None)
        if complete and total > FLOW_HISTORY_LEN:
            result.append(t)
    return result


def _detect_saturated_tiles(self: Builder) -> list[Position]:
    """Transport tiles running empirically at full throughput — their
    flow_history is fully occupied. A saturated tile has no headroom
    for another feeder, so everything upstream of it is a bad sink.
    """
    result: list[Position] = []
    for t in self.nearby_buildings:
        i = t.y * MAX_WIDTH + t.x
        bld = self.buildings[i]
        if not isinstance(
            bld,
            BuildingConveyor | BuildingArmouredConveyor | BuildingBridge,
        ):
            continue
        hist = self.flow_history[i]
        if len(hist) < FLOW_HISTORY_LEN:
            continue
        if sum(1 for r, _ in hist if r is not None) >= FLOW_HISTORY_LEN:
            result.append(t)
    return result


def update_economy_reachability(self: Builder) -> None:
    """Per-turn flood over the structural transport graph. Marks
    `reaches_core`, `reaches_foundry`, `upstream_of_dangling`,
    `upstream_of_congestion` (backward over `in_edges`) and
    `ti_upstream`, `ax_upstream` (forward over `out_edges`). All O(edges)
    set-membership lookups afterwards.
    """
    self.reaches_core = set()
    self.reaches_foundry = set()
    self.ti_upstream = set()
    self.ax_upstream = set()
    self.upstream_of_dangling = set()
    self.upstream_of_congestion = set()

    in_edges = self.in_edges
    out_edges = self.out_edges

    def flood_back(roots: list[Position], target: set[Position]) -> None:
        stack: list[Position] = []
        for r in roots:
            if r not in target:
                target.add(r)
                stack.append(r)
        while stack:
            p = stack.pop()
            for u in in_edges[p.y * MAX_WIDTH + p.x]:
                if u in target:
                    continue
                target.add(u)
                stack.append(u)

    if self.my_core is not None:
        flood_back([self.my_core, *self.core_edges], self.reaches_core)

    if self.my_foundries:
        flood_back(list(self.my_foundries), self.reaches_foundry)

    dangling_roots = [p for p in self.dangling_set if in_edges[p.y * MAX_WIDTH + p.x]]
    flood_back(dangling_roots, self.upstream_of_dangling)

    self.congested_junctions = set(_detect_congested_junctions(self))
    flood_back(list(self.congested_junctions), self.upstream_of_congestion)

    def flood_forward(seeds: set[Position], target: set[Position]) -> None:
        stack: list[Position] = []
        for s in seeds:
            if s in target:
                continue
            if not out_edges[s.y * MAX_WIDTH + s.x]:
                continue
            target.add(s)
            stack.append(s)
        while stack:
            p = stack.pop()
            for out in out_edges[p.y * MAX_WIDTH + p.x]:
                if out in target:
                    continue
                target.add(out)
                stack.append(out)

    flood_forward(self.ti_harvester_adjacent, self.ti_upstream)
    flood_forward(self.ax_harvester_adjacent, self.ax_upstream)


def _feeder_flow_kind(self: Builder, f: Position) -> str | None:
    """Classify a feeder tile by its observed flow-history: 'ti' if only
    Ti stacks seen, 'ax' if only Ax stacks seen, None if no flow observed
    or mixed. Used as the empirical backstop for `_is_junction`.
    """
    i = f.y * MAX_WIDTH + f.x
    seen_ti = False
    seen_ax = False
    for r, _rid in self.flow_history[i]:
        if r is None:
            continue
        if r == ResourceType.TITANIUM:
            seen_ti = True
        elif r in (ResourceType.RAW_AXIONITE, ResourceType.REFINED_AXIONITE):
            seen_ax = True
    if seen_ti and not seen_ax:
        return "ti"
    if seen_ax and not seen_ti:
        return "ax"
    return None


def _is_junction(self: Builder, pos: Position) -> bool:
    """True iff `pos` is a viable foundry site: a friendly conveyor or
    armoured conveyor with >= 1 feeder delivering Ti only AND >= 1 feeder
    delivering Ax only. Checked structurally via `ti_upstream` / `ax_upstream`
    first; falls back to `flow_history` evidence on each feeder.
    """
    i = pos.y * MAX_WIDTH + pos.x
    bld = self.buildings[i]
    if not isinstance(bld, BuildingConveyor | BuildingArmouredConveyor):
        return False
    if bld.team != self.my_team:
        return False
    feeders = self.in_edges[i]
    if len(feeders) < 2:
        return False

    has_ti = False
    has_ax = False
    for f in feeders:
        in_ti = f in self.ti_upstream
        in_ax = f in self.ax_upstream
        if in_ti and not in_ax:
            has_ti = True
        elif in_ax and not in_ti:
            has_ax = True
    if has_ti and has_ax:
        return True

    # Empirical fallback: pure-Ti / pure-Ax flow on feeders.
    for f in feeders:
        kind = _feeder_flow_kind(self, f)
        if kind == "ti":
            has_ti = True
        elif kind == "ax":
            has_ax = True
    return has_ti and has_ax


def update_junctions(self: Builder) -> None:
    """Derive `self.junctions` from `is_multi_input` using `_is_junction`.
    Runs once per turn after `update_economy_reachability` has populated
    `ti_upstream` / `ax_upstream`. Scanned set size is bounded by the number
    of multi-input conveyors in the observed transport network, typically
    well under 100.
    """
    self.junctions.clear()
    for pos in self.is_multi_input:
        if _is_junction(self, pos):
            self.junctions.add(pos)


def update_foundry_target(self: Builder) -> None:
    """Re-derive `ax_sink` every turn from three option classes.
    `foundry_target` tracks `ax_sink` (when kind is `ti_candidate`) until
    the Ax chain physically connects (`ax_feeds_target` True), at which
    point it locks. Topology invalidation (tile no longer a valid
    kind-C site) clears the lock and resumes tracking.
    """
    if not self.ax_ore_target and not self.ax_harvester_adjacent:
        self.ax_sink = None
        self.foundry_target = None
        return

    origin = self.dangling_output if self.dangling_output is not None else self.my_pos

    ax_chain_best: Position | None = None
    ax_chain_d = 1 << 30
    foundry_best: Position | None = None
    foundry_d = 1 << 30
    ti_cand_best: Position | None = None
    ti_cand_d = 1 << 30

    with Scope("foundries", time=True):
        for pos in self.my_foundries:
            d = _manhattan(origin, pos)
            if d < foundry_d:
                foundry_d = d
                foundry_best = pos

    with Scope("ax_upstream", time=True):
        for pos in self.ax_upstream:
            if not _pure_ax_merge_ok(self, pos):
                continue
            d = _manhattan(origin, pos)
            if d < ax_chain_d:
                ax_chain_d = d
                ax_chain_best = pos

    with Scope("ti_candidates", time=True):
        for pos in self.reaches_core - self.reaches_foundry:
            if not _foundry_local_ok(self, pos):
                continue
            d = _manhattan(origin, pos)
            if d < ti_cand_d:
                ti_cand_d = d
                ti_cand_best = pos

    options: list[tuple[int, Position | None, str]] = []
    if ax_chain_best is not None:
        options.append((ax_chain_d, ax_chain_best, "ax_chain"))
    if foundry_best is not None:
        options.append((foundry_d, foundry_best, "foundry"))
    if ti_cand_best is not None:
        options.append(
            (ti_cand_d + _FOUNDRY_REUSE_THRESHOLD, ti_cand_best, "ti_candidate"),
        )
    if not options:
        self.ax_sink = None
    else:
        options.sort(key=lambda o: o[0])
        _, chosen, _kind = options[0]
        self.ax_sink = chosen

    # foundry_target is independent of ax_sink selection: commit when the
    # Ax chain has physically connected to a valid kind-C site. Topology
    # invalidation drops the commitment.
    ft = self.foundry_target
    if ft is not None:
        bld = self.buildings[ft.y * MAX_WIDTH + ft.x]
        still_valid = (
            isinstance(bld, BuildingConveyor | BuildingArmouredConveyor)
            and bld.team == self.my_team
            and ft in self.reaches_core
            and ft not in self.reaches_foundry
        )
        if not still_valid:
            self.foundry_target = None
    if self.foundry_target is None and self.ax_sink is not None:
        chosen = self.ax_sink
        if _foundry_local_ok(self, chosen) and ax_feeds_target(self, chosen):
            self.foundry_target = chosen


def _ti_sink_ok(self: Builder, pos: Position) -> bool:
    """Empirical Ti-sink candidate: friendly Ti conveyor that carries Ti,
    not Ax-contaminated, not upstream of a dangling end or a congested
    junction, and not currently saturated (volume < FLOW_HISTORY_LEN). The
    saturation check prevents a fresh merge from tipping an already-busy
    tile into over-capacity — and is the inherent rule that stops the
    destroy-and-rebuild cycle: after destruction the sink's flow_history
    still shows volume=FLOW_HISTORY_LEN for ~FLOW_HISTORY_LEN turns, so it's
    not re-picked.
    """
    i = pos.y * MAX_WIDTH + pos.x
    bld = self.buildings[i]
    if not isinstance(bld, BuildingConveyor | BuildingArmouredConveyor):
        return False
    if bld.team != self.my_team:
        return False
    if pos in self.upstream_of_dangling:
        return False
    if pos in self.upstream_of_congestion:
        return False
    if pos in self.ax_harvester_adjacent:
        return False
    hist = self.flow_history[i]
    if _tile_volume(self, pos) >= FLOW_HISTORY_LEN:
        return False
    saw_ti = False
    for r, _rid in hist:
        if r in (ResourceType.RAW_AXIONITE, ResourceType.REFINED_AXIONITE):
            return False
        if r == ResourceType.TITANIUM:
            saw_ti = True
    return saw_ti


def _near_core_saving_threshold(self: Builder) -> int:
    """Tier-1 (branch merge) requires this many Manhattan tiles saved vs.
    routing to core. Grows with round — early game is cheap, so merging
    is fine; late game has many harvesters, so we prefer independent
    core-trunks to avoid forming overcapacity junctions. Integer steps,
    round-to-nearest.
    """
    return 5 + round(self.round / 80)


def update_ti_sink(self: Builder) -> None:
    """Pick where new Ti chains should terminate. Three-tier preference
    (pick nearest-to-anchor within the first non-empty tier):

    1. Ti conveyor candidate FAR from core — joining it saves more than
       `_near_core_saving_threshold(self)` tiles of Manhattan distance vs.
       routing direct to core. The threshold grows with round so late-game
       merges are effectively disabled.
    2. Core edge — direct delivery, new trunk, no congestion on existing trunk.
    3. Ti conveyor candidate NEAR core — joining saves <= threshold,
       piles flow onto a short trunk. Only picked when tiers 1/2 are empty.
    """
    anchor = self.dangling_output if self.dangling_output is not None else self.my_pos
    core = self.my_core
    d_builder_to_core = (
        abs(self.my_pos.x - core.x) + abs(self.my_pos.y - core.y)
        if core is not None
        else 0
    )
    saving_threshold = _near_core_saving_threshold(self)

    tier1_best: Position | None = None
    tier1_d = 1 << 30
    tier3_best: Position | None = None
    tier3_d = 1 << 30
    for pos in self.nearby_tiles:
        if not _ti_sink_ok(self, pos):
            continue
        d_anchor_sq = anchor.distance_squared(pos)
        d_builder_to_cand = abs(self.my_pos.x - pos.x) + abs(self.my_pos.y - pos.y)
        saving = d_builder_to_core - d_builder_to_cand
        if saving <= saving_threshold:
            if d_anchor_sq < tier3_d:
                tier3_d = d_anchor_sq
                tier3_best = pos
        elif d_anchor_sq < tier1_d:
            tier1_d = d_anchor_sq
            tier1_best = pos

    tier2_best: Position | None = None
    tier2_d = 1 << 30
    for edge in self.core_edges:
        d = anchor.distance_squared(edge)
        if d < tier2_d:
            tier2_d = d
            tier2_best = edge

    if tier1_best is not None:
        best, best_d, tier = tier1_best, tier1_d, 1
    elif tier2_best is not None:
        best, best_d, tier = tier2_best, tier2_d, 2
    else:
        best, best_d, tier = tier3_best, tier3_d, 3

    if best != self.ti_sink:
        log(
            f"update_ti_sink: ti_sink changed from {self.ti_sink} to {best} "
            f"(tier {tier}, anchor={anchor}, dist_sq={best_d})",
        )
    self.ti_sink = best


def update_ax_ore_target(self: Builder) -> None:
    """Pick the nearest unclaimed Ax-ore tile, gated on round AND Ti buffer
    of >= 2x scaled harvester cost (matches the empirical rule from the
    Blue Dragon / something else / Kessoku Band replays).
    """
    if self.round < _AX_HARVESTER_ROUND_GATE:
        self.ax_ore_target = None
        return
    ti_base, _ax_base = BASE_COST[EntityType.HARVESTER]
    if self.ti < 2 * int(ti_base * self.scale):
        self.ax_ore_target = None
        return
    candidate = pick_ax_ore_target(self)
    if (
        not self.ax_ore_target
        or not ore_available(self, self.ax_ore_target)
        or not self.is_reachable(self.ax_ore_target)
        or harvester_would_contaminate(self, self.ax_ore_target)
        or (
            candidate
            and candidate.distance_squared(self.my_pos) <= 2
            and self.ax_ore_target.distance_squared(self.my_pos) > 2
        )
    ):
        self.ax_ore_target = candidate
