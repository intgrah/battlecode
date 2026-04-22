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
from util.constants import BASE_COST, INF, MAX_WIDTH
from util.directions import DIR4
from util.debug import debug as log

from builder.helpers import (
    ax_feeds_target,
    find_dangling,
    harvester_would_contaminate,
    is_dangling,
    ore_available,
    pick_ax_ore_target,
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

    conv = self.get_conveyors_to_here(pos)
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


def update_dangling(self: Builder) -> None:
    if self.pending_bridge:
        self.dangling_output = self.pending_bridge
        return

    if self.dangling_output is not None and is_dangling(self, self.dangling_output):
        return

    if is_dangling(self, self.my_pos):
        self.dangling_output = self.my_pos
        return

    match self.get_building(self.my_pos):
        case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
            target = self.my_pos.add(d)
            if is_dangling(self, target):
                self.dangling_output = target
                return
        case _:
            for n in self.neighbours_8:
                if is_dangling(self, n):
                    self.dangling_output = n
                    return

    self.dangling_output = find_dangling(self)


def update_ore_target(self: Builder) -> None:
    candidate_ore = pick_ore_target(self)
    if (
        not self.ore_target
        or not ore_available(self, self.ore_target)
        or self.bfs_dist[self.ore_target.y * MAX_WIDTH + self.ore_target.x] is INF
        or harvester_would_contaminate(self, self.ore_target)
        or (
            candidate_ore
            and candidate_ore.distance_squared(self.my_pos) <= 2
            and self.ore_target.distance_squared(self.my_pos) > 2
        )
    ):
        self.ore_target = candidate_ore


_AX_HARVESTER_ROUND_GATE = 500
"""Derived from Blue Dragon / Kessoku Band: no Ax harvester before turn 500."""


def _foundry_local_ok(self: Builder, pos: Position) -> bool:
    """Foundry candidate: friendly Ti conveyor that reaches the core, is NOT
    on a chain already feeding a foundry, and is NOT structurally downstream
    of any known Ax harvester (`ax_upstream`). The `ax_upstream` gate catches
    mixed-flow trunks whose periodic Ax stacks happen to sit outside the
    8-turn flow window at pick time. Flow history must show Ti and no Ax as
    the empirical corroboration."""
    i = pos.y * MAX_WIDTH + pos.x
    bld = self.buildings[i]
    if not isinstance(bld, BuildingConveyor | BuildingArmouredConveyor):
        return False
    if bld.team != self.my_team:
        return False
    if pos in self.ax_harvester_adjacent:
        return False
    if pos not in self.reaches_core:
        return False
    if pos in self.reaches_foundry:
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
    if has_ax and not ax_feeds_target(self, pos):
        return False
    return saw_ti


def _ax_chain_reaches_foundry(self: Builder, pos: Position) -> bool:
    """`pos` is a friendly transport tile that reaches a foundry (per the
    per-turn backward DFS from foundries) AND is downstream of an Ax
    harvester AND is NOT downstream of a Ti harvester. All three checks are
    O(1) set lookups against precomputed reachability sets."""
    i = pos.y * MAX_WIDTH + pos.x
    bld = self.buildings[i]
    return (
        isinstance(
            bld,
            BuildingConveyor
            | BuildingArmouredConveyor
            | BuildingSplitter
            | BuildingBridge,
        )
        and bld.team == self.my_team
        and pos in self.reaches_foundry
        and pos in self.ax_upstream
        and pos not in self.ti_upstream
    )


_FOUNDRY_REUSE_THRESHOLD = 10
"""Manhattan-distance threshold: a pre-existing foundry or Ax chain is only
preferred over building a new foundry on a nearby Ti conveyor if the pre-
existing option isn't more than this many tiles further. Otherwise creating
a new foundry locally is the better choice."""


def _manhattan(a: Position, b: Position) -> int:
    return abs(a.x - b.x) + abs(a.y - b.y)


def update_economy_reachability(self: Builder) -> None:
    """Per-turn DFS from the core and from each known friendly foundry over
    the reverse economy graph (conveyors_to_here + splitters_to_here). Marks
    `self.reaches_core` and `self.reaches_foundry`. O(tiles in the transport
    network) total work, so per-candidate checks collapse to O(1) set
    membership instead of per-candidate BFS.

    Also computes `ti_upstream` / `ax_upstream` via forward flood from
    harvester-adjacent transport tiles, so `chain_ore_kinds`-style lookups
    become O(1) set membership as well."""
    self.reaches_core = set()
    self.reaches_foundry = set()
    self.ti_upstream = set()
    self.ax_upstream = set()

    def flood_back(roots: list[Position], target: set[Position]) -> None:
        stack: list[Position] = []
        for r in roots:
            if r not in target:
                target.add(r)
                stack.append(r)
        while stack:
            p = stack.pop()
            i = p.y * MAX_WIDTH + p.x
            for u in self.conveyors_to_here[i]:
                if u in target:
                    continue
                target.add(u)
                stack.append(u)
            for u in self.splitters_to_here[i]:
                if u in target:
                    continue
                target.add(u)
                stack.append(u)

    if self.my_core is not None:
        core_roots = [self.my_core, *self.core_edges]
        flood_back(core_roots, self.reaches_core)

    if self.my_foundries:
        flood_back(list(self.my_foundries), self.reaches_foundry)

    def flood_forward(seeds: set[Position], target: set[Position]) -> None:
        stack: list[Position] = []
        for s in seeds:
            if s in target:
                continue
            bld = self.buildings[s.y * MAX_WIDTH + s.x]
            if not isinstance(
                bld,
                (
                    BuildingConveyor
                    | BuildingArmouredConveyor
                    | BuildingSplitter
                    | BuildingBridge
                ),
            ):
                continue
            if bld.team != self.my_team:
                continue
            target.add(s)
            stack.append(s)
        while stack:
            p = stack.pop()
            bld = self.buildings[p.y * MAX_WIDTH + p.x]
            outs: list[Position] = []
            match bld:
                case (
                    BuildingConveyor(direction=d)
                    | BuildingArmouredConveyor(
                        direction=d,
                    )
                ):
                    outs.append(p.add(d))
                case BuildingSplitter(direction=d):
                    back = d.opposite()
                    outs.extend(p.add(sd) for sd in DIR4 if sd != back)
                case BuildingBridge(target=t):
                    outs.append(t)
            for out in outs:
                if not self.in_bounds(out):
                    continue
                if out in target:
                    continue
                b2 = self.buildings[out.y * MAX_WIDTH + out.x]
                if not isinstance(
                    b2,
                    (
                        BuildingConveyor
                        | BuildingArmouredConveyor
                        | BuildingSplitter
                        | BuildingBridge
                    ),
                ):
                    continue
                if b2.team != self.my_team:
                    continue
                target.add(out)
                stack.append(out)

    flood_forward(self.ti_harvester_adjacent, self.ti_upstream)
    flood_forward(self.ax_harvester_adjacent, self.ax_upstream)


def _feeder_flow_kind(self: Builder, f: Position) -> str | None:
    """Classify a feeder tile by its observed flow-history: 'ti' if only
    Ti stacks seen, 'ax' if only Ax stacks seen, None if no flow observed
    or mixed. Used as the empirical backstop for `_is_junction`."""
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
    first; falls back to `flow_history` evidence on each feeder."""
    i = pos.y * MAX_WIDTH + pos.x
    bld = self.buildings[i]
    if not isinstance(bld, BuildingConveyor | BuildingArmouredConveyor):
        return False
    if bld.team != self.my_team:
        return False
    feeders = self.conveyors_to_here[i] + self.splitters_to_here[i]
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
    well under 100."""
    self.junctions.clear()
    for pos in self.is_multi_input:
        if _is_junction(self, pos):
            self.junctions.add(pos)


def update_foundry_target(self: Builder) -> None:
    """Re-derive `ax_sink` every turn from three option classes.
    `foundry_target` tracks `ax_sink` (when kind is `ti_candidate`) until
    the Ax chain physically connects (`ax_feeds_target` True), at which
    point it locks. Topology invalidation (tile no longer a valid
    kind-C site) clears the lock and resumes tracking."""
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

    for pos in self.my_foundries:
        d = _manhattan(origin, pos)
        if d < foundry_d:
            foundry_d = d
            foundry_best = pos

    for pos in self.reaches_foundry & self.ax_upstream:
        if pos in self.ti_upstream:
            continue
        if not _ax_chain_reaches_foundry(self, pos):
            continue
        d = _manhattan(origin, pos)
        if d < ax_chain_d:
            ax_chain_d = d
            ax_chain_best = pos

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
        if (
            _foundry_local_ok(self, chosen)
            and ax_feeds_target(self, chosen)
        ):
            self.foundry_target = chosen


def _ti_sink_ok(self: Builder, pos: Position) -> bool:
    """Empirical Ti-sink candidate: friendly Ti conveyor that is both
    flowing (Ti observed, no Ax contamination) AND not congested. Congestion
    signals, in order of earliness:
      - Any stack id appears at least twice in the flow_history window →
        a stack sat on the tile across ticks without moving (fires 2
        ticks in).
      - Legacy fallback: every slot in the 8-entry window is non-None AND
        all-Ti, which only fires after the window fills."""
    i = pos.y * MAX_WIDTH + pos.x
    bld = self.buildings[i]
    if not isinstance(bld, BuildingConveyor | BuildingArmouredConveyor):
        return False
    if bld.team != self.my_team:
        return False
    # Don't pick a tile that feeds into our dangling output — routing toward
    # it would double back through our own in-progress chain. This is the
    # specific "just-placed conveyor becomes ti_sink" bug fix.
    if (
        self.dangling_output is not None
        and pos
        in self.conveyors_to_here[
            self.dangling_output.y * MAX_WIDTH + self.dangling_output.x
        ]
    ):
        return False
    if pos in self.ax_harvester_adjacent:
        return False
    hist = self.flow_history[i]
    saw_ti = False
    has_ax = False
    seen_ids: set[int] = set()
    repeated_id = False
    for r, rid in hist:
        if r in (ResourceType.RAW_AXIONITE, ResourceType.REFINED_AXIONITE):
            has_ax = True
        elif r == ResourceType.TITANIUM:
            saw_ti = True
        if rid is not None:
            if rid in seen_ids:
                repeated_id = True
            else:
                seen_ids.add(rid)
    if has_ax or repeated_id or not saw_ti:
        return False
    # Legacy: if the window is full AND every slot is Ti (no empty), treat
    # as saturated island. Duplicate-id check above is stricter, so this is
    # just belt-and-braces.
    return not (len(hist) == hist.maxlen and all(r is not None for r, _ in hist))


_NEAR_CORE_SAVING_THRESHOLD = 5
"""A Ti conveyor candidate is considered 'near core' (tier 3) if joining to
it saves at most this many tiles of Manhattan distance vs. routing directly
to the core. I.e. if `Manhattan(builder, core) - Manhattan(builder, candidate)
<= 5`, joining is a small saving and the candidate gets deprioritised."""


def update_ti_sink(self: Builder) -> None:
    """Pick where new Ti chains should terminate. Three-tier preference
    (pick nearest-to-anchor within the first non-empty tier):

    1. Ti conveyor candidate FAR from core — joining it saves more than
       `_NEAR_CORE_SAVING_THRESHOLD` tiles of Manhattan distance vs. routing
       direct to core.
    2. Core edge — direct delivery, new trunk, no congestion on existing trunk.
    3. Ti conveyor candidate NEAR core — joining saves <= threshold,
       piles flow onto a short trunk. Only picked when tiers 1/2 are empty."""
    anchor = self.dangling_output if self.dangling_output is not None else self.my_pos
    core = self.my_core
    d_builder_to_core = (
        abs(self.my_pos.x - core.x) + abs(self.my_pos.y - core.y)
        if core is not None
        else 0
    )

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
        if saving <= _NEAR_CORE_SAVING_THRESHOLD:
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
    Blue Dragon / something else / Kessoku Band replays)."""
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
        or self.bfs_dist[self.ax_ore_target.y * MAX_WIDTH + self.ax_ore_target.x] is INF
        or harvester_would_contaminate(self, self.ax_ore_target)
        or (
            candidate
            and candidate.distance_squared(self.my_pos) <= 2
            and self.ax_ore_target.distance_squared(self.my_pos) > 2
        )
    ):
        self.ax_ore_target = candidate
