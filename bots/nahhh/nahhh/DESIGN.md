# tree_denial_clean Design (v57)

## Architecture Overview

Ti-only economy. All builders share one `Player` class. No dedicated roles — every builder is a generalist that does econ, defense, and offense based on what it sees.

**Spawning**: reserve-based with no hard cap. First 4 spawn quickly (builder cost + per-builder reserve). Beyond 4 need steeper reserve (2x builder cost). Emergency spawn bypasses reserve when enemy bots detected near core.

## Builder Lifecycle

### Phase 1: Econ (seek ore → harvest → connect)
- 4 sectors (NE/SE/SW/NW), marker-based claiming, lowest ID wins conflicts
- Exploration sweeps outward with density scaling by radius
- Ore picking scores by walk distance + 2x connect distance, with sector bonus
- After 2+ harvesters, considers enemy-half ore (expansion)
- Builds harvester, routes conveyor/bridge chain to nearest unsaturated tree node or core
- Connect-back uses A* chain planning with conveyor + bridge edges

### Phase 2: Maintenance (patrol chain, repair, defend)
- Triggers when: 4+ harvesters connected, OR 1+ harvesters and sector exhausted
- Patrols own chain nodes sorted by proximity to core (trunk first, branches later)
- **Chain repair**: detects gaps in any known chain (own or other builders'), rebuilds with stored direction. Rebuilds as splitter if own turret is adjacent.
- **Reactive gunner defense**: detects enemy turrets near our infra or in our half, places gunner to counter. Ammo from adjacent harvester or splitter tap.
- **Opportunistic healing**: heals adjacent damaged buildings. Stops healing after 10 turns of sustained damage (futile without killing the turret).

### Phase 3: Offense (advance, sentinel, gunner)
- Triggers when: sector exhausted, no ore found, not in maintenance
- Walks toward nearest known enemy building (skips turrets to avoid fire). Falls back to enemy core (confirmed or 180° guess).
- **Opportunistic sentinels**: places sentinels on exposed enemy Ti harvesters (no enemy turrets adjacent). Facing scored by enemy building coverage + core direction bias. Evaluated when adjacent with full vision.
- **Offensive gunners**: targets enemy core (highest priority) and turrets. Ammo from adjacent enemy Ti harvester (direct), own harvester, or chain-routed from nearby secured harvester/ore.

## Turret Fire Control

### Sentinels (`_run_sentinel`)
Priority: turrets (0) > transport (1) > core (2) > bots/harvesters (3) > roads (4).
- Never shoots harvesters feeding our turrets (checks for own turret adjacent)
- Friendly fire check: skips tiles with allied bots

### Gunners (`_run_gunner`)
Priority: turrets (50) > transport (20) > harvesters (15) > bots (10) > roads (5).
- Rotates 45° toward targets when current facing has none (only if has ammo)
- `get_stored_resource()` check prevents wasteful rotation without ammo

### Launchers (`_run_launcher`)
Throws enemy bots away from our infrastructure. Prefers throwing toward map edges.

## Key Mechanisms

### Connect-Back (`_run_connect_back`)
A*-planned chain from `chain_end` toward terminal (unsaturated tree node or core 3x3). Also used for offensive ammo chains (gunner pos added as terminal).

### Chain Repair (`_check_chain_repair`)
Scans `my_chain_dirs` (cached directions for all visible friendly conveyors) for missing buildings. Any builder can repair any chain. Escalates to gunner if enemy turret is on repair tile.

### Turret Avoidance (`_build_walk_cache`)
Enemy turret attack tiles added to `_wc_danger` set with +8 A* cost. Launchers use dummy direction (omnidirectional). Always active (not disabled during gunner builds — builders self-heal instead).

### Offensive Attack System
1. `_find_attack_target`: core (tier 0) > turrets (tier 1) > harvesters (tier 2)
2. `_pick_gunner_for_target`: tile within r²≤13 with LoS, not on enemy core, has non-facing ammo path
3. `_find_ammo_for_gunner`: direct (adjacent harvester) > chain-routed (secured enemy harvester or ore within dist²≤100)
4. Chain routes from ammo source to gunner pos via connect-back

### Emergency Core Defense
Core spawns builder immediately (bypass reserve) when enemy units detected in vision via `get_nearby_units`.

## Ammo Mechanics
- Turrets can't accept ammo from the tile they FACE (accept from 7 other directions)
- Harvesters output to ANY cardinal-adjacent building (own or enemy)
- Conveyors accept from ANY direction, output in facing direction only
- Splitters accept from back only, output forward + 2 sides
- Gunner rotation is 45° per step, 10 Ti, 1-turn cooldown

## Known Weaknesses
- **Core defense** — builders patrol chains far from core, arrive late to attacks
- **Gunner ammo validation** — some gunners placed without working ammo feed
- **TLEs** — 37-82 per match on server (chain cache rebuild every turn may be expensive)
- **Over-spawning** — 49 units on long games, reserve formula doesn't reflect maintenance builders
- **No launchers** — don't place launchers for area denial
- **No barriers** — don't block tiles around core/harvesters
