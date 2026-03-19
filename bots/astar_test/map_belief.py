from enum import Enum

from cambc import Controller, EntityType, Environment, Team

# A* walkability costs. Lower = preferred by pathfinder.
COST_ROAD = 7       # walkable buildings (roads, conveyors, splitters, allied core)
COST_EMPTY = 10      # seen empty ground — builder must build a road to traverse
COST_UNSEEN = 12     # never seen — optimistic guess, slightly penalised vs known empty
COST_IMPASSABLE = 1_000_000  # walls, ore tiles, enemy buildings, non-walkable buildings


class Symmetry(Enum):
    """Map symmetry type. Maps are guaranteed to have at least one.

    Any two symmetries imply the third, so either exactly one holds
    or all three hold. Exactly two is impossible.
    """

    ROT = 0  # 180° rotational: (x,y) <-> (w-1-x, h-1-y)
    HOR = 1  # horizontal reflection: (x,y) <-> (w-1-x, y)
    VER = 2  # vertical reflection: (x,y) <-> (x, h-1-y)


_WALKABLE_BUILDINGS = frozenset(
    (
        EntityType.ROAD,
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
    ),
)


class MapBelief:
    """Persistent per-builder map knowledge, updated incrementally from vision.

    Stores ground truth for all tiles ever seen, and derives A* costs on the fly.
    Detects map symmetry to infer unseen tiles from seen ones.

    Fields:
        env:        terrain per tile. None = never seen, else Environment enum.
                    Permanent once set — terrain never changes.
                    Also set by symmetry reflection (inferred, not directly observed).
        entity:     building per tile. None = no building or never seen.
                    (EntityType, Team) if a building was observed. Stale belief —
                    buildings can be destroyed while out of vision.
                    NOT reflected by symmetry (players build differently).
        symmetry:   confirmed map symmetry type, or None if unresolved.

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
        self.symmetry: Symmetry | None = None
        self._sym_candidates = {Symmetry.ROT, Symmetry.HOR, Symmetry.VER}
        self._enemy_core: tuple[int, int] | None = None

    def idx(self, x: int, y: int) -> int:
        return y * self.w + x

    def mirror(self, x: int, y: int) -> tuple[int, int]:
        """Mirror a position under the confirmed symmetry. Identity if unconfirmed."""
        match self.symmetry:
            case Symmetry.ROT:
                return (self.w - 1 - x, self.h - 1 - y)
            case Symmetry.HOR:
                return (self.w - 1 - x, y)
            case Symmetry.VER:
                return (x, self.h - 1 - y)
        return (x, y)

    # -- Per-turn update --

    def update(self, ct: Controller) -> None:
        """Incorporate all visible tiles into the belief. Call once per turn."""
        new_tiles: list[tuple[int, int, Environment]] = []

        for t in ct.get_nearby_tiles():
            i = self.idx(t.x, t.y)
            env = ct.get_tile_env(t)
            self.env[i] = env
            bid = ct.get_tile_building_id(t)
            if bid is not None:
                etype = ct.get_entity_type(bid)
                team = ct.get_team(bid)
                self.entity[i] = (etype, team)
                if (
                    self._enemy_core is None
                    and etype == EntityType.CORE
                    and team != self.my_team
                ):
                    center = ct.get_position(bid)
                    self._enemy_core = (center.x, center.y)
            else:
                self.entity[i] = None
            new_tiles.append((t.x, t.y, env))

        if self.symmetry is None:
            self._eliminate_symmetries(new_tiles)

        if self.symmetry is not None:
            for x, y, env in new_tiles:
                mx, my = self.mirror(x, y)
                mi = self.idx(mx, my)
                if self.env[mi] is None:
                    self.env[mi] = env

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
                        px, py = w - 1 - cx, cy
                    case Symmetry.VER:
                        px, py = cx, h - 1 - cy
                if (px, py) != (ex, ey):
                    to_remove.add(sym)
        else:
            # Without enemy core, eliminate symmetries that would map our core to itself
            cx, cy = self.core_pos
            for sym in self._sym_candidates:
                match sym:
                    case Symmetry.HOR:
                        if cy != h - 1 - cy:
                            to_remove.add(sym)
                    case Symmetry.VER:
                        if cx != w - 1 - cx:
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
                        mx, my = w - 1 - x, y
                    case Symmetry.VER:
                        mx, my = x, h - 1 - y
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
            # Pick any one. Not a proof — the builder may discover contradictions
            # later if the guess is wrong.
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
