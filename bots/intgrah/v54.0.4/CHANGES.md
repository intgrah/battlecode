# v54 Session Changes

Baseline: v54 = v53.4.0 port + micro fixes over v52_live. Goal of the
session: beat `drewfett/v52_live` in 60-game sweeps on the `bc16`
hetzner server.

## Results

All sweeps `drewfett/v54 vs drewfett/v52_live`, 60 games each, bc16.

| Change | W-L | % | Δ |
|---|---|---|---|
| Baseline v54 | 34-26 | 56.7% | — |
| + Bridges in A* (nb_count=20, bridge cost 8x conv) | 41-19 | 68.3% | +7 |
| + Stomp guard + spawn fix + unseen cost bump | 44-16 | 73.3% | +3 |
| + Team unit cap 25 → 40 | 47-13 | 78.3% | +3 |
| + Gunner unfed-reset fix + sentinel self-destruct | 45-15 | 75.0% | -2 (noise) |

At n=120 across the last two sweeps the cumulative is 92-28 = 76.7%,
95% CI roughly [69%, 84%] — clearly significant vs the 54% team-A
bias floor observed in v52_live self-play.

Castle_keep went from losing game 59 (30880 vs 87430 Ti) at baseline
to winning convincingly (68370 vs 25200) after the bridge fix.

## Changes by file

### `builder/algorithms/pathfind.py` — bridges as A* edges

Two bugs and one enhancement, in one file.

1. **Bucket A* (`nb_count = 5`) was silently dropping high-cost
   edges.** Dial's algorithm requires `nb_count ≥ max_edge_weight +
   heuristic_delta`. Cardinal conveyors cost 1–2, diagonals cost 5–6,
   so 5 was already on the edge (relaxation saved it). Adding bridge
   edges (cost ~8–12) would have been dead code because bridge nodes
   land in bucket indices that get wiped before their turn comes.
   Bumped to `nb_count = 20`.

2. **Bridge cost ratio was wrong vs adgato.** Adgato: `COST_CONV=3`,
   `COST_BRIDGE=30` (10x). v54 had conv=1 (for empty tiles) but kept
   bridge at 30 → 30x ratio. A* would only bridge when the detour
   cost was 30+ tiles, which basically never happens. Changed to
   `COST_BRIDGE_EXTRA = 7` so bridge = 1+7 = 8 for empty destinations
   — 8x conv, slightly more bridge-happy than adgato.

3. **Bridges as A* neighbors.** Added 24 `BRIDGE_DELTAS` to
   `_CONV_NEIGHBORS` — all (dx, dy) with `0 < dx²+dy² ≤ 9` and
   `|dx|+|dy| ≠ 1`. Static list, works for both `_run` and
   `_extract_path` without structural changes. `cost[ni] < INF`
   check in the neighbor loop already rejects walls and enemy
   buildings, which is all a bridge needs — intermediate tiles can
   be anything.

### `builder/state.py` — unseen conveyor cost penalty

`conveyor_cost_grid` was initialised to `[1] * n`, meaning unseen
tiles cost the same as seen empty terrain. A* treated fog as a free
highway — a 25-tile unmapped detour (25 cost) beat a single bridge
(30 cost) every time.

Changed init to `[5] * n`. With bridge cost 8, A* picks a bridge over
any fog detour longer than ~7 tiles. Seen tiles still overwrite the
init on first sight.

### `builder/task_attack.py` — attack-side gunner placement

Added `_gunner_chain_facing(pos)`: ray-casts each diagonal direction
(NE/SE/SW/NW) from `pos`, returns the first one whose forward ray
hits an enemy conveyor / armoured conveyor / splitter / bridge as its
first building (within gunner attack r²=13). Diagonal-facing because
diagonal turrets can be fed from all 4 cardinal sides.

In the attack branch of `run_attack`, when adjacent to an enemy
harvester: count existing friendly gunners + sentinels around the
target. Max 1 of each. Try gunner first (if LoS to chain exists),
sentinel fallback (Ti ore only), barrier fallback. Replaces the old
"up to 2 sentinels" logic.

### `builder/task_defend.py` — stomp guard

Before: `gunner_facing` rejected ALL friendly non-road buildings
(too broad — we want to allow destroying friendly conveyors/splitters
/ bridges for turret placement). `sentinel_facing` had no guard at
all and was stomping friendly harvesters.

After: `_is_precious_friendly(b, team)` rejects only friendly
`Harvester`, `Foundry`, `Launcher` — the high-Ti, high-scale
buildings that must not be destroyed. Everything else (roads,
conveyors, splitters, bridges, markers) is destroy-OK. Applied to
both `gunner_facing` and `sentinel_facing`.

### `core/__init__.py` — live unit count, not cumulative spawns

The core's spawn gate used `self.spawned >= _MAX_BUILDERS = 12`,
which was monotonic: once 12 builders had ever been spawned across
the whole game, the core never spawned again — even if every one of
them died and the team was sitting on a huge Ti surplus. Late-game
loss condition: enemy wipes your builders, you have 5000 Ti, core
does nothing.

Replaced with `ct.get_unit_count() >= _MAX_TEAM_UNITS = 40`. Also
updated the `has_income` check to divide by live units instead of
cumulative spawns. Cap of 40 (vs the game's 50) leaves headroom for
turrets + builders to coexist without the cap becoming a bottleneck.

### `gunner/__init__.py` — unfed-reset bug

Pre-existing gunner self-destruct logic:
```python
if fired or rotated: idle = 0
else: idle += 1
if not self._is_fed(ct): idle = 0   # ← the bug
if idle > 10: self_destruct()
```

The last line reset idle to 0 whenever ammo wasn't coming in. The
intent was "don't count waiting-for-ammo as idle", but it meant a
gunner that never gets fed (bad placement, chain never completed,
feeding harvester died) sits at idle=0 forever and never
self-destructs — permanently occupying a unit slot.

Removed the reset, dropped the now-dead `_is_fed` method. Unfed
gunners accumulate idle and self-destruct after 10 turns, same as
any other idle gunner.

### `sentinel/__init__.py` — self-destruct added

Sentinel had no self-destruct logic at all — dead sentinels (no
targets in vision, no ammo) just sat there forever. Added mirror of
the gunner logic: `idle_turns` counter, reset on successful fire,
increment otherwise, `_try_self_destruct` at `_SELF_DESTRUCT_THRESHOLD
= 15` (slightly higher than gunner's 10 — sentinels are more
expensive at 30 Ti / 20% scale and we want to be less eager to
recycle them).

Self-destruct guarded by: at least one ally nearby (so the slot is
actually usable) AND no enemies in vision (so we're not vacating
defense when it's needed).

## Open items

### Bridge reachability through fog

A* still allows bridges to land on unseen tiles (cost 5 + bridge 7
= 12). With unseen=5 this is rarely the cheapest option — seen
alternatives usually win — but on a map with lots of fog behind
walls, A* might commit to a bridge whose destination turns out to
be a wall when revealed. The bot then wastes Ti on the bridge and
gets stuck on it.

Adgato's design treats unseen as IMPASSABLE (`cost = INF`) for
chain planning, forcing exploration to establish reachability
before bridges become available. That's a bigger change — it
requires the exploration gate to be tightened (exploration is
currently a second-to-last fallback, only when Ti > 100). Deferred.

### Cap-pressure-gated self-destruct

Current: turrets self-destruct any time they're idle for N turns.
Better: only recycle when the team is actually near the unit cap
(`get_unit_count() >= 35`), keeping turrets alive through quiet
periods. Minor optimisation — deferred until we see real cap
pressure in replays.

### Exploration + long-chain tuning

User feedback from castle_keep replay: bots extend chains too far,
abandon harvesters, leave extended chains exposed to raids. The
bridge fix helped (chains complete faster, less exposed time), but
the structural "when to extend vs defend vs hand off" question is
unaddressed. Discussion-level, not yet coded.

## Rejected / deferred changes

- **Turret cap per harvester** — considered adding "max 1 turret
  per friendly harvester" to prevent sentinel spam. User pushed
  back: "we don't need max 1 per here". Scrapped.
- **Conveyor-cost bump to 3** — alternative to the bridge-ratio
  fix. Would have touched state_update_map cost assignment with
  broader implications. Used the localized COST_BRIDGE_EXTRA
  approach instead.
