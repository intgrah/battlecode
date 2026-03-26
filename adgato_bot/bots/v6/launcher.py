"""Launcher unit logic for v6."""

import random

from cambc import Controller, EntityType

from utils import king_dist


def run_launcher(player, ct: Controller) -> None:
    pos = ct.get_position()
    my_team = ct.get_team()

    # Find team core and enemy core positions
    core_pos = None
    enemy_core_pos = None
    for bid in ct.get_nearby_buildings():
        if ct.get_entity_type(bid) == EntityType.CORE:
            if ct.get_team(bid) == my_team:
                core_pos = ct.get_position(bid)
            else:
                enemy_core_pos = ct.get_position(bid)

    # If an enemy bot is adjacent, launch it away from our core (or furthest tile)
    for uid in ct.get_nearby_units():
        if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
            continue
        if ct.get_team(uid) == my_team:
            continue
        bp = ct.get_position(uid)
        if bp.distance_squared(pos) > 2:
            continue
        # Find best tile to launch enemy to — away from our core, or furthest
        targets = [tile for tile in ct.get_nearby_tiles() if ct.can_launch(bp, tile)]
        if targets:
            if core_pos is not None:
                best_dist = max(king_dist(t, core_pos) for t in targets)
                best = [t for t in targets if king_dist(t, core_pos) == best_dist]
            else:
                best_dist = max(king_dist(t, pos) for t in targets)
                best = [t for t in targets if king_dist(t, pos) == best_dist]
            ct.launch(bp, random.choice(best))
            print(f"Launcher: launched enemy bot away to {best[0]}")
            return

    # If we can see enemy core, launch any adjacent builder onto an enemy conveyor
    if enemy_core_pos is not None:
        # Find adjacent allied builder
        for uid in ct.get_nearby_units():
            if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
                continue
            if ct.get_team(uid) != my_team:
                continue
            bp = ct.get_position(uid)
            if bp.distance_squared(pos) > 2:
                continue
            # Find enemy conveyor we can launch onto
            for bid in ct.get_nearby_buildings():
                etype = ct.get_entity_type(bid)
                if etype not in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR, EntityType.SPLITTER, EntityType.BRIDGE):
                    continue
                if ct.get_team(bid) == my_team:
                    continue
                tile = ct.get_position(bid)
                if ct.can_launch(bp, tile):
                    ct.launch(bp, tile)
                    print(f"Launcher: launched builder onto enemy conveyor at {tile}")
                    return
            break
        return

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
