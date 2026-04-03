# drewfett/v1 — Combat Strategy Plan

## Turret comparison

| | Sentinel | Gunner | Breach |
|---|---|---|---|
| Cost | 30 Ti, 20% scale | 10 Ti, 10% scale | 15 Ti + 10 Ax, 10% scale |
| HP | 30 | 40 | 60 |
| Range r² | 32 | 13 | 5 |
| Damage | 18 | 10 (30 w/ refined ax) | 40 + 20 splash |
| Reload | 3 rounds | 1 round | 1 round |
| Ammo/shot | 10 Ti | 2 Ti | 5 refined ax only |
| DPS | 6/round | 10/round | 40+/round |
| Coverage | Line + 1 king-move width | Closest in facing line | 180° cone |

**Sentinel for defense:** r²=32 covers ~6 tile radius. One sentinel near core covers most approach paths. 18 damage kills a builder (30 HP) in 2 shots (6 rounds). Expensive (20% scale) but one covers a lot.

**Gunner for offense/reactive:** Cheap (10% scale), fast reload, rotatable. Good for targeting a specific enemy building. Needs only 2 Ti ammo per shot. Best placed adjacent to enemy harvesters (free ammo via parasiting) or near our splitters.

**Ammo mechanics:** Turrets accept from any direction EXCEPT facing. Diagonal-facing turrets accept from all 4 cardinal sides. Splitters accept from back only, output to front + 2 sides.

## Defense strategy

### Goal
Prevent enemy from destroying our core and disrupting key infrastructure.

### When to defend
State-driven triggers (no round numbers):
- `len(state.my_harvesters) >= 2` and no friendly turrets within r²≤32 of core → place sentinel
- Enemy builder/turret spotted within r²≤36 of our core → emergency defense
- Flow disruption: `my_frac` dropping on key transport near core → investigate + defend

### Sentinel placement near core
- Place 1 sentinel covering the main approach from enemy core direction
- Facing: toward `en_core_pos` (or map center if unknown). Diagonal facing preferred (accepts ammo from all 4 cardinal sides)
- Position: adjacent to a conveyor/splitter that carries Ti (check `flow.ti[i] > 0`). This provides ammo — but we need to convert the adjacent conveyor to a splitter so flow splits toward the sentinel
- Alternatively: position adjacent to a harvester near core (direct Ti feed, no splitter needed)

### Ammo routing for defense
Option A (simple): Place sentinel adjacent to a Ti harvester near core. Harvester outputs to all cardinal neighbors — sentinel gets fed directly. No splitter needed.

Option B (if no harvester near core): Identify a conveyor near core with Ti flow. Destroy it, rebuild as splitter facing same direction. Splitter side output feeds sentinel. Risk: temporarily breaks the chain during rebuild.

For v1: use option A only. Option B deferred.

### Reactive gunner defense
When enemy turret detected near our infra:
- Find gunner position with LoS to enemy turret
- Place gunner adjacent to any Ti source (our harvester, our splitter, enemy harvester)
- Gunner needs only 2 Ti/shot — even slow ammo feed works
- Already implemented in `task_defend.py` (priority 180)

## Offense strategy

### Goal
Disrupt enemy economy and/or destroy enemy core.

### Phase 1: Parasitic sentinels (cheap, emerges from exploration)
- Builder exploring into enemy territory sees enemy Ti harvester
- Place sentinel adjacent to it — harvester feeds us ammo
- Face toward enemy core or high-value enemy infra
- Already partially implemented in `task_place_sentinel.py` (priority 40)
- Improve: score higher when builder is actually near enemy harvesters

### Phase 2: Targeted gunner strikes (mid-game)
- Use `en_frac` and `en_total` from flow sim to identify high-value enemy transport
- "High value" = tile where `en_total[i]` is highest (most enemy resources flow through)
- Place gunner to cut that tile — maximum economic damage per gunner
- Ammo: parasite from adjacent enemy harvester, or build forward harvester on enemy-side ore
- Needs new task: `ATTACK_INFRA`

### Phase 3: Core kill (late-game)
- When enemy core position is known and we have econ advantage
- Route gunners within r²≤13 of enemy core
- Need ammo chain from nearby ore/harvester to gunner
- Most complex — defer to v2

## Task priority table (proposed)

| Priority | Task | Trigger |
|---|---|---|
| 999 | HEAL_CORE | Core HP < max |
| 180 | DEFEND | Enemy turret near our infra |
| 150 | CONNECT_EXCESS_TI | Flow excess detected |
| 100 | HARVEST_TI | Unharvested Ti ore known |
| 90 | DEFEND_CORE | 2+ harvesters, no turret near core |
| 80/50/20 | EXPLORE | <30% / <50% / >50% map seen |
| 40 | PLACE_SENTINEL | Enemy Ti harvesters visible |
| 25/15 | PATROL | Staleness > 50 / else |
| 10 | HEAL_TURRET | Damaged friendly turret visible |

## Open questions

- How much scale cost is acceptable for defense? One sentinel (20%) is probably worth it. Two sentinels (40%) delays econ significantly.
- Should we place gunners proactively near core instead of sentinels? Cheaper (10% scale) but shorter range and need ammo routing.
- When do we switch from "defend and grow" to "attack"? Probably when we have vision of enemy infra from exploration.
- Splitter conversion for ammo: when is it worth temporarily breaking a chain to feed a turret?
