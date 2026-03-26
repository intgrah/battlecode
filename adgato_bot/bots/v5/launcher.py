"""Launcher unit logic for v5."""

from cambc import Controller, EntityType, Position
from utils import decode_waypoint, is_waypoint_marker, king_dist


def run_launcher(player, ct: Controller) -> None:
    """Throw adjacent allied builder toward team core (scout return) or enemy core (assault)."""
    pos = ct.get_position()
    my_team = ct.get_team()

    # Resolve core positions once on first run
    if player.core_pos is None:
        w, h = ct.get_map_width(), ct.get_map_height()

        # 1. Try waypoint marker
        for bid in ct.get_nearby_buildings():
            if ct.get_entity_type(bid) != EntityType.MARKER:
                continue
            if ct.get_team(bid) != my_team:
                continue
            val = ct.get_marker_value(bid)
            if not is_waypoint_marker(val):
                continue
            tx, ty, ex, ey = decode_waypoint(val)
            player.core_pos = Position(tx, ty)
            player.enemy_core = Position(ex, ey)
            break

        # 2. Try to find cores in vision
        if player.core_pos is None or player.enemy_core is None:
            for bid in ct.get_nearby_buildings():
                if ct.get_entity_type(bid) != EntityType.CORE:
                    continue
                core_pos = ct.get_position(bid)
                if ct.get_team(bid) == my_team:
                    player.core_pos = core_pos
                else:
                    player.enemy_core = core_pos

        # 3. Infer the missing core as the rotational mirror
        if player.core_pos is not None and player.enemy_core is None:
            player.enemy_core = Position(
                w - 1 - player.core_pos.x,
                h - 1 - player.core_pos.y,
            )
        elif player.enemy_core is not None and player.core_pos is None:
            player.core_pos = Position(
                w - 1 - player.enemy_core.x,
                h - 1 - player.enemy_core.y,
            )

    if player.core_pos is None or ct.get_action_cooldown() > 0:
        return

    # Find adjacent allied builder bot to throw
    bot_pos = None
    for uid in ct.get_nearby_units():
        if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
            continue
        if ct.get_team(uid) != my_team:
            continue
        bp = ct.get_position(uid)
        if bp.distance_squared(pos) <= 2:
            bot_pos = bp
            break

    if bot_pos is None:
        return

    # Throw toward team core (gets the builder closer to home)
    throw_target = player.core_pos
    bot_dist = king_dist(bot_pos, throw_target)
    best_target = None
    best_dist = bot_dist  # must improve on current distance
    best_far = 0  # tiebreak: farthest from launcher

    for tile in ct.get_nearby_tiles():
        if not ct.can_launch(bot_pos, tile):
            continue
        d = king_dist(tile, throw_target)
        d_far = king_dist(tile, pos)
        if d < best_dist or (d == best_dist and d_far > best_far):
            best_dist = d
            best_far = d_far
            best_target = tile

    if best_target is not None:
        ct.launch(bot_pos, best_target)
