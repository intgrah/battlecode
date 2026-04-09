# Game Facts & Invariants for v7 Bot

Reference for code reviews and bug hunting. Every claim here is from the
official docs. Code that contradicts these facts is **buggy**.

---

## Map & Tiles

- Map: 20x20 to 50x50, symmetric (reflection or rotation).
- Tile types: EMPTY, WALL, ORE_TITANIUM, ORE_AXIONITE.
- Walls: impassable, no building can be placed, blocks gunner LoS.
- Ore: walkable (builders can walk on ore). Only harvesters/foundries can be
  built on ore. Conveyors, roads, barriers, bridges, turrets CANNOT be placed
  on ore.

## Builder Bot (only mobile unit)

- 40 HP, costs 30 Ti, 20% scale, vision r²=20, action r²=2.
- **Walks on:** conveyors, splitters, armoured conveyors, bridges, roads,
  allied core, markers — ALL regardless of team. Direction doesn't matter.
- **Cannot walk on:** walls, enemy core, harvesters, barriers, gunners,
  sentinels, breaches, launchers, foundries.
- **Build/heal/destroy:** action r²=2 (must be on or adjacent to target tile).
- **Heal:** 4 HP for 1 Ti to ALL friendly entities on target tile.
- **Fire (attack building on OWN tile):** 2 dmg for 2 Ti via `can_fire()`/`fire()`.
  Only attacks building the bot is standing on. Cannot attack adjacent buildings.
- **Destroy friendly:** free, unlimited per round. Can destroy ANY own building.
- **Cannot destroy enemy buildings** (except via fire on own tile).
- **Self-destruct:** does NO damage. Just removes the bot.
- **If bot stands on a building:** only walkable buildings can be built there.
  Turret attacks hit ONLY the bot, not the building underneath.

## Buildings — Construction Rules

- Cannot build on a tile that already has a building, EXCEPT:
  - **Markers:** any team can build over markers (auto-destroys them).
- One marker per round per unit, separate from action cooldown.
- Cost scaling: additive. `cost = floor(scale * base_cost)`. Scale starts 1.0x.

## Buildings — Types

| Building | HP | Cost | Scale | Notes |
|---|---|---|---|---|
| Road | 5 | 1 Ti | 0.5% | Walkable |
| Marker | 1 | free | 0% | u32 value. Not walkable. Any team builds over. Don't block gunner LoS |
| Barrier | 30 | 3 Ti | 1% | Blocks space. Not walkable |
| Conveyor | 20 | 3 Ti | 1% | Cardinal only. 3 inputs, 1 output. Walkable |
| Splitter | 20 | 6 Ti | 1% | Cardinal only. 1 input (back), 3 rotating outputs (fwd/left/right). LRU priority. Walkable |
| Bridge | 20 | 20 Ti | 10% | Teleport to tile within r²≤9. Accepts from ALL directions. Walkable |
| Armoured Conveyor | 50 | 5 Ti + 5 refined Ax | 1% | Like conveyor but immune to builder fire attacks. Walkable |
| Harvester | 30 | 20 Ti | 5% | Must be on ore. Outputs every 4 rounds LRU. First output immediate on build. NOT walkable |
| Foundry | 50 | 40 Ti | 50% | Accepts input/output any side. Ti + raw Ax → refined Ax. NOT walkable |
| Core | 500 | — | — | 3x3. Vision r²=36, action r²=8 from centre. Allied core is walkable |

## Turrets (common rules)

- Face one of 8 directions.
- **Receive ammo from non-facing sides.** Diagonal turrets can be fed from all
  4 cardinal sides.
- Hold max one stack (10 resources), only accept when empty.
- Raw axionite fed to turrets is **destroyed**.
- Resources can be sent to enemy buildings — careful with conveyor placement.
- **If a builder bot stands on a turret, attacks hit ONLY the bot.**

| Turret | HP | Cost | Scale | Range r² | Damage | Reload | Ammo/shot | Notes |
|---|---|---|---|---|---|---|---|---|
| Gunner | 40 | 10 Ti | 10% | 13 | 10 (40 w/ refined Ax) | 1 | 2 Ti | Fires along forward ray |
| Sentinel | 30 | 30 Ti | 20% | 32 | 18 | 3 | 10 Ti | Hits within 1 king-move of facing line. Refined Ax: +5 stun |
| Breach | 60 | 15 Ti + 10 Ax | 10% | 13 | 40 + 20 splash | 1 | 5 refined Ax only | 180° cone. Friendly fire on splash (not self). Ti/raw Ax fed = destroyed |
| Launcher | 30 | 20 Ti | 10% | 26 (throw) | — | 1 | **NO AMMO** | Throws adjacent bots. No facing. Action r²=2 pickup |

## Gunner LoS (firing ray)

Walk forward ray from gunner position in facing direction:
1. **Wall:** blocks LoS, NOT targetable → stop, return nothing.
2. **Marker:** targetable but DOESN'T block LoS → skip over.
3. **Any other building:** blocks LoS AND is targetable.
   - Enemy → fire at it.
   - Friendly → blocked, stop.
4. **Builder bot on tile:** blocks LoS, targetable. If bot is on a building,
   attack hits ONLY the bot.
5. **Friendly builder bot:** blocks LoS (can't fire through own bots).
6. Range: r²≤13 from gunner position.

## Resources & Transport

- Ti: start 500, +10 passive every 4 rounds.
- Ax: start 0, raw/refined.
- Resources move in stacks of 10 via conveyors and bridges.
- Raw Ax delivered to core or turrets is **destroyed** — refine first.
- Core converts refined Ax to Ti: 1 Ax → 4 Ti via `c.convert(amount)`.
- Harvesters output every 4 rounds, LRU direction priority.
- Conveyors: 3 inputs, 1 output (cardinal).
- Splitters: 1 input (back), 3 outputs (fwd/left/right), LRU priority.
- Bridges: accept from all directions, output to target tile.

## Danger Zones

- Launchers: throw r²=26. Builder bots thrown to any bot-passable tile in
  range. Mark as hard-block in nav.
- Gunners: fire ray r²=13. Mark as soft-avoid in pathfinding.
- Sentinels: arc within 1 king-move of facing line, r²=32.

## Communication

- Markers only — each unit is an isolated Python instance, no shared globals.
- Can overwrite own markers but NOT enemy markers.
- Any team can BUILD OVER any marker (auto-destroy).

## Win Conditions

- Destroy enemy core (500 HP).
- Max 2000 rounds.
- Tiebreakers: refined Ax delivered > Ti delivered > harvesters alive > Ax stored > Ti stored > coin flip.

---

## Code Invariants (our bot)

These are rules our code must follow, derived from the above:

### Routing (chain_astar.py)
- NEVER route conveyors through ore tiles.
- NEVER route through walls.
- Bridge hops must satisfy r²≤9.
- AttackAstar: only route through tiles we can build on (empty, any marker,
  own road, own barrier). No friendly transport, no enemy buildings.
- ChainAstar: can reuse existing friendly transport at zero cost.

### Building (builder.py)
- Before placing conveyor/bridge: verify tile is not wall/ore AND has no
  non-removable building.
- Before placing gunner: verify tile is buildable AND not enemy-owned.
- Before placing harvester: verify tile IS ore.
- `_destroy_friendly` only removes roads/markers. `_destroy_friendly_for_attack`
  also removes barriers. Neither removes conveyors/bridges.
- After destroying/building: UPDATE `s.building[idx]` to avoid stale state.

### Path invalidation
- Check for walls AND ore (not just walls).
- Check for friendly non-removable buildings (recompute).
- Enemy buildings on attack path: DON'T invalidate (clearing gunner handles).
- When clearing path in _build_at_gap: use correct variable (_connect_path vs
  _attack_path based on mode).

### Gunner LoS (_has_los / _scan_ray)
- Walls: block, not targetable → return None / break.
- Markers: skip (don't block LoS).
- Other buildings: block + targetable (enemy=target, friendly=blocked).
- Builder bots: block LoS. Enemy=targetable, friendly=blocked.

### Cut feed
- Skip launchers (no ammo — feeding them is harmless).
- Only cut feed to gunners, sentinels, breaches.

### Defense
- Reactive gunner: only trigger for enemy bots that are ACTUALLY attacking
  (building HP < max_hp), not just passing through.
- Barrier removal: remove own barriers on ore when no nearby enemy threat,
  so harvesters can be placed.
