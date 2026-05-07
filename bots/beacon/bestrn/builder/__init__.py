"""
Translation of `bots/intgrah/v54.7.9/builder/__init__.py`.

`Builder` is the bot's most complex unit — it owns map belief, conveyor
routing graphs, navigation state, role/task scheduling, and per-turn
ephemeral sets. Submodules implement the algorithms (`algorithms/`),
per-turn updates (`update/`), end-of-turn hooks (`hooks/`), and the
task-policy tree (`tasks/`); this file wires them together.
"""

from __future__ import annotations

from unit import in_bounds
from cambc import EntityType, Environment, GameConstants, Position
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller, ControllerApi, ResourceType
from builder.algorithms.econ_astar import AStarSearch
from builder.dump import dump
from builder.algorithms.econ_astar import EconAstarCtx
from builder.algorithms.nav import BugNav, NavCtx
from builder.algorithms.reachability import find_ro, update_reachability
from builder.hooks.heal import end_of_turn_heal
from builder.hooks.indicators import indicators
from builder.hooks.propagate_symmetry import end_of_turn_propagate_symmetry

if TYPE_CHECKING:
    from builder.role import Role
from builder.tasks._policy import run_policy
from builder.tasks.offense.helpers import begin_turn_offense
from builder.tasks import policy_for_role
from builder.update import update
from builder.update.vision import apply_local_destroy as vision_apply_local_destroy
from config import DEBUG_DUMP, HARDCODE
from hardcode.identify import identify_map

if TYPE_CHECKING:
    from hardcode.identify import KnownMap
from unit import UnitState
from util.constants import INF, MAX_N, MAX_WIDTH, ROAD_COST
from util.debug import Scope, debug as log
from util.directions import DIR4, DIR8, DIR8_DELTA
from util.symmetry import Symmetry
from util.visualiser import auto_wrap_position

if TYPE_CHECKING:
    from cambc import Team


class Builder:
    """
    The Builder unit. Embeds `UnitState` (auto-Deref'd so `builder.my_pos`
    resolves transparently) plus per-builder map belief, navigation state,
    economy bookkeeping, role state, and offense/heal trackers.
    """

    state: UnitState
    my_core: Position
    en_core_guess: Position
    symmetry: Symmetry | None
    env: list[Environment | None]
    building_ids: list[int | None]
    building_kind: list[EntityType | None]
    building_team: list[Team | None]
    hp: list[int]
    max_hp: list[int]
    cost_grid: list[int]
    _threat_bumped: set[int]
    buildable: list[bool]
    ti_leakage: list[bool]
    ax_leakage: list[bool]
    ti_routable: list[bool]
    ax_routable: list[bool]
    routing_extra: list[int]
    _ti_harv_at: list[int]
    _ax_harv_at: list[int]
    _foundry_at: list[int]
    _ti_in_count: list[int]
    _ax_in_count: list[int]
    pnb: list[list[int]]
    reach_parent: list[int]
    reach_frontier: list[int]
    conv_search: AStarSearch
    ax_conv_search: AStarSearch
    bugnav: BugNav
    flow_history: list[list[tuple[ResourceType | None, int | None]]]
    in_edges: list[list[Position]]
    out_edges: list[list[Position]]
    reflect_queue: list[int]
    nearby_buildings: list[Position]
    healable_buildings: list[Position]
    adjacent_to_unconnected_harvester: set[Position]
    adjacent_to_harvester: set[Position]
    ti_harvester_adjacent: set[Position]
    ax_harvester_adjacent: set[Position]
    reaches_core: set[Position]
    reaches_foundry: set[Position]
    ti_upstream: set[Position]
    ax_upstream: set[Position]
    upstream_of_dangling: set[Position]
    congested_junctions: set[Position]
    upstream_of_congestion: set[Position]
    my_foundries: set[Position]
    visible_ti_ores: set[Position]
    visible_ax_ores: set[Position]
    my_harvesters: set[Position]
    is_multi_input: set[Position]
    junctions: set[Position]
    adjacent_to_enemy_launcher: set[Position]
    enemy_turret_ray_tiles: set[Position]
    friendly_turret_ray_tiles: set[Position]
    deny_ore_neighbours: set[Position]
    nearest_enemy_turret: Position | None
    role: Role | None
    role_age: int
    ore_target: Position | None
    ax_ore_target: Position | None
    offensive_ore_target: Position | None
    foundry_target: Position | None
    ax_sink: Position | None
    ti_sink: Position | None
    dangling_set: set[Position]
    unreachable_dangling: set[Position]
    dangling_output: Position | None
    repair_pos: Position | None
    repaired_prev: bool
    en_core_seen: bool
    offense_target: Position | None
    offense_turns: int
    offense_launcher: Position | None
    last_fire: tuple[Position, int] | None
    attack_tile_blacklist: dict[Position, int]
    patrol_head: Position | None
    last_seen: list[int]
    _vision_offsets: list[tuple[int, int, int]]
    explore_target: Position | None
    explore_heading: tuple[int, int] | None
    opportunistic: bool
    econ_radius_sq: int
    known_map: KnownMap | None
    core_edges: list[Position]

    def __init__(self):
        """ct-independent allocation. Mirrors Python `Builder.__init__`."""
        pnb = Builder.build_initial_pnb()
        flow_history: list[list[tuple[ResourceType | None, int | None]]] = [
            [] for _ in range(MAX_N)
        ]
        in_edges: list[list[Position]] = [[] for _ in range(MAX_N)]
        out_edges: list[list[Position]] = [[] for _ in range(MAX_N)]
        vision_offsets: list[tuple[int, int, int]] = []
        for dx in range(-4, (4) + 1):
            for dy in range(-4, (4) + 1):
                if dx * dx + dy * dy <= GameConstants.BUILDER_BOT_VISION_RADIUS_SQ:
                    vision_offsets.append((dx, dy, dy * int(50) + dx))
        self.state = UnitState()
        self.my_core = Position(x=0, y=0)
        self.en_core_guess = Position(x=0, y=0)
        self.symmetry = None
        self.env = [None] * MAX_N
        self.building_ids = [None] * MAX_N
        self.building_kind = [None] * MAX_N
        self.building_team = [None] * MAX_N
        self.hp = [0] * MAX_N
        self.max_hp = [0] * MAX_N
        self.cost_grid = [3] * MAX_N
        self._threat_bumped = set()
        self.buildable = [False] * MAX_N
        self.ti_leakage = [False] * MAX_N
        self.ax_leakage = [False] * MAX_N
        self.ti_routable = [False] * MAX_N
        self.ax_routable = [False] * MAX_N
        self.routing_extra = [0] * MAX_N
        self._ti_harv_at = [0] * MAX_N
        self._ax_harv_at = [0] * MAX_N
        self._foundry_at = [0] * MAX_N
        self._ti_in_count = [0] * MAX_N
        self._ax_in_count = [0] * MAX_N
        self.pnb = pnb
        self.reach_parent = [-1] * MAX_N
        self.reach_frontier = []
        self.conv_search = AStarSearch()
        self.ax_conv_search = AStarSearch()
        self.bugnav = BugNav()
        self.flow_history = flow_history
        self.in_edges = in_edges
        self.out_edges = out_edges
        self.reflect_queue = []
        self.nearby_buildings = []
        self.healable_buildings = []
        self.adjacent_to_unconnected_harvester = set()
        self.adjacent_to_harvester = set()
        self.ti_harvester_adjacent = set()
        self.ax_harvester_adjacent = set()
        self.reaches_core = set()
        self.reaches_foundry = set()
        self.ti_upstream = set()
        self.ax_upstream = set()
        self.upstream_of_dangling = set()
        self.congested_junctions = set()
        self.upstream_of_congestion = set()
        self.my_foundries = set()
        self.visible_ti_ores = set()
        self.visible_ax_ores = set()
        self.my_harvesters = set()
        self.is_multi_input = set()
        self.junctions = set()
        self.adjacent_to_enemy_launcher = set()
        self.enemy_turret_ray_tiles = set()
        self.friendly_turret_ray_tiles = set()
        self.deny_ore_neighbours = set()
        self.nearest_enemy_turret = None
        self.role = None
        self.role_age = 0
        self.ore_target = None
        self.ax_ore_target = None
        self.offensive_ore_target = None
        self.foundry_target = None
        self.ax_sink = None
        self.ti_sink = None
        self.dangling_set = set()
        self.unreachable_dangling = set()
        self.dangling_output = None
        self.repair_pos = None
        self.repaired_prev = True
        self.en_core_seen = False
        self.offense_target = None
        self.offense_turns = 0
        self.offense_launcher = None
        self.last_fire = None
        self.attack_tile_blacklist = {}
        self.patrol_head = None
        self.last_seen = [0] * MAX_N
        self._vision_offsets = vision_offsets
        self.explore_target = None
        self.explore_heading = None
        self.opportunistic = False
        self.econ_radius_sq = 0
        self.known_map = None
        self.core_edges = [Position(x=0, y=0)] * 8

    def __getattr__(self, name):
        return getattr(self.state, name)

    @staticmethod
    def default():
        return Builder()

    @staticmethod
    def build_initial_pnb():
        pnb: list[list[int]] = [[] for _ in range(MAX_N)]
        stride = int(50)
        offsets: list[int] = list((t[1] * stride + t[0] for t in DIR8_DELTA))
        for cy in range(1, int(50) - 1):
            row = cy * stride
            for cx in range(1, int(50) - 1):
                i = int(row + cx)
                pnb[i] = list((int(i) + o for o in offsets))
        for cy in range(0, int(50)):
            row = cy * stride
            for cx in range(0, int(50)):
                if (cx in range(1, int(50) - 1)) and (cy in range(1, int(50) - 1)):
                    continue
                i = int(row + cx)
                nbs: list[int] = []
                for dx, dy in DIR8_DELTA:
                    nx = cx + dx
                    ny = cy + dy
                    if (nx in range(0, int(50))) and (ny in range(0, int(50))):
                        nbs.append(ny * stride + nx)
                pnb[i] = nbs
        return pnb

    def update_pnb(self, i):
        """
        Recompute `pnb[i]` and the relevant entries of every neighbour after
        tile i's passability changed. Mirrors Python `Builder.update_pnb`.
        """
        w = self.state.width
        h = self.state.height
        cx = int(i % 50)
        cy = int(i // 50)
        passable = self.cost_grid[i] != 1000000
        self.pnb[i].clear()
        if passable:
            for dx, dy in DIR8_DELTA:
                nx = cx + dx
                ny = cy + dy
                if (nx in range(0, w)) and (ny in range(0, h)):
                    ni = int(ny) * 50 + int(nx)
                    if self.cost_grid[ni] != 1000000:
                        self.pnb[i].append(int(ni))
        for dx, dy in DIR8_DELTA:
            nx = cx + dx
            ny = cy + dy
            if not ((nx in range(0, w)) and (ny in range(0, h))):
                continue
            ni = int(ny) * 50 + int(nx)
            if self.cost_grid[ni] == 1000000:
                continue
            nb_list = self.pnb[ni]
            if passable:
                if not (int(i) in nb_list):
                    nb_list.append(int(i))
            else:
                p = next((__i for __i, x in enumerate(nb_list) if x == int(i)), None)
                if p is not None:
                    (nb_list.__setitem__(p, nb_list[-1]) or nb_list.pop())

    def idx(self, pos):
        """
        Position to flat index (inherent shadow of `Unit::idx` so peer code
        in `crate::builder::*` doesn't need to import the trait).
        """
        return int(pos.y) * 50 + int(pos.x)

    def in_bounds(self, pos):
        """In-bounds check (inherent shadow of `Unit::in_bounds`)."""
        return (
            pos.x >= 0
            and pos.x < self.state.width
            and pos.y >= 0
            and pos.y < self.state.height
        )

    def symmetry_guess(self):
        """Inherent shadow of `Unit::symmetry_guess`."""
        for sym in [Symmetry.Rot, Symmetry.Ver, Symmetry.Hor]:
            if sym in self.state.symmetry_candidates:
                return sym
        return Symmetry.Rot

    def get_env(self, pos):
        return self.env[self.idx(pos)]

    def get_building(self, pos):
        """Kind + team at `pos`, or `None` if no building / not in vision."""
        i = self.idx(pos)
        kind = self.building_kind[i]
        team = self.building_team[i]
        return (kind, team) if (kind is not None) and (team is not None) else None

    def kind_at(self, pos):
        return self.building_kind[self.idx(pos)]

    def team_at(self, pos):
        return self.building_team[self.idx(pos)]

    def get_cost(self, pos):
        return self.cost_grid[self.idx(pos)]

    def is_passable(self, pos):
        return self.cost_grid[self.idx(pos)] != 1000000

    def is_reachable(self, pos):
        i = int(self.idx(pos))
        my_i = self.state.my_pos.y * int(50) + self.state.my_pos.x
        if self.reach_parent[int(i)] == -1 or self.reach_parent[int(my_i)] == -1:
            return False
        return find_ro(self.reach_parent, i) == find_ro(self.reach_parent, my_i)

    def is_walkable(self, pos):
        if not self.cost_grid[self.idx(pos)] != 1000000:
            return False
        return (self.building_kind[self.idx(pos)] is not None) and (
            self.building_kind[self.idx(pos)] == EntityType.CONVEYOR
            or self.building_kind[self.idx(pos)] == EntityType.ROAD
            or self.building_kind[self.idx(pos)] == EntityType.SPLITTER
            or self.building_kind[self.idx(pos)] == EntityType.ARMOURED_CONVEYOR
            or self.building_kind[self.idx(pos)] == EntityType.BRIDGE
        )

    def get_in_edges(self, pos):
        return list(self.in_edges[self.idx(pos)])

    def get_out_edges(self, pos):
        return list(self.out_edges[self.idx(pos)])

    def is_buildable(self, pos):
        i = self.idx(pos)
        return self.env[i] != Environment.WALL and (
            (self.building_team[i] is None)
            or self.building_team[i] == self.state.my_team
        )

    def is_friendly_turret(self, pos):
        i = self.idx(pos)
        kind = self.building_kind[i]
        if kind is None:
            return False
        if (
            kind == EntityType.CONVEYOR
            or kind == EntityType.ROAD
            or kind == EntityType.SPLITTER
            or kind == EntityType.ARMOURED_CONVEYOR
            or kind == EntityType.BRIDGE
        ):
            return False
        return self.building_team[i] == self.state.my_team

    def is_enemy_building(self, pos):
        i = self.idx(pos)
        match self.building_team[i]:
            case None:
                return False
            case t if t is not None:
                return t != self.state.my_team

    def leads_to_enemy_building(self, pos):
        i = self.idx(pos)
        if self.building_team[i] != self.state.my_team:
            return False
        kind = self.building_kind[i]
        if not (
            (kind is not None)
            and (
                kind == EntityType.CONVEYOR
                or kind == EntityType.ARMOURED_CONVEYOR
                or kind == EntityType.BRIDGE
            )
        ):
            return False
        if not self.out_edges[i]:
            return False
        output_location = self.out_edges[i][0]
        if not self.in_bounds(output_location):
            return False
        return self.is_enemy_building(output_location)

    def update_reachability(self):
        """
        Drain the reachability frontier, expanding admitted tiles into their
        8-connected non-WALL neighbours up to `K_PER_TURN` pops.
        """
        update_reachability(
            self.reach_parent,
            self.reach_frontier,
            self.env,
            self.state.width,
            self.state.height,
        )

    def apply_local_destroy(self, pos):
        """Mid-turn invariant fix-up after `ct.destroy(pos)`."""
        vision_apply_local_destroy(self, pos)

    def ti_conv_astar(self, start, target, resource):
        """
        Run the Ti A* search. Constructs an `EconAstarCtx` from this
        builder's borrowed state and forwards to `conv_search.search`.
        """
        ctx = self.make_econ_ctx()
        path = self.conv_search.search(start, target, resource, ctx)
        self.absorb_econ_ctx(ctx)
        return path

    def ax_conv_astar(self, start, target, resource):
        """
        Run the Ax A* search. Same shape as `ti_conv_astar` but goes
        through `ax_conv_search`.
        """
        ctx = self.make_econ_ctx()
        path = self.ax_conv_search.search(start, target, resource, ctx)
        self.absorb_econ_ctx(ctx)
        return path

    def make_econ_ctx(self):
        return EconAstarCtx(
            ax_routable=list(self.ax_routable),
            ti_routable=list(self.ti_routable),
            routing_extra=list(self.routing_extra),
            reach_parent=list(self.reach_parent),
            my_pos=self.state.my_pos,
            nearby_tiles=list(self.state.nearby_tiles),
            all_bots=list(self.state.all_bots),
        )

    def absorb_econ_ctx(self, ctx):
        self.reach_parent = ctx.reach_parent

    def bugnav_step(self, target):
        """
        One A* step toward `target`. Returns the next position to step to,
        or `None` if the goal is unreachable / already at goal. Borrow-splits
        internally so the bugnav state and the cost grid can be passed
        simultaneously.
        """
        bugnav = self.bugnav
        cost_grid = self.cost_grid
        state = self.state
        ctx = NavCtx(
            my_pos=state.my_pos,
            cost_grid=cost_grid,
            w=state.width,
            h=state.height,
            nearby_tiles=state.nearby_tiles,
            all_bots=state.all_bots,
        )
        return bugnav.step(ctx, target)

    def _refresh_ti_leakage(self, i):
        new = self._ax_harv_at[i] > 0 or self._foundry_at[i] > 0
        if new != self.ti_leakage[i]:
            self.ti_leakage[i] = new
            self.ti_routable[i] = self.buildable[i] and not new

    def _refresh_ax_leakage(self, i):
        new = self._ti_harv_at[i] > 0
        if new != self.ax_leakage[i]:
            self.ax_leakage[i] = new
            self.ax_routable[i] = self.buildable[i] and not new

    def _bump_ti_harv(self, pos, delta):
        for d in DIR4:
            n = pos.add(d)
            if not self.in_bounds(n):
                continue
            ni = self.idx(n)
            old = self._ti_harv_at[ni]
            self._ti_harv_at[ni] += delta
            new = self._ti_harv_at[ni]
            self._refresh_ax_leakage(ni)
            if old == 0 and new > 0:
                self.ti_harvester_adjacent.add(n)
                self._reeval_ti_upstream(n)
            elif old > 0 and new == 0:
                self.ti_harvester_adjacent.discard(n)
                self._reeval_ti_upstream(n)

    def _bump_ax_harv(self, pos, delta):
        for d in DIR4:
            n = pos.add(d)
            if not self.in_bounds(n):
                continue
            ni = self.idx(n)
            old = self._ax_harv_at[ni]
            self._ax_harv_at[ni] += delta
            new = self._ax_harv_at[ni]
            self._refresh_ti_leakage(ni)
            if old == 0 and new > 0:
                self.ax_harvester_adjacent.add(n)
                self._reeval_ax_upstream(n)
            elif old > 0 and new == 0:
                self.ax_harvester_adjacent.discard(n)
                self._reeval_ax_upstream(n)

    def _reeval_ti_upstream(self, t):
        i = self.idx(t)
        has_seed = self._ti_harv_at[i] > 0 and not (not self.out_edges[i])
        target = has_seed or self._ti_in_count[i] > 0
        self._set_ti_upstream(t, target)

    def _reeval_ax_upstream(self, t):
        i = self.idx(t)
        has_seed = self._ax_harv_at[i] > 0 and not (not self.out_edges[i])
        target = has_seed or self._ax_in_count[i] > 0
        self._set_ax_upstream(t, target)

    def _set_ti_upstream(self, t, want):
        is_in = t in self.ti_upstream
        if want == is_in:
            return
        i = self.idx(t)
        if want:
            self.ti_upstream.add(t)
            delta = 1
        else:
            self.ti_upstream.discard(t)
            delta = -1
        outs: list[Position] = list(self.out_edges[i])
        for out in outs:
            oi = self.idx(out)
            self._ti_in_count[oi] += delta
            self._reeval_ti_upstream(out)
        for out in outs:
            self._check_dangling(out, "ti_upstream_change")

    def _set_ax_upstream(self, t, want):
        is_in = t in self.ax_upstream
        if want == is_in:
            return
        i = self.idx(t)
        if want:
            self.ax_upstream.add(t)
            delta = 1
        else:
            self.ax_upstream.discard(t)
            delta = -1
        outs: list[Position] = list(self.out_edges[i])
        for out in outs:
            oi = self.idx(out)
            self._ax_in_count[oi] += delta
            self._reeval_ax_upstream(out)
        for out in outs:
            self._check_dangling(out, "ax_upstream_change")

    def _on_in_edge_added(self, t, f):
        i = self.idx(t)
        if f in self.ti_upstream:
            self._ti_in_count[i] += 1
            self._reeval_ti_upstream(t)
        if f in self.ax_upstream:
            self._ax_in_count[i] += 1
            self._reeval_ax_upstream(t)

    def _on_in_edge_removed(self, t, f):
        i = self.idx(t)
        if f in self.ti_upstream:
            self._ti_in_count[i] -= 1
            self._reeval_ti_upstream(t)
        if f in self.ax_upstream:
            self._ax_in_count[i] -= 1
            self._reeval_ax_upstream(t)

    def _on_out_edges_changed(self, pos):
        self._reeval_ti_upstream(pos)
        self._reeval_ax_upstream(pos)

    def _bump_foundry(self, pos, delta):
        for d in DIR4:
            n = pos.add(d)
            if self.in_bounds(n):
                ni = self.idx(n)
                self._foundry_at[ni] += delta
                self._refresh_ti_leakage(ni)

    def _check_multi_input(self, t):
        idx = self.idx(t)
        if len(self.in_edges[idx]) >= 2:
            self.is_multi_input.add(t)
        else:
            self.is_multi_input.discard(t)

    def _is_flow_consumer(self, pos):
        i = self.idx(pos)
        kind = self.building_kind[i]
        if kind is None:
            return False
        if self.building_team[i] != self.state.my_team:
            return False
        return (
            kind == EntityType.CONVEYOR
            or kind == EntityType.ARMOURED_CONVEYOR
            or kind == EntityType.BRIDGE
            or kind == EntityType.SPLITTER
            or kind == EntityType.FOUNDRY
            or kind == EntityType.CORE
            or kind == EntityType.GUNNER
            or kind == EntityType.SENTINEL
            or kind == EntityType.BREACH
            or kind == EntityType.LAUNCHER
        )

    def _splitter_satisfied(self, splitter_pos):
        count = 0
        for out in self.out_edges[self.idx(splitter_pos)]:
            if self._is_flow_consumer(out):
                count += 1
                if count >= 2:
                    return True
        return False

    def _check_dangling(self, t, _trigger):
        i = self.idx(t)
        kind = self.building_kind[i]
        team = self.building_team[i]
        env_i = self.env[i]
        my_team = self.state.my_team
        match kind:
            case None if env_i != Environment.WALL:
                admit_terrain = True
            case EntityType.ROAD if team == my_team:
                admit_terrain = True
            case EntityType.MARKER:
                admit_terrain = True
            case _:
                admit_terrain = False
        if not admit_terrain:
            self.dangling_set.discard(t)
            self.unreachable_dangling.discard(t)
            return
        unconn_adj = t in self.adjacent_to_unconnected_harvester
        feeders_unsatisfied = False
        in_edges_t: list[Position] = list(self.in_edges[i])
        for f in in_edges_t:
            in_ti = f in self.ti_upstream
            in_ax = f in self.ax_upstream
            if not in_ti and not in_ax:
                continue
            fi = self.idx(f)
            is_satisfied_splitter = self.building_kind[
                fi
            ] == EntityType.SPLITTER and self._splitter_satisfied(f)
            if not is_satisfied_splitter:
                feeders_unsatisfied = True
                break
        is_dangling = unconn_adj or feeders_unsatisfied
        if is_dangling:
            if not (t in self.unreachable_dangling):
                self.dangling_set.add(t)
        else:
            self.dangling_set.discard(t)
            self.unreachable_dangling.discard(t)

    def pnb_fix_boundary(self, cx, cy, w, h):
        """
        Set `pnb[(cy, cx)]` to its 8-king-move neighbours within `(w, h)`.
        Pulled out of `post_init` so the body is a single statement and the
        translator doesn't need multi-statement-closure support.
        """
        stride = int(50)
        nbs: list[int] = []
        for dx, dy in DIR8_DELTA:
            nx = cx + dx
            ny = cy + dy
            if (nx in range(0, w)) and (ny in range(0, h)):
                nbs.append(ny * stride + nx)
        self.pnb[int(cy * stride + cx)] = nbs

    def refresh_symmetry_cache(self):
        """Mirror `my_core` under `symmetry_guess`."""
        count = len(self.state.symmetry_candidates)
        self.symmetry = (
            next(iter(self.state.symmetry_candidates), None) if count == 1 else None
        )
        guess = self.symmetry_guess()
        self.en_core_guess = guess.action(
            self.my_core, self.state.width, self.state.height
        )

    def unit_state(self):
        return self.state

    def unit_state_mut(self):
        return self.state

    def post_init(self, ct):
        self.state.init_static_state(ct)
        core = self.resolve_my_core(ct)
        self.set_my_core(core)
        r = self.state.rng.random()
        self.opportunistic = r < 0.5
        s = float(max(self.state.width, self.state.height))
        self.econ_radius_sq = int(round(0.7 * s * (0.7 * s)))
        w = self.state.width
        h = self.state.height
        for y in range(0, int(50)):
            base = int(y) * 50
            for x in range(0, int(50)):
                if x >= w or y >= h:
                    self.cost_grid[base + int(x)] = 1000000
        self.known_map = (
            identify_map(self.state.width, self.state.height, self.my_core)
            if False
            else None
        )
        for i, d in enumerate(DIR8):
            self.core_edges[i] = self.my_core.add(d)
        with Scope.new_timed("pnb") as _scope:
            for cx in range(0, w):
                self.pnb_fix_boundary(cx, h - 1, w, h)
            for cy in range(0, h - 1):
                self.pnb_fix_boundary(w - 1, cy, w, h)
        self.refresh_symmetry_cache()

    def run(self, ct):
        self.state.cache_per_turn_state(ct)
        self.state.check_symmetry_marker(ct)
        self.refresh_symmetry_cache()
        with Scope.new_timed("body") as _g:
            args = {}
            args[str("id")] = self.state.my_id
            args[str("pos")] = auto_wrap_position(self.state.my_pos)
            args[str("round")] = self.state.round
            log("Builder {id} pos={pos} round={round}", args)
            update(self, ct)
            begin_turn_offense(self, ct)
            if DEBUG_DUMP:
                dump(self, ct)
            role = self.role
            with Scope.new_timed("tasks") as _g:
                policy = policy_for_role(role)
                run_policy(self, ct, policy)
            with Scope.new_timed("hooks") as _g:
                with Scope.new_timed("indicators") as _g:
                    indicators(self, ct)
                if not role.is_offensive():
                    with Scope.new_timed("heal") as _g:
                        end_of_turn_heal(self, ct)
                with Scope.new_timed("symmetry") as _g:
                    end_of_turn_propagate_symmetry(self, ct)

    def my_core_pos(self):
        return self.my_core

    def set_my_core(self, pos):
        self.my_core = pos

    def resolve_my_core(self, ct):
        my_team = self.state.my_team
        for bid in ct.get_nearby_buildings(None):
            if (
                ct.get_team(bid) == my_team
                and ct.get_entity_type(bid) == EntityType.CORE
            ):
                return ct.get_position(bid)
        return ct.get_position(None)

    def post_init_core_aware(self, ct):
        """
        Override `Unit::post_init` chain for core-aware units. Concrete
        `Unit::post_init` impls on `CoreAwareUnit` types should delegate here.
        """
        s = self.unit_state_mut()
        s.init_static_state(ct)
        s.narrow_symmetry_from_vision(ct)
        core = self.resolve_my_core(ct)
        self.set_my_core(core)
