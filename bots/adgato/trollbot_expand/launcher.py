"""Launcher unit logic for trollbot — yeet enemy builders away from bridges."""

from cambc import Controller, EntityType, Position
from pathfinding import _ALL_DIRS
from utils import in_bounds


def _adjacent_to_core(bp: Position, core: Position) -> bool:
    """True if builder bot is on a cardinal at king distance 2 from core."""
    return (bp.x == core.x or bp.y == core.y) and max(abs(bp.x - core.x), abs(bp.y - core.y)) == 2


def _try_launch(ct: Controller, bp: Position, my_team: object, core: Position) -> bool:
    """Try to launch enemy builder at bp. Returns True if launched."""
    # Try to launch onto a friendly conveyor first
    for cbid in ct.get_nearby_buildings():
        if ct.get_entity_type(cbid) == EntityType.CONVEYOR and ct.get_team(cbid) == my_team:
            cp = ct.get_position(cbid)
            print(f"considering conveyor {cbid} {bp} {cp}")
            if ct.can_launch(bp, cp):
                ct.launch(bp, cp)
                return True
            
    if core is not None and _adjacent_to_core(bp, core):
        return False

    # Try to launch adjacent to a friendly launcher with a larger ID, then lesser
    my_id = ct.get_id()
    for compare in (lambda lid: lid > my_id, lambda lid: lid < my_id):
        for lbid in ct.get_nearby_buildings():
            if (
                ct.get_entity_type(lbid) == EntityType.LAUNCHER
                and ct.get_team(lbid) == my_team
                and compare(lbid)
            ):
                print(f"considering lbid {lbid}")
                lp = ct.get_position(lbid)
                for d in _ALL_DIRS:
                    adj = lp.add(d)

                    if in_bounds(ct, adj) and ct.can_launch(bp, adj):
                        bid = ct.get_tile_building_id(adj)
                        if bid is not None and bid in (EntityType.BRIDGE, EntityType.SPLITTER):
                            continue
                        ct.launch(bp, adj)
                        return True

    # Otherwise launch anywhere valid
    for tile in ct.get_nearby_tiles():
        print(f"considering tile {tile}")
        bid = ct.get_tile_building_id(tile)
        if bid is not None and bid in (EntityType.BRIDGE, EntityType.SPLITTER):
            continue

        if ct.can_launch(bp, tile):
            ct.launch(bp, tile)
            return True

    return False


def run_launcher(player: object, ct: Controller) -> None:
    pos = ct.get_position()
    my_team = ct.get_team()

    # Find friendly core
    core_pos: Position | None = None
    for uid in ct.get_nearby_units():
        if ct.get_entity_type(uid) == EntityType.CORE and ct.get_team(uid) == my_team:
            core_pos = ct.get_position(uid)
            break

    # Find enemy builders, split by on-bridge vs not
    on_bridge: list[Position] = []
    off_bridge: list[Position] = []
    for uid in ct.get_nearby_units():
        if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
            continue
        if ct.get_team(uid) == my_team:
            continue
        bp = ct.get_position(uid)
        bid = ct.get_tile_building_id(bp)
        if bid is not None and (ct.get_entity_type(bid) in (EntityType.BRIDGE, EntityType.SPLITTER)):
            on_bridge.append(bp)
        else:
            off_bridge.append(bp)

    for bp in on_bridge:
        print("enemy on bridge")
        if _try_launch(ct, bp, my_team, core_pos):
            return

    for bp in off_bridge:
        if _try_launch(ct, bp, my_team, core_pos):
            return
