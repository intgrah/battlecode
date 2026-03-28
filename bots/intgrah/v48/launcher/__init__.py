from cambc import Controller, EntityType, Position, Team
from unit import Unit


class Launcher(Unit):
    def __init__(self, ct: Controller) -> None:
        pass

    def run(self, ct: Controller) -> None:
        pos = ct.get_position()
        my_team = ct.get_team()

        friendly_bots: list[Position] = []
        enemy_bots: list[Position] = []

        for uid in ct.get_nearby_units():
            if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
                continue
            bp = ct.get_position(uid)
            if bp.distance_squared(pos) > 1:
                continue
            if ct.get_team(uid) == my_team:
                friendly_bots.append(bp)
            else:
                enemy_bots.append(bp)

        en_core = _find_enemy_core(ct, my_team)

        if friendly_bots:
            for bp in friendly_bots:
                target = _best_key_target(ct, bp, my_team, en_core)
                if target is not None and ct.can_launch(bp, target):
                    ct.launch(bp, target)
                    return

        for bp in enemy_bots:
            target = _farthest_launchable(ct, pos, bp)
            if target is not None and ct.can_launch(bp, target):
                ct.launch(bp, target)
                return


def _find_enemy_core(ct: Controller, my_team: Team) -> Position | None:
    for bid in ct.get_nearby_buildings():
        if ct.get_entity_type(bid) == EntityType.CORE and ct.get_team(bid) != my_team:
            return ct.get_position(bid)
    return None


def _best_key_target(
    ct: Controller,
    bot_pos: Position,
    my_team: Team,
    en_core: Position | None,
) -> Position | None:
    best: Position | None = None
    best_dist = 999999
    for tile in ct.get_nearby_tiles():
        if not ct.can_launch(bot_pos, tile):
            continue
        bid = ct.get_tile_building_id(tile)
        if bid is None:
            continue
        if ct.get_team(bid) == my_team:
            continue
        etype = ct.get_entity_type(bid)
        if etype not in (
            EntityType.CONVEYOR,
            EntityType.BRIDGE,
            EntityType.SPLITTER,
            EntityType.ARMOURED_CONVEYOR,
            EntityType.HARVESTER,
        ):
            continue
        d = tile.distance_squared(en_core) if en_core is not None else 0
        if d < best_dist:
            best_dist = d
            best = tile
    return best


def _farthest_launchable(
    ct: Controller,
    launcher_pos: Position,
    bot_pos: Position,
) -> Position | None:
    best: Position | None = None
    best_dist = 0
    for tile in ct.get_nearby_tiles():
        if not ct.can_launch(bot_pos, tile):
            continue
        bid = ct.get_tile_building_id(tile)
        if bid is not None and ct.get_entity_type(bid) == EntityType.BRIDGE:
            continue
        d = max(abs(tile.x - launcher_pos.x), abs(tile.y - launcher_pos.y))
        if d > best_dist:
            best_dist = d
            best = tile
    return best
