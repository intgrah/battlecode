"""Launcher unit logic for v6."""

import random

from cambc import Controller, EntityType
from utils import king_dist


def run_launcher(player, ct: Controller) -> None:
    """If a builder is in the team core, launch it to a random tile outside the core."""
    pos = ct.get_position()
    my_team = ct.get_team()

    # Find team core position
    core_pos = None
    for bid in ct.get_nearby_buildings():
        if ct.get_entity_type(bid) == EntityType.CORE and ct.get_team(bid) == my_team:
            core_pos = ct.get_position(bid)
            break

    if core_pos is None:
        return

    # Find adjacent allied builder that is inside the core (king_dist <= 1 from core centre)
    bot_pos = None
    bot_id = None
    for uid in ct.get_nearby_units():
        if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
            continue
        if ct.get_team(uid) != my_team:
            continue
        bp = ct.get_position(uid)
        if bp.distance_squared(pos) <= 2 and bp.distance_squared(core_pos) <= 2:
            bot_pos = bp
            bot_id = uid
            break

    if bot_pos is None:
        player.launch_wait = 0
        player.launch_bot_id = None
        return

    # Reset wait if the builder bot changed
    if player.launch_bot_id is not None and player.launch_bot_id != bot_id:
        player.launch_wait = 0
    player.launch_bot_id = bot_id

    # Wait two turns before launching
    player.launch_wait += 1
    if player.launch_wait < 3:
        return

    # Collect all valid targets outside the core
    targets = []
    for tile in ct.get_nearby_tiles():
        if not ct.can_launch(bot_pos, tile):
            continue
        if king_dist(tile, core_pos) <= 2:
            continue
        targets.append(tile)

    print(f"launcher targets {len(targets)}")

    if targets:
        best_dist = max(king_dist(t, core_pos) for t in targets)
        best = [t for t in targets if king_dist(t, core_pos) == best_dist]
        ct.launch(bot_pos, random.choice(best))
        player.launch_wait = 0
