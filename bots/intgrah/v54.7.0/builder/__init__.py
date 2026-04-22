from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Final, override

from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingRoad,
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
from util.constants import INF, MAX_N, MAX_WIDTH
from util.directions import DIR8, DIR8_DELTA
from util.debug import Scope, debug as log, dot
from util.symmetry import Symmetry

from builder.algorithms.astar import MoveHeapAstar
from builder.algorithms.bfs import extract_path, update_bfs
from builder.algorithms.econ_astar import AStarSearch
from builder.dump import dump
from builder.role import Role
from builder.tasks import POLICIES, Task
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
    update_ore_target,
    update_ti_sink,
)
from builder.update.prune import prune_stale
from builder.update.role import update_role
from builder.update.turrets import update_enemy_turrets, update_ore_denial
from builder.update.vision import update_vision

if TYPE_CHECKING:
    from building import Building


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
        `ax_leakage` / `ax_routable` on them."""
        cx, cy = pos.x, pos.y
        w, h = self.w, self.h
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * MAX_WIDTH + nx
                self._ti_harv_at[ni] += delta
                self._refresh_ax_leakage(ni)

    def _bump_ax_harv(self, pos: Position, delta: int) -> None:
        cx, cy = pos.x, pos.y
        w, h = self.w, self.h
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * MAX_WIDTH + nx
                self._ax_harv_at[ni] += delta
                self._refresh_ti_leakage(ni)

    def _bump_foundry(self, pos: Position, delta: int) -> None:
        cx, cy = pos.x, pos.y
        w, h = self.w, self.h
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * MAX_WIDTH + nx
                self._foundry_at[ni] += delta
                self._refresh_ti_leakage(ni)

    def _check_multi_input(self, t: Position) -> None:
        """Call after `conveyors_to_here[idx(t)]` or `splitters_to_here[idx(t)]`
        is mutated. Adds/removes t from `is_multi_input` based on the current
        total feeder count."""
        idx = t.y * MAX_WIDTH + t.x
        count = len(self.conveyors_to_here[idx]) + len(self.splitters_to_here[idx])
        if count >= 2:
            self.is_multi_input.add(t)
        else:
            self.is_multi_input.discard(t)

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

        self.flow_history: list[deque[tuple[ResourceType | None, int | None]]] = [
            deque(maxlen=8) for _ in range(MAX_N)
        ]
        """Last 8 rounds of (resource, stack_id) observed on this tile. The
        stack_id lets us detect congestion earlier: if the same id appears
        across consecutive ticks, that stack sat on the tile instead of
        moving, which is a backlog signal before the history even fills."""

        self.conveyors_to_here: list[list[Position]] = [[] for _ in range(MAX_N)]
        self.splitters_to_here: list[list[Position]] = [[] for _ in range(MAX_N)]

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
        a DFS backwards from the core over conveyors_to_here/splitters_to_here.
        O(1) membership test replaces the per-candidate downstream BFS."""
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
        self.my_foundries: set[Position] = set()
        """Friendly foundry positions. Maintained incrementally in vision
        update (`_add_topology`/`_remove_topology`) so `update_economy_reachability`
        and `update_foundry_target` don't need full-map scans."""
        self.is_multi_input: set[Position] = set()
        """Tiles with >= 2 feeders (count of `conveyors_to_here[i]` +
        `splitters_to_here[i]`). Maintained incrementally in
        `_add_topology`/`_remove_topology`. Superset of potential foundry
        junctions — filtered by Ti+Ax feeder kinds into `self.junctions`."""
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
        self.pending_bridge: Position | None = None
        self.dangling_output: Position | None = None

        # Repair
        self.repair_pos: Position | None = None
        self.repaired_prev: bool = True

        # Offense
        self.en_core: bool = False
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
        self.core_edges: tuple[Position, ...] = tuple(
            Position(cx + dx, cy + dy)
            for dx, dy in DIR8_DELTA
            if 0 <= cx + dx < self.w and 0 <= cy + dy < self.h
        )

        ct.get_cpu_time_elapsed()

        # pnb and pnb_push/pnb_set were pre-built for full MAX_WIDTH ×
        # MAX_WIDTH. Fix the actual-map boundary so that in-map tiles don't
        # reference out-of-map neighbours.
        w, h = self.w, self.h
        for cy in range(h):
            row = cy * MAX_WIDTH
            for cx in range(w):
                if cx < w - 1 and cy < h - 1 and cx > 0 and cy > 0:
                    continue
                i = row + cx
                self.pnb[i] = [
                    ny * MAX_WIDTH + nx
                    for dx, dy in DIR8_DELTA
                    if 0 <= (nx := cx + dx) < w and 0 <= (ny := cy + dy) < h
                ]

        ct.get_cpu_time_elapsed()

        # self.conv_search.post_init()

        ct.get_cpu_time_elapsed()

        if self.known_map is not None:
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

    def get_conveyors_to_here(self, pos: Position) -> list[Position]:
        return self.conveyors_to_here[self.idx(pos)]

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
    update_bfs = update_bfs
    extract_path = extract_path
    update_ore_denial = update_ore_denial
    update_enemy_turrets = update_enemy_turrets
    update_role = update_role
    update_map_econ = update_map_econ
    update_dangling = update_dangling
    update_ore_target = update_ore_target
    update_ax_ore_target = update_ax_ore_target
    update_foundry_target = update_foundry_target
    update_ti_sink = update_ti_sink
    update_economy_reachability = update_economy_reachability
    update_junctions = update_junctions
    can_place_junction = can_place_junction
    dump = dump

    def draw_debug(self, ct: Controller) -> None:
        """Paint per-builder economy state into the replay: ore targets,
        foundry target, chain endpoints. Only has effect when DEBUG_LOG is set
        (the helpers in `util.log` are no-ops otherwise)."""
        if self.ore_target is not None:
            dot(ct, self.ore_target, 255, 220, 0)  # Ti ore target: yellow
        if self.ax_ore_target is not None:
            dot(ct, self.ax_ore_target, 200, 0, 200)  # Ax ore target: magenta
        if self.foundry_target is not None:
            dot(ct, self.foundry_target, 0, 200, 0)  # foundry target: green
        if self.dangling_output is not None:
            dot(ct, self.dangling_output, 0, 200, 200)  # dangling: cyan

    @override
    def run(self, ct: Controller) -> None:
        super().run(ct)
        t0 = ct.get_cpu_time_elapsed()
        log(
            f"====== Builder {self.my_id} starting turn {self.round}: "
            f"currently at {self.my_pos}, team has ti={self.ti} ax={self.ax}, "
            f"team scale={self.scale:.2f} ======",
        )
        self.update(ct)
        log(
            f"After update, builder {self.my_id} has: "
            f"Ti ore target = {self.ore_target}, "
            f"Ax ore target = {self.ax_ore_target}, "
            f"foundry target = {self.foundry_target}, "
            f"dangling chain tip = {self.dangling_output}",
        )

        self.draw_debug(ct)

        if DEBUG_DUMP:
            self.dump(ct)

        t1 = ct.get_cpu_time_elapsed()
        chosen: Task | None = None
        assert self.role is not None
        for task in POLICIES[self.role]:
            with Scope(f"task={task}"):
                try:
                    task.run(self, ct)
                except Exception as exc:
                    if not isinstance(exc, TaskRejectedError):
                        raise
                    log(f"rejected: {type(exc).__name__}: {exc}")
                    continue
                chosen = task
                break

        if self.role != Role.OFFENSE:
            self.end_of_turn_heal(ct)

        t2 = ct.get_cpu_time_elapsed()
        log(f"task={t2 - t1}us [{chosen}]")
        log(f"total={t2 - t0}us")

    def end_of_turn_heal(self, ct: Controller) -> None:
        my_pos = ct.get_position()
        if ct.can_heal(my_pos) and ct.get_hp() < ct.get_max_hp():
            ct.heal(my_pos)
        for unit in ct.get_nearby_units():
            if ct.get_team(unit) != self.my_team:
                continue
            if ct.get_hp(unit) >= ct.get_max_hp(unit):
                continue
            if ct.get_entity_type(unit) == EntityType.CORE:
                for d in DIR8:
                    heal_pos = ct.get_position(unit).add(d)
                    if ct.can_heal(heal_pos):
                        ct.heal(heal_pos)
                        break
            elif ct.can_heal(ct.get_position(unit)):
                ct.heal(ct.get_position(unit))
