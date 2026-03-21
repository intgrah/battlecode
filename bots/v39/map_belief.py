from collections import deque
from enum import Enum

from cambc import Controller, Direction, EntityType, Environment, Team

# A* walkability costs. Lower = preferred by pathfinder.
COST_ROAD = 7  # walkable buildings (roads, conveyors, splitters, allied core)
COST_EMPTY = 10  # seen empty ground — builder must build a road to traverse
COST_UNSEEN = 12  # never seen — optimistic guess, slightly penalised vs known empty
COST_IMPASSABLE = 1_000_000  # walls, ore tiles, enemy buildings, non-walkable buildings


class Symmetry(Enum):
    """Map symmetry type. Maps are guaranteed to have at least one.

    Any two symmetries imply the third, so either exactly one holds
    or all three hold. Exactly two is impossible.
    """

    ROT = 0  # 180° rotational: (x,y) <-> (w-1-x, h-1-y)
    HOR = 1  # horizontal reflection: (x,y) <-> (x, h-1-y)
    VER = 2  # vertical reflection: (x,y) <-> (w-1-x, y)


_WALKABLE_BUILDINGS = frozenset(
    (
        EntityType.ROAD,
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
    ),
)

_DIRECTED_BUILDINGS = frozenset(
    (
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
    ),
)

_TRANSPORT = frozenset(
    (
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
        EntityType.BRIDGE,
    ),
)

_CARDINALS = [(-1, 0), (1, 0), (0, -1), (0, 1)]


class MapBelief:
    """Persistent per-builder map knowledge, updated incrementally from vision.

    Stores ground truth for all tiles ever seen, and derives A* costs on the fly.
    Detects map symmetry to infer unseen tiles from seen ones.

    Fields:
        env:            terrain per tile. None = never seen, else Environment enum.
                        Permanent once set — terrain never changes.
                        Also set by symmetry reflection (inferred, not directly observed).
        entity:         building per tile. None = no building or never seen.
                        (EntityType, Team) if a building was observed. Stale belief —
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
        self.core_pos = core_pos
        n = w * h
        self.env: list[Environment | None] = [None] * n
        self.entity: list[tuple[EntityType, Team] | None] = [None] * n
        self.direction: list[Direction | None] = [None] * n
        self.bridge_target: list[tuple[int, int] | None] = [None] * n
        self.last_seen: list[int] = [0] * n
        self.flow_in: list[float] = [0.0] * n
        self.excess: list[float] = [0.0] * n
        self.blocked: list[bool] = [False] * n
        self.transport_tiles: set[int] = set()
        self.harvester_tiles: set[int] = set()
        self.ore_ti: set[tuple[int, int]] = set()
        self.ore_ax: set[tuple[int, int]] = set()
        self.harvested: set[tuple[int, int]] = set()
        self.symmetry: Symmetry | None = None
        self._sym_candidates = {Symmetry.ROT, Symmetry.HOR, Symmetry.VER}
        self._enemy_core: tuple[int, int] | None = None
        cx, cy = core_pos
        self._core_tiles: set[int] = set()
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h:
                    self._core_tiles.add(ny * w + nx)
        self._out_target: dict[int, list[int]] = {}
        self._out_target_dirty = True
        self.unit_tiles: set[int] = set()

    def idx(self, x: int, y: int) -> int:
        return y * self.w + x

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

    def update(self, ct: Controller) -> list[tuple[int, int]]:
        """Incorporate all visible tiles into the belief. Call once per turn.

        Returns list of (x, y) tiles whose entity/walkability changed.
        """
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

                if etype in _DIRECTED_BUILDINGS:
                    self.direction[i] = ct.get_direction(bid)
                    self.bridge_target[i] = None
                elif etype == EntityType.BRIDGE:
                    self.direction[i] = None
                    bt = ct.get_bridge_target(bid)
                    self.bridge_target[i] = (bt.x, bt.y)
                else:
                    self.direction[i] = None
                    self.bridge_target[i] = None

                if etype == EntityType.HARVESTER:
                    self.harvested.add((x, y))
                    self.harvester_tiles.add(i)
                    self.transport_tiles.discard(i)
                elif etype in _TRANSPORT:
                    self.transport_tiles.add(i)
                    self.harvester_tiles.discard(i)
                else:
                    self.transport_tiles.discard(i)
                    self.harvester_tiles.discard(i)

                if (
                    self._enemy_core is None
                    and etype == EntityType.CORE
                    and team != self.my_team
                ):
                    center = ct.get_position(bid)
                    self._enemy_core = (center.x, center.y)
            else:
                self.entity[i] = None
                self.direction[i] = None
                self.bridge_target[i] = None
                self.harvested.discard((x, y))
                self.transport_tiles.discard(i)
                self.harvester_tiles.discard(i)
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

        return changed

    # -- Symmetry detection --

    def _eliminate_symmetries(
        self,
        new_tiles: list[tuple[int, int, Environment]],
    ) -> None:
        w, h = self.w, self.h
        to_remove: set[Symmetry] = set()

        # Eliminate using core positions
        if self._enemy_core is not None:
            cx, cy = self.core_pos
            ex, ey = self._enemy_core
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
            cx, cy = self.core_pos
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
        env = self.env[i]
        if env is None:
            return COST_UNSEEN
        if env in (
            Environment.WALL,
            Environment.ORE_TITANIUM,
            Environment.ORE_AXIONITE,
        ):
            return COST_IMPASSABLE
        if i in self.unit_tiles:
            return COST_IMPASSABLE
        ent = self.entity[i]
        if ent is None:
            return COST_EMPTY
        etype, team = ent
        if etype in _WALKABLE_BUILDINGS or (
            etype == EntityType.CORE and team == self.my_team
        ):
            return COST_ROAD
        return COST_IMPASSABLE

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.w and 0 <= y < self.h

    def is_passable(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and self.walkable(x, y) < COST_IMPASSABLE

    def is_unseen(self, x: int, y: int) -> bool:
        return self.env[self.idx(x, y)] is None

    # -- Flow computation (Kahn's topological sort) --

    def recompute_flow(self) -> None:
        core_tiles = self._core_tiles
        receivers = self.transport_tiles | core_tiles
        w, h = self.w, self.h

        for i in self.harvester_tiles | receivers:
            self.flow_in[i] = 0.0
            self.excess[i] = 0.0

        in_degree: dict[int, int] = dict.fromkeys(receivers, 0)
        out_target: dict[int, list[int]] = {}
        in_reverse: dict[int, list[int]] = {}

        for i in self.transport_tiles:
            ent = self.entity[i]
            if ent is None:
                continue
            etype = ent[0]
            bt = self.bridge_target[i]
            d = self.direction[i]
            tgt = -1
            if etype == EntityType.BRIDGE and bt is not None:
                bx, by = bt
                if 0 <= bx < w and 0 <= by < h:
                    tgt = by * w + bx
            elif d is not None:
                dx, dy = d.delta()
                nx, ny = i % w + dx, i // w + dy
                if 0 <= nx < w and 0 <= ny < h:
                    tgt = ny * w + nx
            if tgt >= 0 and tgt in in_degree:
                in_degree[tgt] += 1
                out_target[i] = [tgt]
                in_reverse.setdefault(tgt, []).append(i)

        queue: deque[int] = deque()
        for i in self.harvester_tiles:
            ix, iy = i % w, i // w
            outs: list[int] = []
            for ddx, ddy in _CARDINALS:
                nx, ny = ix + ddx, iy + ddy
                if 0 <= nx < w and 0 <= ny < h:
                    ni = ny * w + nx
                    if ni in receivers:
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
                n_out = max(len(outs), 1)
                push = 0.25 / n_out
                self.excess[ci] = 0.25 - push * len(outs)
                for oi in outs:
                    self.flow_in[oi] += push
                    in_degree[oi] -= 1
                    if in_degree[oi] <= 0:
                        queue.append(oi)
            elif etype in _TRANSPORT:
                incoming = self.flow_in[ci]
                push = incoming / 3 if etype == EntityType.SPLITTER else incoming
                total_out = 0.0
                for oi in outs:
                    self.flow_in[oi] += push
                    total_out += push
                    in_degree[oi] -= 1
                    if in_degree[oi] <= 0:
                        queue.append(oi)
                self.excess[ci] = incoming - total_out

        for i in receivers:
            self.blocked[i] = False
        seeds: deque[int] = deque()
        for i in receivers:
            if self.flow_in[i] > 0.75:
                self.blocked[i] = True
                seeds.append(i)
        while seeds:
            bi = seeds.popleft()
            for fi in in_reverse.get(bi, []):
                if fi in receivers and not self.blocked[fi]:
                    self.blocked[fi] = True
                    seeds.append(fi)
