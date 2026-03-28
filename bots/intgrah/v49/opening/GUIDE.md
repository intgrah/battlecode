# Opening Book Creation Guide

## Overview

Each of the 23 known maps gets a hardcoded opening: a scripted sequence of
spawns, movements, and builds for the first ~20 turns. After the script
completes, builders fall through to the regular policy.

Openings are written in a compact DSL and stored in `opening/<mapname>.py`.

## Workflow

### 1. Read the map

Print the ASCII map, ore positions, wall layout, core positions, and symmetry
type. Key information:

- Core A and Core B positions
- All Ti and Ax ore positions with distances from both cores
- Walls and chokepoints between core and ores
- Symmetry type (ROT, HOR, VER) — scripts are authored for team A and
  automatically mirrored for team B

### 2. Decide strategy: rush or econ

**Rush** — viable when a sentinel can be placed within r²=32 of an enemy core
tile, fed by a harvester. The sentinel fires at the core and destroys it.

**Econ** — when rush is not viable (core too far from ores, too many walls).
Build harvesters, foundries, and deliver refined axionite to the core.

### 3. Decide builder count

Typically 2-3 builders. Every builder must have a purpose from turn 1. Do not
spawn idle builders.

### 4. Plan spawn positions

The core spawns builders on tiles within r²≤2 (the 8 adjacent tiles). **Spawn
builders in the direction they need to go.** If a builder needs to rush east,
spawn it on the east side of the core. This saves 1-2 turns.

Core spawns are encoded as `(dx, dy)` offsets from the core centre.

### 5. Plan parallel scripts

Each builder gets its own script. Scripts run simultaneously — plan for
parallelism:

- **Avoid collisions.** Two builders on the same tile block each other's
  movement. Use separate road paths or stagger timing.
- **Builders do action + move in one turn.** Build a road, then walk onto it.
  Build a harvester to the east, then move northeast. This is critical for
  speed.
- **Builders move like kings in chess.** All 8 directions, one tile per turn.
  Diagonal moves cover more ground.
- **Action before move.** The build executes first, then the move. A road
  placed to the south makes that tile walkable for the same turn's move.
- **Builders can only walk on roads, conveyors, and allied core.** Every tile
  the builder needs to walk on must have a road (or conveyor) placed first.

Target ~20 steps total across all builders. Front-load the critical path.

## DSL Reference

Steps are separated by `;` or newlines. Each step is one turn.

Format: `<build_dir> <building> [args], <move_dir>`

- `build_dir`: direction to build relative to current pos (n/ne/e/se/s/sw/w/nw)
- `move_dir`: direction to move (n/ne/e/se/s/sw/w/nw) or `x` for stay
- Both parts are optional: `x, e` = no build, move east. `e rd, x` = build
  road east, stay.

### Buildings

| Code | Building | Arguments |
|------|----------|-----------|
| `rd` | road | — |
| `h` | harvester | — |
| `c` | conveyor | facing direction (e.g. `c s` = conveyor facing south) |
| `sp` | splitter | facing direction |
| `sn` | sentinel | facing direction |
| `gn` | gunner | facing direction |
| `ln` | launcher | — |
| `ba` | barrier | — |
| `br` | bridge | target x y (absolute coords, e.g. `br 7 9`) |
| `f` | foundry | — |

### Examples

```
e rd, e           -- build road east, move east
e h, x            -- build harvester east, stay
ne sn e, x        -- build sentinel NE facing east, stay
w br 6 12, x      -- build bridge west targeting (6,12), stay
x, s              -- no build, move south
se ba, x          -- build barrier SE, stay
sw sp e, sw       -- build splitter SW facing east, move SW
```

## Verification Requirements

### Rush strategies

- **MUST destroy the enemy core before turn 200.**
- Test: `cambc run bots/intgrah/v49 bots/nothing/200 maps/<map>.map26`
- Test swapped: `cambc run bots/nothing/200 bots/intgrah/v49 maps/<map>.map26`
- Both must show `Core destroyed, turn N` where N < 200.
- `Core destroyed, turn 201` means **FAILURE** — the nothing/200 bot resigns
  at t200, so t201 means the core was not destroyed in time.
- If the rush is too slow, optimise: reduce wasted moves, eliminate
  collisions, use diagonal movement, use parallel builders.

### Econ strategies

Econ is for maps where a rush cannot kill the core in 200 turns. The goal is
to produce refined axionite and deliver it to the core. Refined axionite
delivered is the **first tiebreaker** — it wins games.

**Foundry pipeline:**

1. Ti harvester → conveyor/bridge → foundry input
2. Ax harvester → conveyor/bridge → foundry input (separate path, must not
   mix with Ti before the foundry)
3. Foundry outputs refined axionite → conveyor/bridge → core

**Foundry cost warning:** A foundry costs **120 Ti base** and adds **+100%
scaling**. This doubles the cost of everything after it. Plan the build order
carefully:

- Build cheap buildings first (roads 1Ti/+0.5%, barriers 3Ti/+1%)
- Build harvesters before the foundry (80Ti/+10% each)
- Build the foundry last among expensive buildings
- Ensure Ti income is flowing BEFORE building the foundry — you need the
  income to afford buildings at 2x+ scale

**Hard requirements:**

- **MUST have income of both Ti AND refined axionite (RAx).** Verify in the
  replay that both Ti mined > 0 and Ax mined > 0.
- All harvesters must be protected with **3 barriers** on non-output sides.
  The output side must connect to the transport network.
- All bridges must have a **launcher** adjacent to defend against enemy
  builders.
- The foundry must have a **launcher** adjacent.
- The foundry needs BOTH Ti and Ax input. Place it where Ti and Ax conveyor
  paths can reach it without mixing before arrival.
- All bridges must have a **valid target** within dist²≤9 that can accept
  resources. A bridge targeting an empty tile or a wall does nothing.

**Econ verification:**

- Test: `cambc run bots/intgrah/v49 bots/nothing/200 maps/<map>.map26`
- Check output: Ti mined > 0, Ax collected > 0 (refined axionite delivered)
- During debugging, policy fallback is disabled — scripted builders do nothing
  after their script ends. All econ must come from the script itself.

### Debugging mode

During development, the policy fallback is **disabled**. Scripted builders do
nothing after their script ends or fails. This ensures you are testing ONLY
the opening script, not the regular policy patching over mistakes. If a
builder goes idle, the script is incomplete or broken — fix it.

### Both strategies

- Must work as **both team A and team B**. The mirroring is automatic based on
  the map's symmetry type — just test both player orders.
- Check for red indicator dots in the replay — these indicate a script step
  failed. Green dots indicate the script completed successfully.
- Print output shows `[SCRIPT] FAIL move ...` when a move fails.

## Common Mistakes

1. **Forgetting roads.** Builders cannot walk on empty tiles. Every tile in the
   path needs a road placed before the builder walks there.
2. **Builder collisions.** Two builders on the same tile block each other. Use
   separate paths or stagger with `x, x` wait steps.
3. **Building on own tile.** Only roads and conveyors can be built on the
   builder's current tile. Harvesters, barriers, sentinels etc. must be built
   on an adjacent tile.
4. **Harvester not feeding sentinel.** Harvesters output to all 4 cardinal
   neighbours. Block 3 sides with barriers to force output to the sentinel.
   The sentinel must be on a cardinal side of the harvester, and the sentinel
   accepts ammo from non-facing directions.
5. **Sentinel not hitting core.** The sentinel fires along its facing direction
   ±1 king-move, within r²=32. The core is 3x3 — try all 9 tiles with
   `can_fire`. The sentinel code iterates core tiles, not just the centre.
6. **Bridge targeting wrong tile.** Bridge targets are absolute coordinates.
   They are mirrored automatically for team B.
7. **Spawn position wastes turns.** Spawn the builder on the side of the core
   closest to where it needs to go.

## File Structure

```
opening/
  __init__.py      -- Opening/Step types, registry
  parse.py         -- DSL parser
  mirror.py        -- Symmetry mirroring for team B
  identify.py      -- Map identification from core vision
  arena.py         -- Arena opening
  battlebot.py     -- Battlebot opening
  <mapname>.py     -- One file per map
  GUIDE.md         -- This file
```

## Registering an Opening

```python
from hardcode.known import KnownMap
from . import Opening, register
from .parse import parse_script

_B1 = parse_script(spawn_x, spawn_y, "script string")
_B2 = parse_script(spawn_x, spawn_y, "script string")

register(KnownMap.MAP_NAME, Opening(
    core_spawns=[(dx1, dy1), (dx2, dy2)],
    builder_scripts=[_B1, _B2],
))
```

Then add `from . import mapname as _mapname` to `opening/__init__.py`.
