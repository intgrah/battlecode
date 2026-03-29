from cambc import Controller, EntityType, Position
from unit import Unit

_WALKABLE = frozenset((EntityType.ROAD, EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR, EntityType.SPLITTER))


class Launcher(Unit):
    def __init__(self, ct: Controller) -> None:
        self._core_pos: Position | None = None

    def run(self, ct: Controller) -> None:
        pos = ct.get_position()
        my_team = ct.get_team()

        if self._core_pos is None:
            for bid in ct.get_nearby_buildings():
                if ct.get_entity_type(bid) == EntityType.CORE and ct.get_team(bid) == my_team:
                    self._core_pos = ct.get_position(bid)
                    break

        enemy_bots: list[Position] = []
        for uid in ct.get_nearby_units():
            if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
                continue
            if ct.get_team(uid) == my_team:
                continue
            bp = ct.get_position(uid)
            if bp.distance_squared(pos) <= 1:
                enemy_bots.append(bp)

        if not enemy_bots:
            return

        targets: list[tuple[int, Position]] = []
        core = self._core_pos
        for tile in ct.get_nearby_tiles():
            bid = ct.get_tile_building_id(tile)
            if bid is None:
                continue
            etype = ct.get_entity_type(bid)
            if etype not in _WALKABLE and not (etype == EntityType.CORE and ct.get_team(bid) == my_team):
                continue
            if ct.get_tile_builder_bot_id(tile) is not None:
                continue
            d = (tile.x - core.x) ** 2 + (tile.y - core.y) ** 2 if core is not None else 0
            targets.append((d, tile))

        targets.sort(reverse=True)

        for bp in enemy_bots:
            for _, tile in targets:
                if ct.can_launch(bp, tile):
                    ct.launch(bp, tile)
                    return
