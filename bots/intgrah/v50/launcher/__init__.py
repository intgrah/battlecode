from cambc import Controller, EntityType, Position
from unit import Unit

_WALKABLE = frozenset(
    (
        EntityType.ROAD,
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
        EntityType.BRIDGE,
    ),
)

_MY_TRANSPORT = frozenset(
    (
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
        EntityType.BRIDGE,
    ),
)


class Launcher(Unit):
    def __init__(self, _ct: Controller) -> None:
        pass

    def run(self, ct: Controller) -> None:
        pos = ct.get_position()
        my_team = ct.get_team()

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

        good: list[tuple[int, Position]] = []
        bad: list[tuple[int, Position]] = []
        for tile in ct.get_nearby_tiles():
            if ct.get_tile_builder_bot_id(tile) is not None:
                continue
            bid = ct.get_tile_building_id(tile)
            if bid is None:
                continue
            etype = ct.get_entity_type(bid)
            team = ct.get_team(bid)
            if etype not in _WALKABLE:
                continue
            if etype == EntityType.CORE and team == my_team:
                continue
            priority = tile.distance_squared(pos)
            if team == my_team and etype in _MY_TRANSPORT:
                bad.append((priority, tile))
            else:
                good.append((priority, tile))

        good.sort(reverse=True)
        bad.sort(reverse=True)

        for bp in enemy_bots:
            for _, tile in good:
                if ct.can_launch(bp, tile):
                    ct.launch(bp, tile)
                    return
            for _, tile in bad:
                if ct.can_launch(bp, tile):
                    ct.launch(bp, tile)
                    return
