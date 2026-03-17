# Meta Analysis

## Current meta (day 1, ~8 hours in)

Pure economy + kamikaze raids. No team uses turrets with ammo, foundries, or refined axionite effectively. Games are decided by tiebreaker at turn 2000.

### Economy

The conveyor network is everything. Harvesters produce Ti/Ax, conveyors route it to core. Income = connected harvesters × 2.5 Ti/turn (1 stack of 10 every 4 turns).

Key metrics:
- Harvesters connected (not just built)
- Core delivery rate (stacks/turn into core)
- Core input lanes (parallel conveyor entries -- more = higher throughput)
- Dead conveyor ratio (conveyors carrying 0 flow)
- Chain path ratio (chain length / straight-line distance)
- Scale cost (every building adds cumulative cost to all future buildings)

Top teams get 20-40 Ti/turn from 8-22 harvesters. Conveyor chain efficiency (income per harvester) varies 3-4x between teams.

### Attack

Self-destruct (20 dmg) one-shots a conveyor (20 HP). Destroying one mid-chain conveyor disconnects all upstream harvesters. ROI: 10 Ti builder cost → potentially 5+ Ti/turn of enemy income destroyed.

Nobody defends. Nobody repairs (except v15). Kamikaze raids are unopposed. Builder spam (50-100+ raiders) overwhelms through volume.

### Defense (unexploited)

Gunners (10 Ti, 10 dmg, r²=13) can kill builders (30 HP = 3 shots). But they need Ti ammo via conveyor, requiring a splitter to split chain flow. Nobody has implemented ammo routing.

Barriers (3 Ti, 30 HP) can block approach paths, forcing raiders into kill zones.

### Unexploited mechanics

- Splitters (6 Ti): split one input into 3 rotating outputs. Critical for ammo routing.
- Bridges (10 Ti): teleport stacks over dist² 9. Less scale than 3 conveyors. Nobody uses them.
- Launchers (20 Ti): throw builders across defenses. No ammo needed.
- Foundries (120 Ti, +100% scale): produce refined Ax for breach turrets. Nobody builds them.
- Sentinels (15 Ti, 20 dmg, r²=32): huge range, stun with refined Ax. Unused.
- Markers: 32-bit values on tiles. Barely used beyond spawn assignment. Could enable distributed coordination.

## Our bot (v15)

### Architecture

Utility-based agent. Each builder autonomously:
1. Scans environment (Percept: ore, enemies, broken chains, infrastructure density)
2. Scores possible actions (harvest, seek_ore, explore, repair, raid, raid_core)
3. Commits to highest-scoring action for ~15 turns
4. Re-evaluates when commitment expires or harvester opportunity appears

No hardcoded turn thresholds for role switching. Ti trend (rising/falling) drives repair urgency. Ti level drives raid willingness.

### Economy
- 8 initial builders, each assigned a spoke direction
- Conveyors built with `d.opposite()` (point back the way builder came)
- Ore tiles preserved for harvesters (skip_ore after income established)
- Explored block markers to avoid re-exploring (TAG_EXPLORED)

### Raiding
- Builders near enemy infrastructure with healthy Ti self-destruct on conveyors
- Idle builders (no ore found for 30+ turns) transition to raiding
- Replacement raiders spawned from core every 20 turns when Ti > 1500

### Repair
- Builders detect broken chains (conveyor outputting to empty tile)
- Repair score spikes when Ti is falling (income disrupted)
- 5/6 breaks repaired in tested games (v9 repairs 0/6)

### Weaknesses
- 69-92% dead conveyors (wasted scale from exploration branches)
- No ammo-fed turrets (gunners built without ammo are useless)
- No splitter-based resource routing
- No bridges for chain shortcuts
- Raids are opportunistic, not targeted at high-betweenness tiles
- Builder figure-8 circling around harvesters wastes conveyors

## Workflow

### Development
- `just snapshot` -- freeze current version, create next
- Iterate on latest version, test against previous versions
- `just match v15 v12` -- run + print stats

### Analysis pipeline
- `just stats <replay>` -- quick summary (winner, Ti, harvesters)
- `just economy <replay>` -- income curves, harvester connectivity
- `just flow <replay>` -- max flow, bottlenecks, core delivery timeline
- `just graph <replay>` -- chain tracing, path lengths, dead ends
- `just health <replay>` -- break/repair events, destruction causes, scale breakdown
- `just deep <replay>` -- connectivity timeline, builder activity, raid impact
- `just combat <replay>` -- damage, shots, self-destructs
- `just network <replay>` -- harvester connectivity, dead conveyors
- `just map <replay>` -- ASCII map visualization and heatmaps

### Ladder
- `just submit` -- upload latest version
- `just download <match_id>` -- download replays for analysis
- `just status` -- check rating

### Key lessons
- Always analyze replays before iterating. Aggregate scores hide root causes.
- Trace per-harvester connectivity over time to detect breaks and repairs.
- Count conveyor destruction causes to understand what's actually killing chains.
- Measure core delivery rate over time, not just final Ti collected.
- Scale cost is the silent killer -- 500+ dead conveyors at 1% each doubles all costs.
