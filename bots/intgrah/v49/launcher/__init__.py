from cambc import Controller, EntityType, Position, Team
from unit import Unit


class Launcher(Unit):
    def __init__(self, ct: Controller) -> None:
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

        jail = _find_jail_cell(ct, pos, my_team)
        if jail is not None:
            for bp in enemy_bots:
                if ct.can_launch(bp, jail):
                    ct.launch(bp, jail)
                    return

        upstream = _find_upstream_launcher(ct, pos, my_team)
        if upstream is not None:
            for bp in enemy_bots:
                if ct.can_launch(bp, upstream):
                    ct.launch(bp, upstream)
                    return


def _find_jail_cell(
    ct: Controller, my_team: Team,
) -> Position | None:
    for tile in ct.get_nearby_tiles():
        bid = ct.get_tile_building_id(tile)
        if bid is None:
            continue
        if ct.get_entity_type(bid) != EntityType.ROAD:
            continue
        if ct.get_team(bid) != my_team:
            continue
        core_adj = 0
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if dx == 0 and dy == 0:
                    continue
                np = Position(tile.x + dx, tile.y + dy)
                nbid = ct.get_tile_building_id(np)
                if nbid is not None and ct.get_entity_type(nbid) == EntityType.CORE and ct.get_team(nbid) == my_team:
                    core_adj += 1
        if core_adj >= 2:
            return tile
    return None


def _find_upstream_launcher(
    ct: Controller, pos: Position, my_team: Team,
) -> Position | None:
    best: Position | None = None
    best_id = -1
    for bid in ct.get_nearby_buildings():
        if ct.get_entity_type(bid) != EntityType.LAUNCHER:
            continue
        if ct.get_team(bid) != my_team:
            continue
        if bid <= ct.get_id():
            continue
        bp = ct.get_position(bid)
        if bp == pos:
            continue
        if bid > best_id:
            best_id = bid
            best = bp
    return best
