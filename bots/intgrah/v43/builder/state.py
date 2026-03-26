from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto

from cambc import Controller, Direction, EntityType, Environment, Team
from known_maps import MAPS
from known_maps import decode as decode_known_map
from marker import Eureka, TaskClaim, is_stale
from marker import decode as decode_marker
from util import (
    DELTA_TO_DIR,
    DIR4_DELTA,
    DIRECTED_BUILDINGS,
    TRANSPORT,
    TURRETS,
    WALKABLE_BUILDINGS,
    tiles_3x3,
)

# A* walkability costs. Lower = preferred by pathfinder.
COST_ROAD = 2  # walkable buildings (roads, conveyors, splitters, allied core)
COST_EMPTY = 10  # seen empty ground — builder must build a road to traverse
COST_UNSEEN = 12  # never seen — optimistic guess, slightly penalised vs known empty
COST_IMPASSABLE = 1_000_000  # walls, ore tiles, enemy buildings, non-walkable buildings


@dataclass(slots=True)
class FlowState:
    n: int
    ti: list[float] = field(init=False)
    ax: list[float] = field(init=False)
    rax: list[float] = field(init=False)
    total: list[float] = field(init=False)
    ti_excess: list[float] = field(init=False)
    ax_excess: list[float] = field(init=False)
    rax_excess: list[float] = field(init=False)
    excess: list[float] = field(init=False)
    blocked: list[bool] = field(init=False)

    def __post_init__(self) -> None:
        n = self.n
        self.ti = [0.0] * n
        self.ax = [0.0] * n
        self.rax = [0.0] * n
        self.total = [0.0] * n
        self.ti_excess = [0.0] * n
        self.ax_excess = [0.0] * n
        self.rax_excess = [0.0] * n
        self.excess = [0.0] * n
        self.blocked = [False] * n


class Symmetry(Enum):
    """Map symmetry type. Maps are guaranteed to have at least one.

    Any two symmetries imply the third, so either exactly one holds
    or all three hold. Exactly two is impossible.
    """

    ROT = auto()  # 180° rotational: (x,y) <-> (w-1-x, h-1-y)
    HOR = auto()  # horizontal reflection: (x,y) <-> (x, h-1-y)
    VER = auto()  # vertical reflection: (x,y) <-> (w-1-x, y)


class State:
    """Persistent per-builder map knowledge, updated incrementally from vision.

    Stores ground truth for all tiles ever seen, and derives A* costs on the fly.
    Detects map symmetry to infer unseen tiles from seen ones.

    Fields:
        env:            terrain per tile. None = never seen, else Environment enum.
                        Permanent once set — terrain never changes.
                        Also set by symmetry reflection (inferred, not directly observed).
        entity:         building per tile. None = no building or never seen.
                        (EntityType, Team) if a building was observed. Stale state —
                        buildings can be destroyed while out of vision.
                        NOT reflected by symmetry (players build differently).
        direction:      output direction of conveyors/splitters. None if not applicable.
        bridge_target:  (x, y) target of bridges. None if not a bridge.
        last_seen:      turn number when tile was last in vision. 0 if never seen.
        ore_ti:         set of known Ti ore positions.
        ore_ax:         set of known Ax ore positions.
        harvested:      set of ore positions that have a harvester on them.
        symmetry:       confirmed map symmetry type, or None if unresolved.

    Symmetry detection:
        Three hypotheses (ROT, HOR, VER) are tested against observations.
        A hypothesis is eliminated when a seen tile's env contradicts its mirror.
        Core positions provide immediate eliminations:
          - HOR requires our core y == h-1-y (on horizontal midline)
          - VER requires our core x == w-1-x (on vertical midline)
          - Enemy core position (when seen) must match the predicted mirror of our core
        Eureka triggers when one hypothesis remains (certain), or when >50% of tiles
        are seen with multiple survivors (heuristic — any surviving hypothesis is used).
        On eureka, all known env tiles are reflected to fill the unseen half.
    """

    def __init__(
        self,
        w: int,
        h: int,
        my_team: Team,
        core_pos: tuple[int, int],
    ) -> None:
        self.w = w
        self.h = h
        self.my_team = my_team
        self.age = 0
        n = w * h

        # -- Per-tile arrays (indexed by y * w + x) --
        self.env: list[Environment | None] = [None] * n
        self.entity: list[tuple[EntityType, Team] | None] = [None] * n
        self.direction: list[Direction | None] = [None] * n
        self.bridge_target: list[tuple[int, int] | None] = [None] * n
        self.last_seen: list[int] = [0] * n

        # -- Resources (xy tuples) --
        self.ore_ti: set[tuple[int, int]] = set()
        self.ore_ax: set[tuple[int, int]] = set()

        # -- Friendly states --
        self.my_core: tuple[int, int] = core_pos
        self.my_harvested: set[tuple[int, int]] = set()
        self.my_harvesters: set[int] = set()
        self.my_transport: set[int] = set()
        self.my_foundries: set[int] = set()
        self.my_turrets: set[int] = set()
        self.my_flow = FlowState(n)

        # -- Enemy states --
        self.en_core: tuple[int, int] | None = None
        self.en_core_tiles: set[int] = set()
        self.en_harvested: set[tuple[int, int]] = set()
        self.en_harvesters: set[int] = set()
        self.en_transport: set[int] = set()
        self.en_turrets: set[int] = set()
        self.en_foundries: set[int] = set()
        self.en_flow = FlowState(n)

        # -- Ephemeral (rebuilt each turn) --
        self.unit_tiles: set[int] = set()
        self.claims: set[TaskClaim] = set()

        # -- Symmetry --
        self.symmetry: Symmetry | None = None
        self._sym_candidates = {Symmetry.ROT, Symmetry.HOR, Symmetry.VER}

        # -- Internal --
        self.my_core_tiles: set[int] = tiles_3x3(*core_pos, w, h)
        self._out_target: dict[int, list[int]] = {}
        self._out_target_dirty = True

        self._try_load_known_map(core_pos)

    def _try_load_known_map(self, core_pos: tuple[int, int]) -> None:
        key = (self.w, self.h, core_pos[0], core_pos[1])
        known = MAPS.get(key)
        if known is None:
            return
        encoded, en_core = known
        tiles = decode_known_map(encoded, self.w * self.h)
        for i in range(self.w * self.h):
            self.env[i] = tiles[i]
            x, y = i % self.w, i // self.w
            match tiles[i]:
                case Environment.ORE_TITANIUM:
                    self.ore_ti.add((x, y))
                case Environment.ORE_AXIONITE:
                    self.ore_ax.add((x, y))
        self._set_en_core(en_core)
        self._sym_candidates.clear()

    def _set_en_core(self, en_core: tuple[int, int]) -> None:
        self.en_core = en_core
        self.en_core_tiles = tiles_3x3(*en_core, self.w, self.h)

    def idx(self, x: int, y: int) -> int:
        return y * self.w + x

    def pos(self, i: int) -> tuple[int, int]:
        return i % self.w, i // self.w

    def mirror(self, x: int, y: int) -> tuple[int, int]:
        """Mirror a position under the confirmed symmetry. Identity if unconfirmed."""
        match self.symmetry:
            case Symmetry.ROT:
                return (self.w - 1 - x, self.h - 1 - y)
            case Symmetry.HOR:
                return (x, self.h - 1 - y)
            case Symmetry.VER:
                return (self.w - 1 - x, y)
        return (x, y)

    # -- Per-turn update --

    def update(self, ct: Controller) -> tuple[list[tuple[int, int]], bool]:
        """Incorporate all visible tiles into the state. Call once per turn.

        Returns list of (x, y) tiles whose entity/walkability changed.
        """
        self.age += 1
        rnd = ct.get_current_round()
        new_tiles: list[tuple[int, int, Environment]] = []
        changed: list[tuple[int, int]] = []

        self.unit_tiles.clear()
        my_id = ct.get_id()
        for uid in ct.get_nearby_units():
            if uid == my_id:
                continue
            upos = ct.get_position(uid)
            self.unit_tiles.add(self.idx(upos.x, upos.y))

        self.claims = {c for c in self.claims if not is_stale(c, rnd)}

        for t in ct.get_nearby_tiles():
            x, y = t.x, t.y
            i = self.idx(x, y)
            self.last_seen[i] = rnd

            old_env = self.env[i]
            old_ent = self.entity[i]
            env = ct.get_tile_env(t)
            self.env[i] = env

            if env == Environment.ORE_TITANIUM:
                self.ore_ti.add((x, y))
            elif env == Environment.ORE_AXIONITE:
                self.ore_ax.add((x, y))
            bid = ct.get_tile_building_id(t)
            if bid is not None:
                etype = ct.get_entity_type(bid)
                team = ct.get_team(bid)
                new_ent = (etype, team)
                self.entity[i] = new_ent
                if new_ent != old_ent or env != old_env:
                    changed.append((x, y))

                if etype in DIRECTED_BUILDINGS:
                    self.direction[i] = ct.get_direction(bid)
                    self.bridge_target[i] = None
                elif etype == EntityType.BRIDGE:
                    self.direction[i] = None
                    bt = ct.get_bridge_target(bid)
                    self.bridge_target[i] = (bt.x, bt.y)
                else:
                    self.direction[i] = None
                    self.bridge_target[i] = None

                if team == self.my_team:
                    if etype == EntityType.HARVESTER:
                        self.my_harvested.add((x, y))
                        self.my_harvesters.add(i)
                        self.my_transport.discard(i)
                        self.my_foundries.discard(i)
                    elif etype in TRANSPORT:
                        self.my_transport.add(i)
                        self.my_harvesters.discard(i)
                        self.my_foundries.discard(i)
                    elif etype == EntityType.FOUNDRY:
                        self.my_foundries.add(i)
                        self.my_transport.discard(i)
                        self.my_harvesters.discard(i)
                    elif etype in TURRETS:
                        self.my_turrets.add(i)
                    elif etype == EntityType.MARKER:
                        msg = decode_marker(ct.get_marker_value(bid))
                        if isinstance(msg, TaskClaim) and not is_stale(msg, rnd):
                            self.claims.add(msg)
                        elif isinstance(msg, Eureka) and self.symmetry is None:
                            self.symmetry = Symmetry(msg.symmetry)
                            self._reflect_all()
                    else:
                        self.my_transport.discard(i)
                        self.my_harvesters.discard(i)
                        self.my_foundries.discard(i)
                    self.en_transport.discard(i)
                    self.en_harvesters.discard(i)
                    self.en_turrets.discard(i)
                else:
                    if etype == EntityType.HARVESTER:
                        self.en_harvested.add((x, y))
                        self.en_harvesters.add(i)
                        self.en_transport.discard(i)
                        self.en_foundries.discard(i)
                    elif etype in TRANSPORT:
                        self.en_transport.add(i)
                        self.en_harvesters.discard(i)
                        self.en_foundries.discard(i)
                    elif etype == EntityType.FOUNDRY:
                        self.en_foundries.add(i)
                        self.en_transport.discard(i)
                        self.en_harvesters.discard(i)
                    elif etype in TURRETS:
                        self.en_turrets.add(i)
                    else:
                        self.en_transport.discard(i)
                        self.en_harvesters.discard(i)
                        self.en_foundries.discard(i)
                    self.my_transport.discard(i)
                    self.my_harvesters.discard(i)
                    self.my_turrets.discard(i)

                if (
                    self.en_core is None
                    and etype == EntityType.CORE
                    and team != self.my_team
                ):
                    center = ct.get_position(bid)
                    self._set_en_core((center.x, center.y))
            else:
                self.entity[i] = None
                self.direction[i] = None
                self.bridge_target[i] = None
                self.my_harvested.discard((x, y))
                self.en_harvested.discard((x, y))
                self.my_transport.discard(i)
                self.my_harvesters.discard(i)
                self.my_turrets.discard(i)
                self.en_transport.discard(i)
                self.en_harvesters.discard(i)
                self.en_turrets.discard(i)
                if old_ent is not None or env != old_env:
                    changed.append((x, y))

            new_tiles.append((x, y, env))

        if self.symmetry is None:
            self._eliminate_symmetries(new_tiles)

        if self.symmetry is not None:
            for x, y, env in new_tiles:
                mx, my = self.mirror(x, y)
                mi = self.idx(mx, my)
                if self.env[mi] is None:
                    self.env[mi] = env
                    if env == Environment.ORE_TITANIUM:
                        self.ore_ti.add((mx, my))
                    elif env == Environment.ORE_AXIONITE:
                        self.ore_ax.add((mx, my))

        needs_reflow = any(
            self.idx(cx, cy) in self.my_transport
            or self.idx(cx, cy) in self.my_harvesters
            or self.idx(cx, cy) in self.my_foundries
            for cx, cy in changed
        )
        needs_enemy_reflow = any(
            self.idx(cx, cy) in self.en_transport
            or self.idx(cx, cy) in self.en_harvesters
            for cx, cy in changed
        )
        if needs_reflow:
            self.recompute_flow()
        if needs_enemy_reflow:
            self.recompute_enemy_flow()

        return changed, needs_reflow

    # -- Symmetry detection --

    def _eliminate_symmetries(
        self,
        new_tiles: list[tuple[int, int, Environment]],
    ) -> None:
        w, h = self.w, self.h
        to_remove: set[Symmetry] = set()

        # Eliminate using core positions
        if self.en_core is not None:
            cx, cy = self.my_core
            ex, ey = self.en_core
            for sym in self._sym_candidates:
                match sym:
                    case Symmetry.ROT:
                        px, py = w - 1 - cx, h - 1 - cy
                    case Symmetry.HOR:
                        px, py = cx, h - 1 - cy
                    case Symmetry.VER:
                        px, py = w - 1 - cx, cy
                if (px, py) != (ex, ey):
                    to_remove.add(sym)
        else:
            # Without enemy core, eliminate symmetries that would map our core to itself
            cx, cy = self.my_core
            for sym in self._sym_candidates:
                match sym:
                    case Symmetry.HOR:
                        if cy == h - 1 - cy:
                            to_remove.add(sym)
                    case Symmetry.VER:
                        if cx == w - 1 - cx:
                            to_remove.add(sym)
                    case Symmetry.ROT:
                        pass

        # Eliminate using env contradictions
        for x, y, env in new_tiles:
            for sym in self._sym_candidates - to_remove:
                match sym:
                    case Symmetry.ROT:
                        mx, my = w - 1 - x, h - 1 - y
                    case Symmetry.HOR:
                        mx, my = x, h - 1 - y
                    case Symmetry.VER:
                        mx, my = w - 1 - x, y
                mi = self.idx(mx, my)
                mirror_env = self.env[mi]
                if mirror_env is not None and mirror_env != env:
                    to_remove.add(sym)

        self._sym_candidates -= to_remove

        if len(self._sym_candidates) == 1:
            self.symmetry = next(iter(self._sym_candidates))
            self._reflect_all()
        elif len(self._sym_candidates) > 1:
            # Heuristic fallback: if >50% of tiles seen and multiple hypotheses
            # survive, all survivors are likely valid (map has multiple symmetries).
            # Pick any one. Not a proof.
            # There exist contrived counterexamples for this.

            seen = sum(1 for e in self.env if e is not None)
            if seen > self.w * self.h // 2:
                self.symmetry = next(iter(self._sym_candidates))
                self._reflect_all()

    def _reflect_all(self) -> None:
        """One-time bulk reflection of all known env tiles under confirmed symmetry."""
        for i in range(self.w * self.h):
            env = self.env[i]
            if env is None:
                continue
            x, y = i % self.w, i // self.w
            mx, my = self.mirror(x, y)
            mi = self.idx(mx, my)
            if self.env[mi] is None:
                self.env[mi] = env
                if env == Environment.ORE_TITANIUM:
                    self.ore_ti.add((mx, my))
                elif env == Environment.ORE_AXIONITE:
                    self.ore_ax.add((mx, my))

    # -- Queries --

    def walkable(self, x: int, y: int) -> int:
        """A* movement cost for a builder to traverse this tile."""
        i = self.idx(x, y)
        if i in self.unit_tiles:
            return COST_IMPASSABLE
        match self.env[i]:
            case None:
                return COST_UNSEEN
            case Environment.WALL | Environment.ORE_TITANIUM | Environment.ORE_AXIONITE:
                return COST_IMPASSABLE
        match self.entity[i]:
            case None:
                return COST_EMPTY
            case (EntityType.MARKER, _):
                return COST_EMPTY
            case (EntityType.CORE, team) if team == self.my_team:
                return COST_ROAD
            case (etype, _) if etype in WALKABLE_BUILDINGS:
                return COST_ROAD
            case _:
                return COST_IMPASSABLE

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.w and 0 <= y < self.h

    def is_passable(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and self.walkable(x, y) < COST_IMPASSABLE

    def is_unseen(self, x: int, y: int) -> bool:
        return self.env[self.idx(x, y)] is None

    # -- Flow computation (Kahn's topological sort) --

    def _accepts_input_from(self, ti: int, from_dir: Direction) -> bool:
        """Check if tile ti accepts input arriving along from_dir (source->target direction)."""
        ent = self.entity[ti]
        if ent is None:
            return True
        etype = ent[0]
        d = self.direction[ti]
        if etype == EntityType.SPLITTER:
            if d is None:
                return False
            return from_dir == d
        if etype in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR):
            if d is None:
                return True
            return from_dir != d.opposite()
        return True

    def _harvester_ore_type(self, i: int) -> Environment | None:
        x, y = i % self.w, i // self.w
        if (x, y) in self.ore_ti:
            return Environment.ORE_TITANIUM
        if (x, y) in self.ore_ax:
            return Environment.ORE_AXIONITE
        return None

    def recompute_flow(self) -> None:
        self._recompute_flow_impl(
            self.my_flow,
            self.my_harvesters,
            self.my_transport,
            self.my_foundries,
            self.my_core_tiles,
        )

    def recompute_enemy_flow(self) -> None:
        self._recompute_flow_impl(
            self.en_flow,
            self.en_harvesters,
            self.en_transport,
            self.en_foundries,
            self.en_core_tiles,
        )

    def _recompute_flow_impl(
        self,
        f: FlowState,
        harvesters: set[int],
        transport: set[int],
        foundries: set[int],
        core_tiles: set[int],
    ) -> None:
        receivers = transport | foundries | core_tiles
        w, h = self.w, self.h

        for i in harvesters | receivers:
            f.ti[i] = 0.0
            f.ax[i] = 0.0
            f.rax[i] = 0.0
            f.total[i] = 0.0
            f.ti_excess[i] = 0.0
            f.ax_excess[i] = 0.0
            f.rax_excess[i] = 0.0
            f.excess[i] = 0.0

        in_degree: dict[int, int] = dict.fromkeys(receivers, 0)
        out_target: dict[int, list[int]] = {}
        in_reverse: dict[int, list[int]] = {}

        for i in transport:
            ent = self.entity[i]
            if ent is None:
                continue
            etype = ent[0]
            bt = self.bridge_target[i]
            d = self.direction[i]
            if etype == EntityType.BRIDGE and bt is not None:
                bx, by = bt
                if 0 <= bx < w and 0 <= by < h:
                    tgt = by * w + bx
                    if tgt in in_degree:
                        in_degree[tgt] += 1
                        out_target[i] = [tgt]
                        in_reverse.setdefault(tgt, []).append(i)
            elif etype == EntityType.SPLITTER and d is not None:
                ix, iy = i % w, i // w
                dx, dy = d.delta()
                outs: list[int] = []
                for odx, ody in [(dx, dy), (-dy, dx), (dy, -dx)]:
                    nx, ny = ix + odx, iy + ody
                    if 0 <= nx < w and 0 <= ny < h:
                        tgt = ny * w + nx
                        if tgt in in_degree:
                            outs.append(tgt)
                            in_degree[tgt] += 1
                            in_reverse.setdefault(tgt, []).append(i)
                if outs:
                    out_target[i] = outs
            elif d is not None:
                dx, dy = d.delta()
                nx, ny = i % w + dx, i // w + dy
                if 0 <= nx < w and 0 <= ny < h:
                    tgt = ny * w + nx
                    if tgt in in_degree:
                        in_degree[tgt] += 1
                        out_target[i] = [tgt]
                        in_reverse.setdefault(tgt, []).append(i)

        for i in foundries:
            ix, iy = i % w, i // w
            outs: list[int] = []
            for ddx, ddy in DIR4_DELTA:
                nx, ny = ix + ddx, iy + ddy
                if 0 <= nx < w and 0 <= ny < h:
                    ni = ny * w + nx
                    if ni in in_degree:
                        from_dir = DELTA_TO_DIR.get((ddx, ddy))
                        if from_dir is not None and self._accepts_input_from(
                            ni,
                            from_dir,
                        ):
                            outs.append(ni)
                            in_degree[ni] += 1
                            in_reverse.setdefault(ni, []).append(i)
            out_target[i] = outs

        queue: deque[int] = deque()
        for i in harvesters:
            ix, iy = i % w, i // w
            outs: list[int] = []
            for ddx, ddy in DIR4_DELTA:
                nx, ny = ix + ddx, iy + ddy
                if 0 <= nx < w and 0 <= ny < h:
                    ni = ny * w + nx
                    if ni in receivers:
                        from_dir = DELTA_TO_DIR.get((ddx, ddy))
                        if from_dir is not None and self._accepts_input_from(
                            ni,
                            from_dir,
                        ):
                            outs.append(ni)
                            in_degree[ni] += 1
                            in_reverse.setdefault(ni, []).append(i)
            out_target[i] = outs
            queue.append(i)

        for i, deg in in_degree.items():
            if deg == 0:
                queue.append(i)

        while queue:
            ci = queue.popleft()
            ent = self.entity[ci]
            if ent is None:
                continue
            etype = ent[0]
            outs = out_target.get(ci, [])

            if etype == EntityType.HARVESTER:
                ore = self._harvester_ore_type(ci)
                n_out = max(len(outs), 1)
                push = 0.25 / n_out
                excess = 0.25 - push * len(outs)
                for oi in outs:
                    if ore == Environment.ORE_TITANIUM:
                        f.ti[oi] += push
                    elif ore == Environment.ORE_AXIONITE:
                        f.ax[oi] += push
                    f.total[oi] += push
                    in_degree[oi] -= 1
                    if in_degree[oi] <= 0:
                        queue.append(oi)
                if ore == Environment.ORE_TITANIUM:
                    f.ti_excess[ci] = excess
                elif ore == Environment.ORE_AXIONITE:
                    f.ax_excess[ci] = excess
                f.excess[ci] = excess
            elif etype == EntityType.FOUNDRY:
                ti_in = f.ti[ci]
                ax_in = f.ax[ci]
                refined = min(ti_in, ax_in)
                f.ti_excess[ci] = ti_in - refined
                f.ax_excess[ci] = ax_in - refined
                rax_in = f.rax[ci]
                rax_out = rax_in + refined
                n_outs = len(outs)
                push = rax_out / n_outs if n_outs > 0 else 0.0
                for oi in outs:
                    f.rax[oi] += push
                    f.total[oi] += push
                    in_degree[oi] -= 1
                    if in_degree[oi] <= 0:
                        queue.append(oi)
                total_out = rax_out
                f.excess[ci] = (ti_in + ax_in + rax_in) - total_out
            elif etype in TRANSPORT:
                ti_in = f.ti[ci]
                ax_in = f.ax[ci]
                rax_in = f.rax[ci]
                divisor = 3 if etype == EntityType.SPLITTER else 1
                ti_push = ti_in / divisor
                ax_push = ax_in / divisor
                rax_push = rax_in / divisor
                total_push = ti_push + ax_push + rax_push
                total_out = 0.0
                for oi in outs:
                    f.ti[oi] += ti_push
                    f.ax[oi] += ax_push
                    f.rax[oi] += rax_push
                    f.total[oi] += total_push
                    total_out += total_push
                    in_degree[oi] -= 1
                    if in_degree[oi] <= 0:
                        queue.append(oi)
                incoming = ti_in + ax_in + rax_in
                f.ti_excess[ci] = ti_in - ti_push * len(outs)
                f.ax_excess[ci] = ax_in - ax_push * len(outs)
                f.rax_excess[ci] = rax_in - rax_push * len(outs)
                f.excess[ci] = incoming - total_out

        for i in receivers:
            f.blocked[i] = False
        seeds: deque[int] = deque()
        for i in receivers:
            if f.total[i] > 0.75:
                f.blocked[i] = True
                seeds.append(i)
        while seeds:
            bi = seeds.popleft()
            for fi in in_reverse.get(bi, []):
                if fi in receivers and not f.blocked[fi]:
                    f.blocked[fi] = True
                    seeds.append(fi)
