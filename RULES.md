# Cambridge Battlecode Rules

2-player turn-based strategy on Titan. Destroy enemy core (3x3, 500 HP). Max 2000 rounds. Maps 20x20-50x50, symmetric. 2ms CPU/unit/round.

## Win condition

Core destroyed = win. If tied at 2000 rounds: refined ax delivered > Ti delivered > harvesters alive > ax stored > Ti stored > coinflip.

## Resources

- Titanium (Ti): start 1000. Primary currency.
- Axionite (Ax): raw (converts to Ti when consumed) and refined (from foundry). Start 0.
- Moved in stacks of 10 via conveyors at end of round.
- Resources delivered to core add to global pool.
- Resources can be sent to enemy buildings.

## Cost scaling

`cost = floor(scale * base_cost)`, scale starts 1.0. Each build adds to scale (see % below). Destroying entities removes their contribution.

## Entities

### Core

500 HP, 3x3, vision r²=36, action r²=8 from centre. Spawns builder bots on its 9 tiles (1/round).

### Builder bot (only mobile unit)

30 HP | 10 Ti | 10% scale | vision r²=20 | action r²=2

- Moves on: conveyors (any), roads (any team), allied core. Diagonal OK.
- Actions: build (within action r²), heal 10 HP (friendly), destroy allied buildings (free, no cooldown), self-destruct (20 dmg to own tile).
- Can place 1 marker/round (no cooldown cost).
- Can only build walkable buildings on a tile containing a builder bot.

### Gunner

40 HP | 10 Ti | 10% | vision=action=attack r²=13
10 dmg (+10 w/ refined ax) | reload 1 | 2 ammo/shot
Targets closest non-empty tile in facing direction.

### Sentinel

30 HP | 15 Ti | 10% | vision=attack r²=32 | action r²=2
20 dmg | reload 4 | 10 ammo/shot
Hits tiles within 1 king-move of line in facing dir. Refined ax: +3 cooldown stun.

### Breach

60 HP | 30 Ti + 10 Ax | 10% | vision r²=10 | attack r²=5 | action r²=2
40 dmg + 20 splash (180° cone in facing dir) | reload 1 | 5 ammo (refined ax only)
Friendly fire on splash.

### Launcher

30 HP | 20 Ti | 10% | vision=attack r²=26 | action r²=2
Throws adjacent builder bots to target tile. No ammo. reload 1. No facing direction.

### Conveyor

20 HP | 3 Ti | 1% | 3 inputs, 1 output in facing dir.

### Splitter

20 HP | 6 Ti | 1% | 1 input (back), 3 rotating outputs (LRU priority).

### Bridge

20 HP | 10 Ti | 1% | Teleports stack to tile within dist² 9. Bypasses directional restrictions.

### Armoured conveyor

50 HP | 10 Ti + 5 refined Ax | 1% | Same as conveyor but tankier.

### Harvester

30 HP | 80 Ti | 10% | Must be on ore deposit. Outputs 1 stack every 4 rounds (first output immediate). Not a unit (auto-operates). Output priority: LRU.

### Foundry

50 HP | 120 Ti | 100% | Takes 1 stack Ti + 1 stack raw Ax, outputs 1 stack refined Ax. Any side I/O.

### Road

10 HP | 1 Ti | 0.5% | Walkable.

### Barrier

30 HP | 3 Ti | 1% | Blocks space.

### Marker

1 HP | Free | No cooldown. Stores u32. Only comms between units (each unit is isolated Python instance). Any team can build over markers. All units can place markers.

## Turret ammo

Ammo-based turrets (gunner/sentinel/breach) receive ammo from conveyors on non-facing sides. Only accept resources when completely empty.

## Communication

Markers only. No shared globals. Each unit runs in its own Python interpreter.

## API (Controller `ct`)

### Info

get_team/position/id/action_cooldown/move_cooldown/hp/max_hp/entity_type/direction/vision_radius_sq(id?) -> respective types
get_ammo_amount() get_ammo_type() get_gunner_target() -> turret-specific
get_bridge_target(id) get_stored_resource(id?)
get_tile_env(pos) get_tile_building_id(pos) get_tile_builder_bot_id(pos) is_tile_empty(pos) is_tile_passable(pos) is_in_vision(pos)
get_nearby_tiles/entities/buildings/units(dist_sq?) -> list
get_map_width/height() get_current_round() get_global_resources()->(Ti,Ax) get_scale_percent() get_cpu_time_elapsed()->us
get_marker_value(id)

### Cost

get\_{entity}\_cost() -> (Ti, Ax) for all buildable entities

### Actions

move(dir) can*move(dir)
spawn_builder(pos) can_spawn(pos) [core only]
build*{conveyor|splitter|armoured*conveyor|gunner|sentinel|breach}(pos, dir) + can* variants
build*{bridge}(pos, target) + can* variant
build*{harvester|road|barrier|foundry|launcher}(pos) + can* variants
heal(pos) can_heal(pos)
destroy(building_pos) can_destroy(building_pos) [allied buildings, free]
self_destruct()
fire(target) can_fire(target) [turrets]
launch(bot_pos, target) can_launch(bot_pos, target) [launcher]
place_marker(pos, value) can_place_marker(pos)

### Debug

draw_indicator_line(a, b, r, g, b) draw_indicator_dot(pos, r, g, b)

## Types

Team(A, B) EntityType(core, builder_bot, gunner, sentinel, breach, launcher, conveyor, splitter, armoured_conveyor, bridge, harvester, foundry, road, barrier, marker)
ResourceType(titanium, raw_axionite, refined_axionite) Environment(empty, wall, titanium_ore, axionite_ore)
Direction(north, northeast, east, southeast, south, southwest, west, northwest, centre) + delta(), rotate_left/right(), opposite()
Position(x, y) + distance_squared(other), add(dir), direction_to(other)
