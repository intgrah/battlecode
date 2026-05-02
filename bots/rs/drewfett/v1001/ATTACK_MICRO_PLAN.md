# Attack micro plan — drewfett v1000

Brief plan for the attack-micro discussion (drewfett ↔ intgrah). Use this as context after compaction; flesh out before implementing.

## Current state of v1000 attack

- **Harassment** (`offense/parasitic/`): chew enemy conveyors, approach harvesters, walk to cached target.
- **Pushing** (`offense/push/`): extend chain toward enemy core, place sentinels on dangling tips, split before sentinel.
- **Convergence** (`converge_on_rendezvous`): WS-4 rendezvous markers — when one bot spots a high-value enemy harvester it places a `RendezvousAttack` marker; nearby bots converge.
- **Turrets vs harvesters** (`turret_around_harvester`): place gunner / sentinel cardinal to a vulnerable enemy harvester.
- **Defensive turret-clearing** (`clear_enemy_turret`): place sentinel on dangling tip targeting enemy launcher in our half.

What we DON'T do:
- Predictive defense disruption (proactive launcher placement)
- Sentinel drill (own harvester near enemy + sentinel coverage)
- Anti-clumping / proximity gate
- Heal-path blocking
- Throw enemies away from their core systematically

## Tier 1 — quick wins (do first)

### A. Diagonal launcher flank
**Problem**: most teams' reactive defense only triggers on a builder cardinally adjacent to a friendly harvester. A diagonally-adjacent threat slips past.

**Layout**: for an enemy harvester at `H`, target a tile `D` that is:
- diagonally adjacent to `H` (dist² == 2)
- NOT cardinally adjacent to any other friendly harvester
- empty / road / marker

Place a launcher at `D` facing the harvester+conveyor cone. Throw arriving enemy bots away.

**Implementation sketch**:
- new task `tasks/offense/diagonal_launcher_flank.rs`
- gate: standing on a diagonal-of-enemy-harvester tile + can afford launcher (20 Ti scaled)
- helper: `pick_flank_tile(builder, target) -> Option<Position>` scanning DIR8 from `H`, filtering diagonals only, checking buildable + non-friendly-harvester-adjacent
- `try_place(EntityType::Launcher, flank_pos, BuildExtra::None)` (launchers don't take direction)
- ~150 LOC

**Risk**: enemy may react to launcher specifically (some teams flag launchers as threats). Mitigated by the diagonal placement still being one step removed.

### B. Proximity gate
**Problem**: 3 bots can dogpile a single harvester while another sits unattacked.

**Implementation**: helper `am_closest_to(self_, target) -> bool`:
- iterate `friendly_bots` (state.friendly_bots set)
- check Chebyshev dist; return true iff no friendly is strictly closer
- gate `approach_harvester`, `chew_conveyor`, `turret_around_harvester` with this check
- ~20 LOC

**Risk**: in mid-fight chaos, "closest" may flip turn-to-turn causing oscillation. Mitigate by adding hysteresis (only switch if other bot is N tiles closer).

## Tier 2 — medium effort

### D. Buddy / converge attacks (extend rendezvous)
**Already have rendezvous markers (WS-4).** Extensions:
- Score "high-value enemy harvester" = visible enemy conveyor count touching it × flow-history depth × (not currently ringed by friendlies). Drop rendezvous marker only on top-1 score.
- Anti-clumping: combine with proximity gate (B); rendezvous marker target gets a "claimer" — the closest bot — and others wait at distance.
- ~80 LOC on top of existing markers.

### C. Sentinel drill
**Idea**: build our own harvester at an ore tile near enemy's chain, sentinel coverage at max-range-1.

**Hard parts**:
- **Ore selection**: weight enemy-half ore tiles by proximity to enemy infra (visible enemy conveyor density nearby), with anti-suicide guard (must be reachable from our chain).
- **Sentinel placement**: max-range-1 from enemy harvester, facing enemy harvester output direction (where the conveyor outflow goes).
- Need protective ring around the harvester so enemy can't immediately destroy it.

**Implementation sketch**:
- extend `pick_offensive_ti_ore_target` with proximity-to-enemy-infra scoring (already partially done in WS-8)
- new task `tasks/offense/push/sentinel_drill.rs`
- ~300 LOC

## Tier 3 — bold / experimental

### E. Counter-launcher ring
**Idea**: place launchers in a ring around enemy core, throwing their bots outward. Cuts econ + spawns.

**Cost**: ~6 launchers × 20 Ti scaled = 120+ Ti, plus ammo conveyors. Heavy commitment.

**When to try**: only after Tier 1+2 land successfully and we have the resource margin to commit.

### F. Heal-path blocking (SE-style)
**Idea**: predict enemy heal paths, place launchers to throw the medic.

**Hard**: need to model enemy bot intent. Probably not worth without real opponent modeling.

## Conventions / shared

- Use existing markers infrastructure (`Marker::RendezvousAttack`, `EnemyThreat`).
- Re-use `vulnerable_harvesters` helper. (Cache it per turn — pending optimization #1 from earlier.)
- Re-use BFS nav. Road tiebreak (in flight) helps these tasks reuse infra.

## Recommended sequencing

1. **A + B together** as one workstream. Sweep n=208. Land if neutral or +.
2. **D** on top of A+B. Sweep again.
3. Decide between **C** (sentinel drill) and **E** (counter-launcher ring) based on observed gaps.
4. Defer **F**.

## Notes from the discussion

- Pantheon's stalking has holes — they only commit when enemy is closer to their core than their bot. Predictable.
- SE has strong attack micro — they place sentinels (and seem to react to barriers). Aim for parity first.
- Most teams: `C C / C H C C C C / C C` placement. Diagonal flank `L C / C H C C C C / L C` slips past since each `L` is technically not cardinal to `H`.
- Spam launchers on opponent side + careful spacing (≥2 tiles apart) creates inverse-troll-bot.
- "Do not pursue if not closest" rule + "spread attackers" hits 80% of attack-micro value cheaply.

## Out of scope (explicit)

- Neural opponent classifier — pattern-matching is enough for v1000.
- MCTS / search — turn budget too tight.
- Cross-team comms — markers are the only channel and team-private.
