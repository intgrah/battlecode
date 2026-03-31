from cambc import Controller, Direction, EntityType, Position

_TARGETS = frozenset(
    (
        EntityType.BRIDGE,
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
    ),
)

_DIRS = [d for d in Direction if d != Direction.CENTRE]


class Player:
    def __init__(self) -> None:
        self._spawned = 0

    def run(self, ct: Controller) -> None:
        if ct.get_entity_type() == EntityType.CORE:
            self._run_core(ct)
        elif ct.get_entity_type() == EntityType.BUILDER_BOT:
            self._run_builder(ct)

    def _run_core(self, ct: Controller) -> None:
        if self._spawned >= 5:
            return
        ti, _ = ct.get_global_resources()
        cost, _ = ct.get_builder_bot_cost()
        if ti < cost:
            return
        pos = ct.get_position()
        for d in _DIRS:
            sp = pos.add(d)
            if ct.can_spawn(sp):
                ct.spawn_builder(sp)
                self._spawned += 1
                return

    def _run_builder(self, ct: Controller) -> None:
        pos = ct.get_position()
        my_team = ct.get_team()

        best_target: Position | None = None
        best_dist = 999999

        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) == my_team:
                continue
            if ct.get_entity_type(bid) not in _TARGETS:
                continue
            bp = ct.get_position(bid)
            d = abs(bp.x - pos.x) + abs(bp.y - pos.y)
            if d < best_dist:
                best_dist = d
                best_target = bp

        if best_target is None:
            for bid in ct.get_nearby_buildings():
                if ct.get_team(bid) == my_team:
                    continue
                bp = ct.get_position(bid)
                d = abs(bp.x - pos.x) + abs(bp.y - pos.y)
                if d < best_dist:
                    best_dist = d
                    best_target = bp

        if best_target is None:
            w, h = ct.get_map_width(), ct.get_map_height()
            best_target = Position(w // 2, h // 2)

        if pos == best_target and ct.can_fire(pos):
            ct.fire(pos)
            return

        d = pos.direction_to(best_target)
        _move_with_road(ct, pos, d)

        new_pos = ct.get_position()
        if new_pos == best_target and ct.can_fire(new_pos):
            ct.fire(new_pos)


def _move_with_road(ct: Controller, pos: Position, d: Direction) -> None:
    if d == Direction.CENTRE:
        return
    target = pos.add(d)
    if ct.can_move(d):
        ct.move(d)
        return
    if ct.can_build_road(target):
        ct.build_road(target)
        if ct.can_move(d):
            ct.move(d)
            return
    for dd in _DIRS:
        adj = pos.add(dd)
        if ct.can_move(dd):
            ct.move(dd)
            return
        if ct.can_build_road(adj):
            ct.build_road(adj)
            if ct.can_move(dd):
                ct.move(dd)
                return
