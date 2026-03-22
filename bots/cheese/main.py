from cambc import Controller, Direction, EntityType, Environment, Position, Team

DIRS = [d for d in Direction if d != Direction.CENTRE]

CONVEYORS = frozenset(
    {EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR, EntityType.SPLITTER},
)


def ib(ct: Controller, p: Position) -> bool:
    return 0 <= p.x < ct.get_map_width() and 0 <= p.y < ct.get_map_height()


def wall(ct: Controller, p: Position):
    return not ib(ct, p) or ct.get_tile_env(p) == Environment.WALL


def on_core(p: Position, cc: Position) -> int:
    return abs(p.x - cc.x) <= 1 and abs(p.y - cc.y) <= 1


def adj_core(p: Position, cc: Position) -> int:
    return max(abs(p.x - cc.x), abs(p.y - cc.y)) == 2


def conv_feeds_core(ct: Controller, bid: int, ec: Position) -> int:
    d = ct.get_direction(bid)
    dx, dy = d.delta()
    ep = ct.get_position(bid)
    return on_core(Position(ep.x + dx, ep.y + dy), ec)


def has_upstream(ct: Controller, tile: Position, my: Team) -> bool:
    for d in DIRS:
        adj = tile.add(d)
        if not ib(ct, adj) or not ct.is_in_vision(adj):
            continue
        bid = ct.get_tile_building_id(adj)
        if bid is None or ct.get_team(bid) == my:
            continue
        if ct.get_entity_type(bid) not in CONVEYORS:
            continue
        od = ct.get_direction(bid)
        dx, dy = od.delta()
        if adj.x + dx == tile.x and adj.y + dy == tile.y:
            return True
    return False


class BugNav:
    def __init__(self) -> None:
        self.wf = False
        self.ws = 1
        self.best = 999999
        self.recent: list[tuple[int, int]] = []

    def reset(self) -> None:
        self.__init__()

    def go(self, ct, target, step_fn) -> bool:
        pos = ct.get_position()
        self.recent.append((pos.x, pos.y))
        if len(self.recent) > 8:
            self.recent.pop(0)
        if len(self.recent) >= 8 and len(set(self.recent)) <= 2:
            self.ws = -self.ws
            self.wf = not self.wf
            self.recent.clear()
            return False

        dist = pos.distance_squared(target)
        d = pos.direction_to(target)

        if not self.wf:
            if step_fn(d):
                return True
            self.wf = True
            self.best = dist

        if dist < self.best:
            self.wf = False
            self.best = dist
            if step_fn(d):
                return True
            self.wf = True

        scan = d
        for _ in range(8):
            if step_fn(scan):
                return True
            scan = scan.rotate_right() if self.ws == 1 else scan.rotate_left()
        return False


def step_road(ct, d) -> bool:
    nxt = ct.get_position().add(d)
    if wall(ct, nxt):
        return False
    if ct.can_build_road(nxt):
        ct.build_road(nxt)
    if ct.can_move(d):
        ct.move(d)
        return True
    return False


class CoreBot:
    def __init__(self) -> None:
        self.spawned = 0

    def run(self, ct: Controller) -> None:
        ti, _ = ct.get_global_resources()
        if ti < ct.get_builder_bot_cost()[0]:
            return
        core_pos = ct.get_position()
        for d in DIRS:
            sp = core_pos.add(d)
            if ct.can_spawn(sp):
                ct.spawn_builder(sp)
                self.spawned += 1
                return


class Builder:
    def __init__(self) -> None:
        self.core = None
        self.ec: Position | None = None
        self.nav = BugNav()

    def run(self, ct: Controller) -> None:
        pos = ct.get_position()
        my = ct.get_team()

        if self.core is None:
            for eid in ct.get_nearby_entities():
                if (
                    ct.get_entity_type(eid) == EntityType.CORE
                    and ct.get_team(eid) == my
                ):
                    self.core = ct.get_position(eid)
                    w, h = ct.get_map_width(), ct.get_map_height()
                    self.ec = Position(w - 1 - self.core.x, h - 1 - self.core.y)
                    break
        if not self.ec:
            return

        spot = self._find_turret_spot(ct, pos, my)
        if spot:
            tile, face = spot
            if pos.distance_squared(tile) <= 2:
                bid = ct.get_tile_building_id(tile)
                if bid is not None and ct.get_team(bid) == my:
                    ct.destroy(tile)
                if ct.can_build_gunner(tile, face):
                    ct.build_gunner(tile, face)
                    return
            self.nav.go(ct, tile, lambda d: step_road(ct, d))
            return

        bid = ct.get_tile_building_id(pos)
        if bid is not None and ct.get_team(bid) != my:
            et = ct.get_entity_type(bid)
            if et in CONVEYORS and conv_feeds_core(ct, bid, self.ec):
                ct.self_destruct()
                return

        target = self._find_target_conv(ct, pos, my)
        if target:
            self.nav.go(ct, target, lambda d: step_road(ct, d))
            return

        self.nav.go(ct, self.ec, lambda d: step_road(ct, d))

    def _find_turret_spot(self, ct: Controller, pos: Position, my: Team):
        best = None
        best_d = 999999
        for tile in ct.get_nearby_tiles():
            if wall(ct, tile) or on_core(tile, self.ec):
                continue
            if not adj_core(tile, self.ec):
                continue
            bid = ct.get_tile_building_id(tile)
            if (bid is not None and ct.get_team(bid) != my) or ct.get_entity_type(
                bid,
            ) != EntityType.ROAD:
                continue
            if not has_upstream(ct, tile, my):
                continue
            face = tile.direction_to(self.ec)
            if face == Direction.CENTRE:
                continue
            d = pos.distance_squared(tile)
            if d < best_d:
                best_d = d
                best = (tile, face)
        return best

    def _find_target_conv(self, ct: Controller, pos: Position, my: Team):
        best = None
        best_d = 999999
        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) == my:
                continue
            if ct.get_entity_type(eid) not in CONVEYORS:
                continue
            if not conv_feeds_core(ct, eid, self.ec):
                continue
            ep = ct.get_position(eid)
            d = pos.distance_squared(ep)
            if d < best_d:
                best_d = d
                best = ep
        return best


class Turret:
    def run(self, ct: Controller) -> None:
        my = ct.get_team()
        best = None
        best_prio = -1
        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) == my:
                continue
            epos = ct.get_position(eid)
            if not ct.can_fire(epos):
                continue
            et = ct.get_entity_type(eid)
            prio = 100 if et == EntityType.CORE else 1
            if prio > best_prio:
                best_prio = prio
                best = epos
        if best:
            ct.fire(best)


class Player:
    def __init__(self) -> None:
        self.core_bot = CoreBot()
        self.builder = Builder()
        self.turret = Turret()

    def run(self, ct: Controller) -> None:
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            self.core_bot.run(ct)
        elif et == EntityType.BUILDER_BOT:
            self.builder.run(ct)
        elif et in (EntityType.GUNNER, EntityType.SENTINEL, EntityType.BREACH):
            self.turret.run(ct)
