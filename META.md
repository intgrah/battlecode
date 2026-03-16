# Meta Analysis (Early Stage)

Tournament started ~2 hours ago. Most teams are still figuring out conveyor chains. No combat has been observed in any top-tier match yet.

## Current meta: pure economy

Every match is decided by the resources tiebreaker at turn 2000. No team has destroyed an enemy core. The winning formula:

1. Spawn builders immediately
2. Build conveyors outward from core (`direction.opposite()` to form connected chains)
3. Build harvesters on any ore found
4. Never stop exploring

### What top teams do

**nibbly-finger** (top tier): 8 builders, ~400-600 conveyors, 7-11 harvesters. Wins by sheer exploration speed and chain efficiency. 20-30 Ti/turn income.

**Operation Blade** (mid tier now): 3 builders, conveyors only, systematic perimeter sweeps. Was dominant early but outpaced by teams with more builders.

**Code Monkeys** (low tier): 1 builder, road-out/conveyor-back. Reliable chains but slow exploration. ~5-8 Ti/turn.

### Key economy metrics
- First income timing (turn 5-30 is competitive)
- Harvester count and connectivity (100% connectivity is table stakes)
- Income rate (/turn, 15-30 is top tier)
- Dead conveyor ratio (wasted conveyors that carry no resources)

### Builder count
More builders = faster exploration = more harvesters = more income. The scaling cost (10% per builder) is offset by the income gained. 8 builders appears optimal currently. Diminishing returns beyond that.

### Conveyor chain design
- `d.opposite()`: each conveyor points back toward where the builder came from. Forms connected chains along the walked path.
- Skip ore tiles to preserve them for harvesters (but not before first income is flowing).
- Dead-end branches are acceptable; the cost (~1% scale each) is worth the exploration.

## Unexplored mechanics

### Combat
Nobody is attacking yet. Self-destruct (20 dmg) one-shots a conveyor (20 HP). Destroying one mid-chain conveyor disconnects all upstream harvesters. A single raider could cripple an enemy's income for the cost of one builder (10 Ti, 10% scale, scale refunded on death).

Turrets (gunner, sentinel, breach) are entirely unused. Ammo logistics via conveyors adds complexity. Likely needed once combat starts.

### Foundries and refined axionite
No team builds foundries (+100% scale is brutal). Refined Ax enables breach turrets and armoured conveyors. Not needed until combat becomes relevant.

### Bridges
Teleport resources over dist² 9. Could shortcut long conveyor chains or cross walls. No team observed using them effectively yet.

### Launchers
Throw builder bots within r²=26. Could enable deep raids without building roads through enemy territory. No team uses these.

### Markers for coordination
Mostly unused. Potential for distributed algorithms: ore location sharing, explored region broadcasting, chain endpoint advertising. Limited by 1 marker/turn and spatial locality.

### Barriers and defense
No team builds defensive structures. Once combat starts, barriers (30 HP, 3 Ti) could protect key conveyor links. Turret placement + ammo routing is the harder problem.

## Strategic outlook

The meta will shift from pure economy to economy + harassment once teams realize that destroying one enemy conveyor costs 10 Ti but removes 2.5+ Ti/turn of enemy income. First teams to implement targeted raids will dominate.

The endgame meta likely involves: strong economy (8+ builders, fast chain completion) + early raider deployment (turn 200-400) + defensive infrastructure near core (barriers, turrets).
