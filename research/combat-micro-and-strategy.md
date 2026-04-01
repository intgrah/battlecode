# Combat Micro & Strategy Research

Research for Cambridge Battlecode — applying xsquare's (Ivan Geffner's) MIT
Battlecode techniques and general RTS AI patterns to our game.

---

## 1. xsquare's Combat Micro — The MicroInfo Pattern

Source: `github.com/IvanGeffner` — open-source repos for BC19 through BC26.

### Core Algorithm

For **each of the 9 possible moves** (8 directions + CENTRE), compute a
`MicroInfo` object tracking:

```
min_dist_to_enemy   — closest enemy squared distance from that tile
enemies_in_range    — how many enemies can attack you there
enemies_safe        — enemies in range excluding stunned ones
allies_nearby       — friendly units near that tile
```

Then pick the best tile via a **lexicographic comparator** (priority cascade):

1. **Safety classification** (higher = better)
   - `-1` → impassable
   - `0` (unsafe) → alone with >1 non-stunned enemies in range
   - `1` (risky) → more non-stunned enemies in threat range than allies
   - `2` (safe) → otherwise
2. **Prefer in-range over out-of-range** — if you can attack, be in range
3. **If out of range** — prefer closer to enemy (approach)
4. **Minimize exposure** — fewer non-stunned enemies in attack range
5. **Minimize threat** — fewer enemies in move range
6. **Close distance** — prefer closer (tiebreaker)
7. **Prefer CENTRE** — staying still wins ties

### Key Design: `always_in_range` Flag

When the unit **cannot attack** (cooldown > 0) or is **low HP**, set
`always_in_range = True`. This makes every tile count as "in range,"
effectively **disabling approach** and focusing purely on safety — i.e.,
retreat when you can't fight back.

### Turn Structure (Attack-Move-Attack Kiting)

```
1. Attack (before moving)
2. Micro move (reposition to best tile)
3. Attack (after moving)
```

This is **kiting**: deal damage → reposition to safety → deal damage again.

### Target Selection

Simple but effective:
1. Prioritize game-critical targets (flag carriers, etc.)
2. **Lowest HP** wins — focus fire to get kills
3. Recursively attack again if actions remain

---

## 2. Applying to Cambridge Battlecode

### What's Different

Cambridge Battlecode turrets are **static buildings**, not mobile units. Builders
are the only mobile unit. So "combat micro" splits into two very different problems:

- **Builder micro**: avoiding/exploiting enemy turret coverage zones, approaching
  enemy infrastructure to destroy it, surviving while building
- **Turret placement**: choosing WHERE to build turrets and WHICH direction they
  face, to maximize coverage and denial

### Builder Micro (adapted MicroInfo)

For builder movement decisions, evaluate each of 9 tiles:

```python
@dataclass
class TileThreat:
    enemy_turrets_covering: int    # how many enemy turrets can hit this tile
    enemy_damage_potential: float  # total damage per round from enemy turrets
    friendly_turrets_covering: int # how many of our turrets protect this tile
    dist_to_target: int            # distance to current objective
    is_walkable: bool
```

**Comparator** for builder movement (priority order):
1. Must be walkable
2. Minimize `enemy_damage_potential` — don't walk into kill zones
3. Prefer tiles covered by friendly turrets (safety)
4. Minimize distance to objective
5. Prefer CENTRE (don't move unnecessarily)

### Threat Map / Influence Map

Precompute and maintain incrementally:

```python
# Per-tile arrays (indexed by y * w + x)
enemy_threat: list[float]    # total damage enemy turrets can deal to this tile
friendly_cover: list[float]  # total damage our turrets can deal from this tile
threat_staleness: list[int]  # round last updated
```

**When to recompute**: incrementally update when:
- New turret built/destroyed (add/subtract its attack pattern)
- Turret rotated (remove old pattern, add new)
- Turret ammo state changes (has ammo vs empty)

**Precompute attack patterns**: for each turret type × direction, store the set of
relative offsets that can be attacked. Use `c.get_attackable_tiles()` when the
turret is in vision, or hardcode the patterns from the spec.

```python
# Precomputed: for each (turret_type, direction) → set of (dx, dy) offsets
ATTACK_PATTERNS: dict[tuple[EntityType, Direction], list[tuple[int, int]]]

def update_threat_map(threat: list[float], turret_pos: Position,
                      turret_type: EntityType, direction: Direction,
                      damage: float, sign: float = 1.0) -> None:
    for dx, dy in ATTACK_PATTERNS[(turret_type, direction)]:
        x, y = turret_pos.x + dx, turret_pos.y + dy
        if in_bounds(x, y):
            threat[y * w + x] += sign * damage
```

### Ammo Awareness

Turrets without ammo can't shoot. Track:
- Whether a turret has ammo (visible when in vision range)
- Whether a turret's ammo supply chain is connected (flow graph analysis)
- Turrets with no supply chain are "dead" — safe to approach

---

## 3. Macro Strategy

### The Fundamental Tension

Economy vs. military is a **continuous tradeoff**, not a binary choice.
xsquare's key insight: **simple strategies that approximate global coordination
via independent local behavior** beat complex coordination schemes.

Key finding from postmortems:
- **Micro improvements yield 30-50% win rate gains** (Gone Fishin', BC2023)
- **Macro improvements yield ~5% gains**
- But macro is the prerequisite — you need resources to build the military that
  benefits from micro
- "Almost all efforts focused on economy and expansion. Teams would lose despite
  having loads of money." (Om Nom, BC2025) — must convert resources to pressure

### Economy-First with Reactive Military

BC2021 insight: "The first slanderers have the most profound effect on economy."
Translated: **your first harvesters are disproportionately valuable** due to
cost scaling. A harvester built at 1.0x scale costs 80 Ti; at 2.0x it costs 160 Ti.

Win condition tiebreakers favor refined axionite > titanium > harvesters alive.
**Economy wins ties.** So the default stance should be economy-first, with
military triggered reactively by threat detection.

### Piecewise Linear Model for Builder Role Allocation

Your instinct about piecewise linear models is correct. The idea:

```python
def builder_allocation(state: State) -> dict[Task, float]:
    """Return target fraction of builders for each role."""
    round = state.age
    n_builders = count_builders(state)
    n_harvesters = len(state.my_harvesters)
    threat_level = compute_threat_level(state)  # 0.0 to 1.0

    # Piecewise linear: early game → econ, mid game → balanced, late → military
    if round < 50:
        econ_frac = 0.8
        military_frac = 0.1
        scout_frac = 0.1
    elif round < 200:
        # Linear interpolation
        t = (round - 50) / 150
        econ_frac = lerp(0.8, 0.4, t)
        military_frac = lerp(0.1, 0.4, t)
        scout_frac = lerp(0.1, 0.2, t)
    else:
        econ_frac = 0.3
        military_frac = 0.5
        scout_frac = 0.2

    # Reactive adjustment: if under attack, shift to military
    econ_frac *= (1.0 - 0.5 * threat_level)
    military_frac += 0.5 * threat_level * econ_frac

    return {Task.HARVEST: econ_frac, Task.COMBAT: military_frac, Task.SCOUT: scout_frac}
```

### Better Approach: Utility-Based Scoring (what you have, but improved)

Instead of fixed priority scores, compute **dynamic scores** based on game state:

```python
def _policy(state: State) -> list[tuple[float, Task]]:
    scores = []

    # HEAL_CORE: proportional to damage taken
    core_damage = GameConstants.CORE_MAX_HP - state.my_core_hp
    scores.append((core_damage * 10.0, Task.HEAL_CORE))

    # HARVEST_TI: diminishing returns based on existing harvesters
    ti_need = max(0, 4 - len(state.my_harvesters))  # want ~4 harvesters
    scores.append((ti_need * 40.0, Task.HARVEST_TI))

    # CONNECT_EXCESS: high when resources are stranded
    excess_score = sum(state.flow.excess) * 2.0
    scores.append((excess_score, Task.CONNECT_EXCESS_TI))

    # PLACE_SENTINEL: proportional to exposed area
    exposed = compute_undefended_area(state)
    scores.append((exposed * 0.5, Task.PLACE_SENTINEL))

    # PATROL: scales with staleness of map info
    scores.append((state.infra_max_staleness * 0.3, Task.PATROL))

    # EXPLORE: high early, diminishes
    unseen_frac = count_unseen(state) / (state.w * state.h)
    scores.append((unseen_frac * 100.0, Task.EXPLORE))

    scores.sort(key=lambda t: t[0], reverse=True)
    return scores
```

### Proportional Balance via Marker-Based Census

Since units can't share memory, use **markers for census**:

```python
# Each builder places a marker encoding its current task
# Other builders read nearby markers to estimate task distribution
# A builder picks the task with the LARGEST gap between
# desired_fraction and actual_fraction

def pick_task(desired: dict[Task, float], observed: dict[Task, int]) -> Task:
    total = sum(observed.values()) or 1
    max_gap = -inf
    best_task = Task.EXPLORE
    for task, target_frac in desired.items():
        actual_frac = observed.get(task, 0) / total
        gap = target_frac - actual_frac
        if gap > max_gap:
            max_gap = gap
            best_task = task
    return best_task
```

---

## 4. Livelock Prevention

Livelock occurs when units oscillate between states without making progress.
Common causes and solutions:

### Cause 1: Target Switching (xsquare's bugnav example)

A builder navigating to the nearest ore deposit switches targets as it gets
close to a different deposit, looping forever.

**Fix**: only switch from target T to T' if `dist(R, T') < historical_min_dist(R, T)`
since R started pursuing T, not just `dist(R, T') < dist(R, T)`.

### Cause 2: Build-Destroy Cycles

Two builders each destroying what the other just built.

**Fix**: marker-based task claims. Before committing to a build location, place
a marker claiming it. Other builders read claims and avoid duplicating work.
(You already have `MarkerTaskClaim` — good.)

### Cause 3: Patrol Oscillation

A patrolling builder keeps returning to the same area.

**Fix**: track visited tiles with timestamps. Patrol targets should be
**least recently visited** tiles, not just nearest.

### Cause 4: Move-Countermove

Two builders blocking each other in narrow corridors.

**Fix**: priority by spawn order (older units have right-of-way), or use the
unit ID as tiebreaker. Lower ID yields to higher ID.

### Cause 5: Pathfinding Edge-Following

Builder follows map edge forever due to BugNav.

**Fix** (Gone Fishin', BC2023): hard-code rules against following map edges;
treat friendly units as soft obstacles (path around them differently than walls).

### Solutions from BC Postmortems

| Strategy              | Description                                               | Source                  |
| --------------------- | --------------------------------------------------------- | ----------------------- |
| Timeouts              | Block retrying same action/destination for N turns        | 4 Musketeers, BC2023   |
| Random jitter         | Add random perturbation to break symmetry                 | Gone Fishin', BC2023   |
| Prohibit edge-follow  | Hard-code rules against following map edges               | Gone Fishin', BC2023   |
| Priority by ID        | Higher-ID bots yield to lower-ID bots                     | General technique       |
| Soft obstacle allies  | Path around allies differently than walls                 | Gone Fishin', BC2023   |
| Hybrid BFS + BugNav   | Use global BFS when available, fall back to BugNav locally| 1st place BC2014       |

### General Anti-Livelock Pattern: Hysteresis

Don't switch states on exact thresholds — use **hysteresis bands**:

```python
# BAD: oscillates around threshold
if enemy_nearby:
    state = RETREAT
else:
    state = ADVANCE

# GOOD: hysteresis
if state == ADVANCE and threat > HIGH_THRESHOLD:
    state = RETREAT
elif state == RETREAT and threat < LOW_THRESHOLD:
    state = ADVANCE
```

### Commitment Timer

Once a task is chosen, commit to it for a minimum number of rounds before
re-evaluating. This dampens oscillation:

```python
if self.task_commitment > 0:
    self.task_commitment -= 1
    return self.current_task  # don't re-evaluate
# ... re-evaluate task
self.task_commitment = 5  # commit for 5 rounds
```

---

## 5. Move-Action vs Action-Move

This is **the** critical micro decision for builders. The choice depends on
the current situation:

### Action-Move (build/heal first, then move)

Use when:
- **Building in a safe area** — no threat, just build and walk away
- **Healing** — heal the target first, then reposition
- **The build location is your current position** — must act before leaving

### Move-Action (move first, then build/heal)

Use when:
- **Building at a destination** — move to the target tile, then build
- **Retreating from danger** — move to safety first, then act if possible
- **The build location is adjacent** — move into range, then build

### Optimal Pattern: Context-Dependent

```python
def execute_turn(ct, move, action, threat_level):
    if action is not None and can_act_here(ct, action):
        # Action-move: we can act from current position
        if threat_level > THREAT_THRESHOLD:
            # Under threat: act first (might die before next turn)
            execute_action(ct, action)
            if move != Direction.CENTRE and ct.can_move(move):
                ct.move(move)
        else:
            # Safe: move first if we need to reach somewhere
            if move != Direction.CENTRE and ct.can_move(move):
                ct.move(move)
            execute_action(ct, action)
    else:
        # Move-action: need to move to reach action target
        if move != Direction.CENTRE and ct.can_move(move):
            ct.move(move)
        if action is not None:
            execute_action(ct, action)
```

### The "Always Kite Back" Rule

Gone Fishin' (BC2023 top team): "We tried to evaluate the skirmish to only kite
back in certain scenarios but eventually realized that ALWAYS kiting back after an
attack is better." This is counterintuitive but robust — simplicity beats cleverness.

### Move-Action Decision Table (from BC postmortems + MIT OCW)

| Situation                  | Order              | Rationale                                        |
| -------------------------- | ------------------ | ------------------------------------------------ |
| Already in attack range    | **Attack → Move**  | Free hit; opponent may not retaliate before you leave |
| Out of attack range        | **Move → Attack**  | Close gap, deal damage before they retreat        |
| Retreating while in range  | **Attack → Move**  | Deal parting damage while disengaging             |
| Retreating, out of range   | **Move only**      | Preserve health                                   |

MIT OCW (2013): "It's the one who closes the gap first that wins the engagement."

### xsquare's Pattern: Attack-Move-Attack

In Cambridge Battlecode, builders can attack buildings on their own tile (2 dmg
for 2 Ti). The analogous pattern:

```
1. If on enemy building: attack it
2. Move (toward target or away from danger)
3. If on enemy building: attack it again
```

For turrets, the game handles move-action automatically since turrets don't move.
The key insight: **turrets should fire as soon as possible** (before other units
move), so spawn order matters for turrets that need to hit moving builders.

---

## 6. Efficient Game State Tracking

### What to Track (per-tile arrays, indexed by `y * w + x`)

```python
# Environment (static after first observation)
env: list[Environment | None]          # terrain type

# Buildings (update on vision)
building: list[Building | None]        # what's built here
building_team: list[Team | None]       # who owns it

# Threat (recompute incrementally)
enemy_damage: list[float]              # total enemy DPS on this tile
friendly_damage: list[float]           # total friendly DPS on this tile
threat_net: list[float]                # enemy_damage - friendly_damage

# Staleness (for fog-of-war reasoning)
last_seen: list[int]                   # round number last observed

# Navigation
cost: list[int]                        # movement cost (walkable/impassable/unseen)
```

### Turret Coverage Map — Incremental Maintenance

Don't recompute from scratch. Maintain incrementally:

```python
def on_turret_added(pos, turret_type, direction, team, damage):
    """Called when we see a new turret."""
    threat = enemy_damage if team != my_team else friendly_damage
    for dx, dy in ATTACK_PATTERNS[(turret_type, direction)]:
        x, y = pos.x + dx, pos.y + dy
        if in_bounds(x, y):
            threat[y * w + x] += damage

def on_turret_removed(pos, turret_type, direction, team, damage):
    """Called when a turret is destroyed."""
    threat = enemy_damage if team != my_team else friendly_damage
    for dx, dy in ATTACK_PATTERNS[(turret_type, direction)]:
        x, y = pos.x + dx, pos.y + dy
        if in_bounds(x, y):
            threat[y * w + x] -= damage
```

### Budget-Conscious Update Strategy

With 2ms CPU budget, you can't scan the whole map every turn.

1. **Vision scan**: only update tiles in current vision radius (~π×20 ≈ 63 tiles
   for builders). This is your primary update.
2. **Incremental flow**: only recompute flow graph when buildings change
3. **Lazy threat map**: recompute threat for a tile only when a builder needs to
   evaluate it for movement (compute on demand, cache with staleness)
4. **Amortize exploration**: spread map updates across multiple rounds using
   spare CPU time (xsquare's endTurn pattern)

### What NOT to Track

- Don't track every enemy builder position in state — they move every turn and
  you only see them transiently. Use ephemeral per-turn data for this.
- Don't maintain a full pathfinding graph that updates every turn — use your
  existing BFS/A* with lazy invalidation.

---

## 7. Concrete Recommendations for v51

### Priority 1: Threat Map

Add `enemy_threat` and `friendly_cover` arrays to `State`. Update incrementally
when turrets are spotted/destroyed. Use this in builder movement decisions to
avoid walking into kill zones.

### Priority 2: Dynamic Policy Scoring

Replace the hardcoded `_policy()` scores with state-dependent formulas.
Key inputs: round number, harvester count, core HP, turret count, threat level.

### Priority 3: Builder Micro

When a builder is in or near enemy turret range, switch from task-based movement
to micro-based movement using the MicroInfo pattern. Evaluate 9 tiles, pick the
safest one that still makes progress toward the objective.

### Priority 4: Turret Placement Strategy

Use the threat map to find **gaps in coverage**. Place sentinels to cover:
- Ore deposits (deny enemy harvesting)
- Approach paths to core (defense)
- Chokepoints identified by pathfinding

### Priority 5: Anti-Livelock

Add hysteresis to task switching and commitment timers. Track historical minimum
distances for pathfinding targets to prevent oscillation.

### Priority 6: Census via Markers

Encode current task in builder markers. Read nearby markers to estimate
task distribution and pick under-represented tasks.

---

## 8. Influence Map Architecture (from Game AI Pro 2)

For more sophisticated state tracking beyond simple threat arrays:

- **Grid representation**: overlay matching the map grid
- **Propagation**: each enemy unit radiates threat outward with exponential decay
- **Double buffering**: calculate new values into a buffer to prevent
  order-dependent artifacts
- **Momentum parameter**: high momentum (→1.0) biases toward historical values
  (strategic); low momentum (→0.0) tracks current state (tactical)
- **Layers**: combine multiple maps — proximity, threat, terrain, resources
- **Update frequency**: strategic maps every ~20 rounds; tactical maps every
  ~5 rounds

For Cambridge Battlecode, the simpler incremental turret coverage arrays
(section 6) are likely sufficient given the 2ms budget. Reserve full influence
maps for if/when you need multi-layer strategic reasoning.

---

## Sources

- [xsquare's Guide to Battlecode (PDF)](https://battlecode.org/assets/files/battlecode-guide-xsquare.pdf)
- [IvanGeffner GitHub](https://github.com/IvanGeffner) — BC19 through BC26
- [BTC24 source](https://github.com/IvanGeffner/BTC24) — MicroInfo pattern
- [BC25 source](https://github.com/IvanGeffner/BC25) — tower-focused micro
- [Gone Fishin' BC2023 Postmortem](https://battlecode.org/assets/files/postmortem-2023-gone-fishin.pdf)
- [4 Musketeers BC2023 Postmortem](https://battlecode.org/assets/files/postmortem-2023-4-musketeers.pdf)
- [Cout for Clout BC2024 Postmortem](https://battlecode.org/assets/files/postmortem-2024-cout-for-clout.pdf)
- [The Kragle BC2025 Postmortem](https://battlecode.org/assets/files/postmortem-2025-the-kragle.pdf)
- [Om Nom BC2025 Postmortem](https://battlecode.org/assets/files/postmortem-2025-om-nom.pdf)
- [MIT OCW BC2013 Lecture](https://ocw.mit.edu/courses/6-370-the-battlecode-programming-competition-january-iap-2013/)
- [Kiting in RTS Using Influence Maps (AAAI)](https://cdn.aaai.org/ojs/12544/12544-52-16064-1-2-20201228.pdf)
- [Modular Tactical Influence Maps — Game AI Pro 2](https://www.gameaipro.com/GameAIPro2/GameAIPro2_Chapter30_Modular_Tactical_Influence_Maps.pdf)
- [Cambridge Battlecode Docs](https://docs.battlecode.cam)
