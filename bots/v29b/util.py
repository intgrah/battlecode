from cambc import Controller, Direction, EntityType, Environment, Position

DIRS = [d for d in Direction if d != Direction.CENTRE]
CARDINALS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]

SPOKES = [
    Direction.NORTH,
    Direction.NORTHEAST,
    Direction.EAST,
    Direction.SOUTHEAST,
    Direction.SOUTH,
    Direction.SOUTHWEST,
    Direction.WEST,
    Direction.NORTHWEST,
]


def toward(a: Position, b: Position) -> Direction:
    return a.direction_to(b)


def ib(ct: Controller, p: Position) -> bool:
    return 0 <= p.x < ct.get_map_width() and 0 <= p.y < ct.get_map_height()


def wall(ct: Controller, p: Position) -> bool:
    return not ib(ct, p) or ct.get_tile_env(p) == Environment.WALL


def ore_env(ct: Controller, p: Position) -> bool:
    return ib(ct, p) and ct.get_tile_env(p) in (
        Environment.ORE_TITANIUM,
        Environment.ORE_AXIONITE,
    )


def step_road(ct: Controller, d: Direction) -> bool:
    nxt = ct.get_position().add(d)
    if wall(ct, nxt):
        return False
    if ct.can_build_road(nxt):
        ct.build_road(nxt)
    if ct.can_move(d):
        ct.move(d)
        return True
    return False


def step_walk(ct: Controller, d: Direction) -> bool:
    if wall(ct, ct.get_position().add(d)):
        return False
    if ct.can_move(d):
        ct.move(d)
        return True
    return False


def step_patrol(ct: Controller, d: Direction) -> bool:
    nxt = ct.get_position().add(d)
    if wall(ct, nxt):
        return False
    if ct.can_move(d):
        ct.move(d)
        return True
    if ct.can_build_road(nxt):
        ct.build_road(nxt)
    if ct.can_move(d):
        ct.move(d)
        return True
    return False


def _is_diagonal(d: Direction) -> bool:
    dx, dy = d.delta()
    return dx != 0 and dy != 0


_DELTA_TO_DIR = {d.delta(): d for d in Direction if d != Direction.CENTRE}


def step_conv(ct: Controller, d: Direction) -> bool:
    if _is_diagonal(d):
        import random

        dx, dy = d.delta()
        pair = [_DELTA_TO_DIR[(dx, 0)], _DELTA_TO_DIR[(0, dy)]]
        if random.random() < 0.5:
            pair.reverse()
        for cd in pair:
            if step_conv(ct, cd):
                return True
        return False
    pos = ct.get_position()
    nxt = pos.add(d)
    if wall(ct, nxt):
        return False
    if not ore_env(ct, nxt):
        bid = ct.get_tile_building_id(nxt)
        if (
            bid is not None
            and ct.get_entity_type(bid) == EntityType.ROAD
            and ct.get_team(bid) == ct.get_team()
        ):
            ct.destroy(nxt)
        if ct.can_build_conveyor(nxt, d.opposite()):
            ct.build_conveyor(nxt, d.opposite())
    if ct.can_move(d):
        ct.move(d)
        return True
    return False


def step_raid(ct: Controller, d: Direction) -> bool:
    nxt = ct.get_position().add(d)
    if wall(ct, nxt):
        return False
    if ct.can_move(d):
        ct.move(d)
        return True
    if ct.can_build_road(nxt):
        ct.build_road(nxt)
    if ct.can_move(d):
        ct.move(d)
        return True
    return False


def repair_dir(ct: Controller, gap: Position, core: Position) -> Direction:
    my = ct.get_team()
    best_dir = None
    best_core_dist = 999999
    upstream_dir = None

    for d in DIRS:
        adj = gap.add(d)
        if not ib(ct, adj) or not ct.is_in_vision(adj):
            continue
        bid = ct.get_tile_building_id(adj)
        if bid is None or ct.get_team(bid) != my:
            continue
        et = ct.get_entity_type(bid)
        if et not in (
            EntityType.CONVEYOR,
            EntityType.ARMOURED_CONVEYOR,
            EntityType.SPLITTER,
        ):
            continue
        conv_out = ct.get_direction(bid)
        ox, oy = conv_out.delta()
        out_pos = Position(adj.x + ox, adj.y + oy)
        if out_pos.x == gap.x and out_pos.y == gap.y:
            upstream_dir = conv_out
            continue
        dist = adj.distance_squared(core)
        if dist < best_core_dist:
            best_core_dist = dist
            best_dir = d

    if best_dir:
        return best_dir
    if upstream_dir:
        return upstream_dir
    return toward(gap, core)
