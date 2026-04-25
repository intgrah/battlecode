from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Final, override

from building import (
    BuildingArmouredConveyor,
    BuildingBreach,
    BuildingBridge,
    BuildingConveyor,
    BuildingCore,
    BuildingFoundry,
    BuildingGunner,
    BuildingLauncher,
    BuildingMarker,
    BuildingRoad,
    BuildingSentinel,
    BuildingSplitter,
)
from cambc import (
    Controller,
    EntityType,
    Environment,
    Position,
    ResourceType,
)
from config import DEBUG_DUMP, HARDCODE
from hardcode.identify import core_for, find_core, identify_map
from hardcode.map import SYMMETRY, TILES, decode
from unit import Unit
from util.constants import FLOW_HISTORY_LEN, INF, MAX_N, MAX_WIDTH
from util.debug import Scope
from util.debug import debug as log
from util.directions import DIR4, DIR8, DIR8_DELTA
from util.symmetry import Symmetry

from builder.algorithms.astar import MoveHeapAstar
from builder.algorithms.bfs import extract_path, update_bfs
from builder.algorithms.econ_astar import AStarSearch
from builder.dump import dump
from builder.hooks.heal import end_of_turn_heal
from builder.hooks.indicators import indicators
from builder.hooks.propagate_symmetry import end_of_turn_propagate_symmetry
from builder.role import Role
from builder.tasks import POLICIES
from builder.tasks.offense_helpers import begin_turn_offense
from builder.tasks.rejected import TaskRejectedError
from builder.update import update
from builder.update.econ import (
    can_place_junction,
    update_ax_ore_target,
    update_dangling,
    update_economy_reachability,
    update_foundry_target,
    update_junctions,
    update_map_econ,
    update_offensive_ore_target,
    update_ore_target,
    update_ti_sink,
    update_unreachable_dangling,
)
from builder.update.markers import update_markers
from builder.update.prune import prune_stale
from builder.update.reflect import update_reflect
from builder.update.role import update_role
from builder.update.turrets import update_enemy_turrets, update_ore_denial
from builder.update.vision import update_vision

if TYPE_CHECKING:
    from building import Building

    from builder.algorithms.bugnav import WallFollow


class Builder(Unit):
    def _refresh_ti_leakage(self, i: int) -> None:
        new = self._ax_harv_at[i] > 0 or self._foundry_at[i] > 0
        if new != self.ti_leakage[i]:
            self.ti_leakage[i] = new
            self.ti_routable[i] = self.buildable[i] and not new

    def _refresh_ax_leakage(self, i: int) -> None:
        new = self._ti_harv_at[i] > 0
        if new != self.ax_leakage[i]:
            self.ax_leakage[i] = new
            self.ax_routable[i] = self.buildable[i] and not new

    def _bump_ti_harv(self, pos: Position, delta: int) -> None:
        """Called when a friendly or enemy Ti harvester appears/disappears at
        `pos`. Adjusts `_ti_harv_at` for the 4 cardinal tiles and refreshes
        `ax_leakage` / `ax_routable` on them.
        """
        for d in DIR4:
            n = pos.add(d)
            if self.in_bounds(n):
                ni = n.y * MAX_WIDTH + n.x
                self._ti_harv_at[ni] += delta
                self._refresh_ax_leakage(ni)

    def _bump_ax_harv(self, pos: Position, delta: int) -> None:
        for d in DIR4:
            n = pos.add(d)
            if self.in_bounds(n):
                ni = n.y * MAX_WIDTH + n.x
                self._ax_harv_at[ni] += delta
                self._refresh_ti_leakage(ni)

    def _bump_foundry(self, pos: Position, delta: int) -> None:
        for d in DIR4:
            n = pos.add(d)
            if self.in_bounds(n):
                ni = n.y * MAX_WIDTH + n.x
                self._foundry_at[ni] += delta
                self._refresh_ti_leakage(ni)

    def _check_multi_input(self, t: Position) -> None:
        """Call after `in_edges[idx(t)]` is mutated. Adds/removes t from
        `is_multi_input` based on the current feeder count.
        """
        idx = t.y * MAX_WIDTH + t.x
        if len(self.in_edges[idx]) >= 2:
            self.is_multi_input.add(t)
        else:
            self.is_multi_input.discard(t)

    def _is_flow_consumer(self, pos: Position) -> bool:
        """Tile hosts a friendly building that accepts flow (transport or
        sink). Used for splitter-satisfaction counting.
        """
        b = self.buildings[pos.y * MAX_WIDTH + pos.x]
        if b is None or b.team != self.my_team:
            return False
        return isinstance(
            b,
            BuildingConveyor
            | BuildingArmouredConveyor
            | BuildingBridge
            | BuildingSplitter
            | BuildingFoundry
            | BuildingCore
            | BuildingGunner
            | BuildingSentinel
            | BuildingBreach
            | BuildingLauncher,
        )

    def _splitter_satisfied(self, splitter_pos: Position) -> bool:
        """A splitter is 'satisfied' iff >= 2 of its output tiles host a
        friendly flow consumer. Unsatisfied splitters contribute their
        empty outputs as dangling ends; satisfied ones don't.
        """
        count = 0
        for out in self.out_edges[splitter_pos.y * MAX_WIDTH + splitter_pos.x]:
            if self._is_flow_consumer(out):
                count += 1
                if count >= 2:
                    return True
        return False

    def _check_dangling(self, t: Position) -> None:
        """Re-evaluate whether `t` is a dangling chain end and sync
        membership across `dangling_set` and `unreachable_dangling`. These
        two sets are disjoint: `dangling_set` holds the reachable ones,
        `unreachable_dangling` the ones whose `bfs_dist is INF`. This hook
        only knows topology, not reachability — newly-dangling tiles enter
        `dangling_set` and the per-turn migration sorts them later. A tile
        already in `unreachable_dangling` stays there (don't flip-flop
        until reachability is rechecked).

        A tile `t` is dangling iff it's empty/friendly-road AND at least
        one of:
        - It is adjacent to an unconnected harvester.
        - Some feeder in `in_edges[t]` is unsatisfied: conveyors / armoured
          conveyors / bridges are always unsatisfied when their single
          output is empty (i.e., when `t` is that output); splitters are
          unsatisfied only when `_splitter_satisfied` returns False.

        Call after any input could have changed: in_edges[t],
        buildings[t], env[t], a feeder splitter's output connectivity, or
        t's membership in adjacent_to_unconnected_harvester.
        """
        i = t.y * MAX_WIDTH + t.x
        # A tile can host a new chain end iff it's empty non-wall terrain,
        # a friendly road, or any marker (markers are cheaply overbuildable).
        # Anything else disqualifies the tile from being a dangling target.
        match self.buildings[i]:
            case None if self.env[i] != Environment.WALL:
                pass
            case BuildingRoad(team=self.my_team) | BuildingMarker():
                pass
            case _:
                self.dangling_set.discard(t)
                self.unreachable_dangling.discard(t)
                return

        is_dangling = t in self.adjacent_to_unconnected_harvester or any(
            not (
                isinstance(self.buildings[f.y * MAX_WIDTH + f.x], BuildingSplitter)
                and self._splitter_satisfied(f)
            )
            for f in self.in_edges[i]
        )

        if is_dangling:
            if t not in self.unreachable_dangling:
                self.dangling_set.add(t)
        else:
            self.dangling_set.discard(t)
            self.unreachable_dangling.discard(t)

    def _log_state(self) -> None:
        """Human-readable dump of all post-update Builder state, grouped
        by domain. Cheap: scalars + small counts, no per-tile arrays.
        """
        log(f"state: id={self.my_id} pos={self.my_pos} round={self.round}")
        with Scope("identity"):
            log(f"role={self.role} age={self.role_age} perm={self.permanent_role}")
            log(
                f"symmetry={self.symmetry} "
                f"candidates={sorted(s.name for s in self.symmetry_candidates)} "
                f"en_core_seen={self.en_core_seen}",
            )
        with Scope("resources"):
            log(f"ti={self.ti} ax={self.ax}")
        with Scope("econ_targets"):
            log(
                f"ti_ore={self.ore_target} ax_ore={self.ax_ore_target} "
                f"off_ore={self.offensive_ore_target} "
                f"foundry={self.foundry_target}",
            )
            log(
                f"ti_sink={self.ti_sink} ax_sink={self.ax_sink} "
                f"dangling_output={self.dangling_output}",
            )
        with Scope("econ_sets"):
            log(
                f"dangling={len(self.dangling_set)} "
                f"unreachable_dangling={len(self.unreachable_dangling)} "
                f"reflect_queue={len(self.reflect_queue)}",
            )
            with Scope("dangling_set"):
                for p in sorted(
                    self.dangling_set,
                    key=lambda q: (q.y, q.x),
                ):
                    log(str(p))
            with Scope("unreachable_dangling"):
                for p in sorted(
                    self.unreachable_dangling,
                    key=lambda q: (q.y, q.x),
                ):
                    log(str(p))
            log(
                f"reaches_core={len(self.reaches_core)} "
                f"reaches_foundry={len(self.reaches_foundry)} "
                f"foundries={len(self.my_foundries)}",
            )
            log(
                f"ti_upstream={len(self.ti_upstream)} "
                f"ax_upstream={len(self.ax_upstream)} "
                f"upstream_of_dangling={len(self.upstream_of_dangling)} "
                f"upstream_of_congestion={len(self.upstream_of_congestion)}",
            )
            log(
                f"junctions={len(self.junctions)} "
                f"multi_input={len(self.is_multi_input)} "
                f"congested={len(self.congested_junctions)}",
            )
            log(
                f"ti_harv_adj={len(self.ti_harvester_adjacent)} "
                f"ax_harv_adj={len(self.ax_harvester_adjacent)} "
                f"adj_to_unconn_harv={len(self.adjacent_to_unconnected_harvester)}",
            )
        with Scope("offense"):
            log(
                f"target={self.offense_target} turns={self.offense_turns} "
                f"launcher={self.offense_launcher} "
                f"last_fire={self.last_fire}",
            )
            log(
                f"nearest_enemy_turret={self.nearest_enemy_turret} "
                f"enemy_ray_tiles={len(self.enemy_turret_ray_tiles)} "
                f"friendly_ray_tiles={len(self.friendly_turret_ray_tiles)} "
                f"adj_enemy_launcher={len(self.adjacent_to_enemy_launcher)} "
                f"attack_blacklist={len(self.attack_tile_blacklist)}",
            )
        with Scope("misc"):
            log(
                f"repair_pos={self.repair_pos} repaired_prev={self.repaired_prev} "
                f"scout={self.scout_target} scout_age={self.scout_age} "
                f"opportunistic={self.opportunistic}",
            )
            log(
                f"patrol_head={self.patrol_head} "
                f"patrol_trail={len(self.patrol_trail)} "
                f"deny_ore_neighbours={len(self.deny_ore_neighbours)}",
            )
            log(
                f"nearby_buildings={len(self.nearby_buildings)} "
                f"healable={len(self.healable_buildings)}",
            )

    def update_pnb(self, i: int) -> None:
        w, h = self.w, self.h
        cost_grid = self.cost_grid
        pnb = self.pnb
        cx, cy = i % MAX_WIDTH, i // MAX_WIDTH
        passable = cost_grid[i] is not INF
        pnb[i] = []
        if passable:
            for dx, dy in DIR8_DELTA:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h:
                    ni = ny * MAX_WIDTH + nx
                    if cost_grid[ni] is not INF:
                        pnb[i].append(ni)
        for dx, dy in DIR8_DELTA:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * MAX_WIDTH + nx
                if cost_grid[ni] is INF:
                    continue
                nb_list = pnb[ni]
                if passable:
                    if i not in nb_list:
                        nb_list.append(i)
                elif i in nb_list:
                    nb_list.remove(i)

    def find_core(self, ct: Controller) -> Position:
        for bid in ct.get_nearby_buildings():
            if (
                ct.get_team(bid) == self.my_team
                and ct.get_entity_type(bid) == EntityType.CORE
            ):
                return ct.get_position(bid)
        msg = "Core not visible at spawn"
        raise RuntimeError(msg)

    @override
    def __init__(self) -> None:
        """ct-independent heavy allocation. Runs in Player.__init__ (5s window)."""
        super().__init__()

        self.env: list[Environment | None] = [None] * MAX_N
        """Wall, Empty, Ti ore, Ax ore per tile."""
        self.building_ids: list[int | None] = [None] * MAX_N
        """Cached building entity ID per tile, for change detection."""
        self.buildings: list[Building | None] = [None] * MAX_N
        """Building on a tile."""
        self.hp: list[int] = [0] * MAX_N
        """Hitpoints of building on tile."""
        self.max_hp: list[int] = [0] * MAX_N
        """Max hitpoints of building on tile."""

        self.cost_grid: list[int] = [1] * MAX_N
        """Movement cost per tile. INF = impassable, 1 = road/walkable, ROAD_COST = empty."""

        # Conveyor routing decomposes cleanly into: (a) is the tile buildable
        # by us right now, (b) would routing resource R through it cause
        # contamination, (c) is the tile reachable from the builder at all.
        # (c) is bfs_dist-based and checked live in A*. (a) and (b) are
        # incremental bitmaps and are combined into ti_routable / ax_routable.
        self.buildable: list[bool] = [False] * MAX_N
        """True iff a conveyor/bridge/etc. could be placed on this tile now:
        empty terrain with no building, OR friendly road, OR any marker
        (markers are 1 HP and any team can overbuild). Maintained incrementally
        by `vision._update_cost`."""
        self.ti_leakage: list[bool] = [False] * MAX_N
        """True iff routing Ti through this tile would mix with Ax: tile is
        cardinal to an Ax harvester or a friendly foundry (foundry output is
        refined Ax)."""
        self.ax_leakage: list[bool] = [False] * MAX_N
        """True iff routing Ax through this tile would mix with Ti: tile is
        cardinal to a Ti harvester."""
        self.ti_routable: list[bool] = [False] * MAX_N
        """Combined: `buildable[i] and not ti_leakage[i]`. A\\* for Ti chains
        checks this plus `bfs_dist[i] is not INF`."""
        self.ax_routable: list[bool] = [False] * MAX_N
        """Combined: `buildable[i] and not ax_leakage[i]`. A\\* for Ax chains
        checks this plus `bfs_dist[i] is not INF`."""
        # Counts of leakage sources cardinal to each tile. ti_leakage[i] is
        # `_ax_harv_at[i] > 0 or _foundry_at[i] > 0`; ax_leakage[i] is
        # `_ti_harv_at[i] > 0`. Using counts avoids re-scanning cardinals on
        # every removal (multiple harvesters can share a cardinal neighbour).
        self._ti_harv_at: list[int] = [0] * MAX_N
        self._ax_harv_at: list[int] = [0] * MAX_N
        self._foundry_at: list[int] = [0] * MAX_N

        offsets = [dy * MAX_WIDTH + dx for dx, dy in DIR8_DELTA]
        pnb: list[list[int]] = [[] for _ in range(MAX_N)]
        for cy in range(1, MAX_WIDTH - 1):
            row = cy * MAX_WIDTH
            for cx in range(1, MAX_WIDTH - 1):
                i = row + cx
                pnb[i] = [i + o for o in offsets]
        for cy in range(MAX_WIDTH):
            row = cy * MAX_WIDTH
            for cx in range(MAX_WIDTH):
                if 1 <= cx < MAX_WIDTH - 1 and 1 <= cy < MAX_WIDTH - 1:
                    continue
                i = row + cx
                pnb[i] = [
                    ny * MAX_WIDTH + nx
                    for dx, dy in DIR8_DELTA
                    if 0 <= (nx := cx + dx) < MAX_WIDTH
                    and 0 <= (ny := cy + dy) < MAX_WIDTH
                ]
        self.pnb = pnb
        """Passable neighbours. Pre-built for full 50x50; fixed at actual-map
        boundary in post_init."""

        self.bfs_dist: Final[list[int]] = [INF] * MAX_N
        self.bfs_reset: Final[tuple[int, ...]] = (INF,) * MAX_N
        self.move_search: Final = MoveHeapAstar(self)
        self.conv_search: Final = AStarSearch(self)
        self.ax_conv_search: Final = AStarSearch(self)
        """Separate A* search instance for Ax chain routing. Shares the
        builder's state but keeps its own `_dist`/`_target`/`_finished` so the
        Ti search can't clobber Ax search progress (and vice versa)."""

        self.bug_state: WallFollow | None = None
        """Wall-following state for `bugnav` fallback. Persists across turns
        so a builder can resume tracing the obstacle it hit; reset whenever
        the navigation goal changes."""

        self.flow_history: list[deque[tuple[ResourceType | None, int | None]]] = [
            deque(maxlen=FLOW_HISTORY_LEN) for _ in range(MAX_N)
        ]
        """Last 8 rounds of (resource, stack_id) observed on this tile. The
        stack_id lets us detect congestion earlier: if the same id appears
        across consecutive ticks, that stack sat on the tile instead of
        moving, which is a backlog signal before the history even fills."""

        self.in_edges: list[list[Position]] = [[] for _ in range(MAX_N)]
        """Structural feeders: positions whose output (conveyor/armoured/
        bridge/splitter) lands on this tile. Flow presence/direction is
        read empirically from `flow_history`; this graph only tracks
        connectivity."""
        self.out_edges: list[list[Position]] = [[] for _ in range(MAX_N)]
        """Structural consumers: positions this tile's building outputs to.
        Mirrors `in_edges` so forward walks don't have to match on the
        building type."""

        self.symmetry_candidates: set[Symmetry] = set(Symmetry)
        """The current set of symmetry hypotheses."""
        self.symmetry: Symmetry | None = None
        """If `symmetry == {x}`, then this is `x`, otherwise `None`."""

        self.reflect_queue: deque[int] = deque()
        """At the moment symmetry is known, existing tiles in memory have to be reflected.
        To prevent a huge spike, we process only a limited number per turn.
        """

        # Ephemeral (recomputed each turn)

        self.nearby_buildings: list[Position] = []
        self.healable_buildings: list[Position] = []
        self.adjacent_to_unconnected_harvester: set[Position] = set()
        self.adjacent_to_harvester: set[Position] = set()
        self.ti_harvester_adjacent: set[Position] = set()
        """Tiles cardinally adjacent to a Ti harvester (any team). Ax chain
        routing should avoid these tiles — Ti would leak into the Ax stream."""
        self.ax_harvester_adjacent: set[Position] = set()
        """Cardinal-neighbours of Ax harvesters. Ti chains avoid these."""
        self.reaches_core: set[Position] = set()
        """Tiles whose flow eventually reaches the core. Computed per turn by
        a DFS backwards from the core over `in_edges`. O(1) membership test
        replaces the per-candidate downstream BFS."""
        self.reaches_foundry: set[Position] = set()
        """Tiles whose flow eventually reaches any friendly foundry. Same
        mechanism as reaches_core but seeded from each observed foundry."""
        self.ti_upstream: set[Position] = set()
        """Transport tiles fed (transitively) by some friendly Ti harvester.
        Forward flood from `ti_harvester_adjacent` per turn. Replaces
        per-tile `chain_ore_kinds` BFS for Ti presence."""
        self.ax_upstream: set[Position] = set()
        """Transport tiles fed (transitively) by some friendly Ax harvester.
        Forward flood from `ax_harvester_adjacent` per turn. Replaces
        per-tile `chain_ore_kinds` BFS for Ax presence."""
        self.upstream_of_dangling: set[Position] = set()
        """Transport tiles whose flow eventually lands on any known dangling
        tile. Universal filter for sink picking — routing to any tile in
        here forms an island terminating at an unbuilt chain tip."""
        self.congested_junctions: set[Position] = set()
        """Junctions where total feeder inflow exceeds the junction's
        single-tile pass-through — the root cause of congestion. Computed
        per turn by scanning nearby multi-feeder tiles; everything upstream
        back-pressures from here."""
        self.upstream_of_congestion: set[Position] = set()
        """Transport tiles whose flow leads into a congested junction. Union
        of upstream trees of `congested_junctions`. Used to reject Ti-sink
        candidates and to identify conveyors worth upgrading into splitters."""
        self.my_foundries: set[Position] = set()
        """Friendly foundry positions. Maintained incrementally in vision
        update (`_add_topology`/`_remove_topology`) so `update_economy_reachability`
        and `update_foundry_target` don't need full-map scans."""
        self.is_multi_input: set[Position] = set()
        """Tiles with >= 2 feeders (`len(in_edges[i]) >= 2`). Maintained
        incrementally in `_add_topology`/`_remove_topology`. Superset of
        potential foundry junctions — filtered by Ti+Ax feeder kinds into
        `self.junctions`."""
        self.junctions: set[Position] = set()
        """Friendly conveyor/armoured tiles that qualify as foundry sites:
        multi-input AND have at least one Ti-only feeder AND at least one
        Ax-only feeder. Recomputed once per turn after
        `update_economy_reachability` (ti_upstream / ax_upstream)."""
        # Experimental: BFS-skip push/set split (bench_nav navbfs style).
        # A cardinal bracketed by two passable flanking diagonals can be
        # reached at the same BFS level through either diagonal, so we
        # only need to assign its distance, not enqueue it. Maintained
        # lazily in `update_pnb` for the 9-tile neighbourhood around every
        # passability change.
        self.adjacent_to_enemy_launcher: set[Position] = set()

        self.enemy_turret_ray_tiles: set[Position] = set()
        """Tiles that are in the forward firing ray of an enemy gunner
        or sentinel. Populated per-turn in state_update_map when a
        visible enemy turret is encountered. Used as a soft cost
        penalty in cost_grid so move_search routes bots around them.
        """

        self.friendly_turret_ray_tiles: set[Position] = set()
        """Forward firing ray of FRIENDLY gunners/sentinels. Walking
        into one blocks our own shot for that turn — same soft
        penalty keeps bots off their own turrets' kill lanes.
        """

        self.deny_ore_neighbours: set[Position] = set()
        """Ore-denial tiles: for ores in our vision whose cardinal-8
        halo contains an enemy bot or building, the ore's 4 cardinal
        neighbours are candidate road-placement tiles. We pave them
        with cheap roads (1 Ti base) to deny the enemy a harvester
        feed position before they get one built.
        """

        self.nearest_enemy_turret: Position | None = None

        # Role
        self.role: Role | None = None
        self.role_age: int = 0
        self.permanent_role: bool = False

        # Economy
        self.ore_target: Position | None = None
        self.ax_ore_target: Position | None = None
        self.offensive_ore_target: Position | None = None
        """Ti ore tile on the enemy side of the map (more than r²=20 closer
        to their core than ours) that this builder claims for an offensive
        harvester. Seed for forward dangling chains."""
        self.foundry_target: Position | None = None
        """Ti conveyor tile chosen to be REPLACED by a new foundry. Only set
        when no existing Ax chain or foundry is available as a sink. When set,
        equals `ax_sink`. `run_foundry` destroys the conveyor and places the
        foundry on it as the last step. None if Ax chains should route to an
        existing foundry or Ax chain instead (no new foundry needed)."""
        self.ax_sink: Position | None = None
        """Where Ax chains should route. Preference order (closest-by-dist
        within each tier, try next tier if current is empty):
        1. An existing friendly Ax chain tile whose downstream reaches a
           foundry — merge and share the existing foundry.
        2. An existing friendly foundry — feed directly from another side.
        3. A pure-Ti conveyor foundry candidate — triggers `run_foundry`
           to place a new foundry once the Ax chain connects."""
        self.ti_sink: Position | None = None
        """Where Ti chains should route. Prefers the nearest Ti-carrying
        friendly conveyor (so new Ti harvesters merge into the existing chain),
        falling back to the core when no Ti conveyor is closer. Falls back to
        None → `my_core` so the very first harvester still routes correctly."""
        self.dangling_set: set[Position] = set()
        """Reachable loose-end tiles this builder knows about. Maintained
        incrementally via topology hooks (`_add_topology`, `_remove_topology`,
        `_check_dangling`) and via harvester-adjacency changes. Persistent
        across vision loss: entries stay until topology contradicts them.
        Disjoint from `unreachable_dangling`."""
        self.unreachable_dangling: set[Position] = set()
        """Dangling tiles the BFS has proven unreachable (bfs_dist is INF).
        Typically created when a bridge's landing sits inside an enclosed
        pocket. The `DESTROY_DEAD_BRIDGE` task walks upstream from these
        to the offending bridge and destroys it. Disjoint from
        `dangling_set`; migration happens in `update_unreachable_dangling`
        after each turn's BFS."""
        self.dangling_output: Position | None = None
        """The dangling tile this builder is currently committed to. Picked
        from `dangling_set`; stays put until it leaves the set."""

        # Repair
        self.repair_pos: Position | None = None
        self.repaired_prev: bool = True

        # Offense
        self.en_core_seen: bool = False
        self.offense_target: Position | None = None
        self.offense_turns: int = 0
        self.offense_launcher: Position | None = None

        self.last_fire: tuple[Position, int] | None = None
        """Track the tile we last fired at, plus the HP we expected to
        see on the building there NEXT turn (i.e. pre-fire HP minus
        our 2 dmg). If we revisit and the tile's current HP is
        higher than that expectation, an enemy builder healed it —
        concrete evidence we're being out-healed on this tile.
        """

        self.attack_tile_blacklist: dict[Position, int] = {}
        """Tiles we just got out-healed on: {tile: remaining_turns}.
        Decremented at the top of run_attack; _pick_attack_destination
        skips any entry still present. Stops the bounce loop where
        we rotate around the same harvester's neighbours turn after
        turn because the picker keeps picking one of a handful of
        valid tiles and a nearby enemy builder just heals us off it.
        """

        # Patrol
        self.patrol_head: Position | None = None
        self.patrol_trail: list[Position] = []

        # Scouting
        self.scout_target: Position | None = None
        self.scout_age: int = 0
        self.scout_radius: float = 10.0

    @override
    def post_init(self, ct: Controller) -> None:
        super().post_init(ct)
        self.opportunistic: bool = self.rng.random() < 0.5

        core = find_core(ct, self.my_team)
        if HARDCODE and core is not None:
            self.known_map = identify_map(self.w, self.h, core)
        else:
            self.known_map = None
        self.my_core = (
            core
            if core is not None
            else (
                core_for(self.known_map, self.my_team)
                if self.known_map is not None
                else Position(0, 0)
            )
        )

        # The 8 perimeter tiles of the core's 3x3 block (edges + corners,
        # excluding the center). These are the tiles a conveyor outside the
        # core can target to deliver Ti; an external conveyor can't reach
        # the center because all of its cardinal neighbours are core tiles
        # too. Used as Ti-sink candidates in update_ti_sink.
        cx, cy = self.my_core.x, self.my_core.y
        self.core_edges: tuple[Position, ...] = tuple(self.my_core.add(d) for d in DIR8)

        with Scope("pnb", time=True):
            # `__init__` built pnb assuming a full MAX_WIDTH x MAX_WIDTH grid.
            # The real map is anchored at (0, 0)..(w-1, h-1); the x=0 and y=0
            # edges already got correct boundary handling in `__init__`. Only
            # the x=w-1 column and y=h-1 row were built as interior there, so
            # they contain out-of-real-map neighbours. Fix just those w + h - 1
            # tiles (the shared corner is patched once).
            w, h = self.w, self.h

            def _fix(cx: int, cy: int) -> None:
                self.pnb[cy * MAX_WIDTH + cx] = [
                    ny * MAX_WIDTH + nx
                    for dx, dy in DIR8_DELTA
                    if 0 <= (nx := cx + dx) < w and 0 <= (ny := cy + dy) < h
                ]

            for cx in range(w):
                _fix(cx, h - 1)
            for cy in range(h - 1):
                _fix(w - 1, cy)

        if self.known_map is not None:
            with Scope("hardcode", time=True):
                self.symmetry = SYMMETRY[self.known_map]
                self.symmetry_candidates = {self.symmetry}
                tiles = decode(TILES[self.known_map](), w * h)
                env = self.env
                cost_grid = self.cost_grid
                buildable = self.buildable
                ti_routable = self.ti_routable
                ax_routable = self.ax_routable
                for y in range(h):
                    row = y * MAX_WIDTH
                    src = y * w
                    for x in range(w):
                        i = row + x
                        e = tiles[src + x]
                        env[i] = e
                        if e == Environment.WALL:
                            cost_grid[i] = INF
                            buildable[i] = False
                            ti_routable[i] = False
                            ax_routable[i] = False
                        else:
                            cost_grid[i] = 3  # ROAD_COST
                            is_empty = e == Environment.EMPTY
                            buildable[i] = is_empty
                            # No harvesters or foundries seeded yet, so leakage is
                            # all-False; routable collapses to buildable.
                            ti_routable[i] = is_empty
                            ax_routable[i] = is_empty
                with Scope("pnb", time=True):
                    for y in range(h):
                        row = y * MAX_WIDTH
                        for x in range(w):
                            if env[row + x] == Environment.WALL:
                                self.update_pnb(row + x)

    def get_env(self, pos: Position) -> Environment | None:
        return self.env[self.idx(pos)]

    def get_building(self, pos: Position) -> Building | None:
        return self.buildings[self.idx(pos)]

    def get_cost(self, pos: Position) -> int:
        return self.cost_grid[self.idx(pos)]

    def is_passable(self, pos: Position) -> bool:
        return self.cost_grid[self.idx(pos)] is not INF

    def is_walkable(self, pos: Position) -> bool:
        return self.is_passable(pos) and isinstance(
            self.buildings[self.idx(pos)],
            BuildingConveyor
            | BuildingRoad
            | BuildingSplitter
            | BuildingArmouredConveyor
            | BuildingBridge,
        )

    def get_in_edges(self, pos: Position) -> list[Position]:
        return self.in_edges[self.idx(pos)]

    def get_out_edges(self, pos: Position) -> list[Position]:
        return self.out_edges[self.idx(pos)]

    def is_buildable(self, pos: Position) -> bool:
        i = self.idx(pos)
        b = self.buildings[i]
        return self.env[i] != Environment.WALL and (b is None or b.team == self.my_team)

    def is_friendly_turret(self, pos: Position) -> bool:
        b = self.buildings[self.idx(pos)]
        if b is None or isinstance(
            b,
            BuildingConveyor
            | BuildingRoad
            | BuildingSplitter
            | BuildingArmouredConveyor
            | BuildingBridge,
        ):
            return False
        return b.team == self.my_team

    def is_enemy_building(self, pos: Position) -> bool:
        b = self.buildings[self.idx(pos)]
        return b is not None and b.team != self.my_team

    def leads_to_enemy_building(self, pos: Position) -> bool:
        b = self.buildings[self.idx(pos)]
        if b is None or b.team != self.my_team:
            return False
        match b:
            case BuildingConveyor(direction=d):
                output_location = pos.add(d)
            case BuildingBridge(target=t):
                output_location = t
            case _:
                return False
        if not self.in_bounds(output_location):
            return False
        return self.is_enemy_building(output_location)

    update = update
    prune_stale = prune_stale
    update_vision = update_vision
    update_markers = update_markers
    update_reflect = update_reflect
    update_bfs = update_bfs
    extract_path = extract_path
    update_ore_denial = update_ore_denial
    update_enemy_turrets = update_enemy_turrets
    update_role = update_role
    update_map_econ = update_map_econ
    update_unreachable_dangling = update_unreachable_dangling
    update_dangling = update_dangling
    update_ore_target = update_ore_target
    update_ax_ore_target = update_ax_ore_target
    update_offensive_ore_target = update_offensive_ore_target
    update_foundry_target = update_foundry_target
    update_ti_sink = update_ti_sink
    update_economy_reachability = update_economy_reachability
    update_junctions = update_junctions
    can_place_junction = can_place_junction
    end_of_turn_heal = end_of_turn_heal
    end_of_turn_propagate_symmetry = end_of_turn_propagate_symmetry
    indicators = indicators
    dump = dump

    @override
    def run(self, ct: Controller) -> None:
        super().run(ct)
        log(
            f"====== Builder {self.my_id} starting turn {self.round}: "
            f"currently at {self.my_pos}, team has ti={self.ti} ax={self.ax}, ",
        )
        self.update(ct)
        begin_turn_offense(self, ct)
        self._log_state()

        if DEBUG_DUMP:
            self.dump(ct)

        assert self.role is not None
        with Scope("tasks", time=True):
            for task in POLICIES[self.role]:
                with Scope(f"task={task}", time=True):
                    try:
                        task.run(self, ct)
                    except Exception as exc:
                        if not isinstance(exc, TaskRejectedError):
                            raise
                        log(f"rejected: {type(exc).__name__}: {exc}")
                        continue
                    break
        with Scope("hooks"):
            with Scope("indicators"):
                self.indicators(ct)
            if self.role != Role.OFFENSE:
                with Scope("heal"):
                    self.end_of_turn_heal(ct)
            with Scope("symmetry"):
                self.end_of_turn_propagate_symmetry(ct)
