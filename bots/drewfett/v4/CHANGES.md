# drewfett/v1 — Changes from intgrah/v50

Forked from intgrah/v50. All changes below are relative to that base.

## New features

### Dynamic core spawning (`core/__init__.py`)
Replaced v50's hard cap of 3 builders with reserve-based spawning.
- Emergency spawn bypasses reserve when enemy bots detected near core
- Reserve scales with alive builders: `harvester_cost + conveyor_cost * 5`
- Cap at 5 builders

### Danger zone pathfinding (`builder/state.py`, `builder/state_update.py`, `navigation/astar_bucket.py`, `util.py`, `config.py`)
Builders avoid enemy turret fire when walking.
- Switched default NAV from BFS to ASTAR_BUCKET_PYTHON (BFS can't handle weighted edges)
- Bucket A* adds `COST_DANGER = 5` penalty for tiles in danger zones
- Danger zones derived from incremental threat maps (see below)

### Incremental threat maps (`attack_patterns.py`, `builder/state.py`, `builder/state_update.py`)
Ref-counted per-tile threat arrays updated when turrets appear/disappear/rotate.
- `en_gunner`, `en_sentinel`, `en_breach`, `en_launcher` — enemy turret coverage per type
- `my_threat` — our own turret coverage
- `attack_patterns.py` — precomputed offset tables per turret type and direction
- Handles turret rotations (direction change triggers -1/+1 update)
- `danger_zones` set derived from threat arrays for pathfinding

### Reactive defense task (`builder/task_defend.py` — NEW)
Detects enemy turrets near friendly infrastructure and places counter-gunners.
- Validates ammo from adjacent harvester or splitter
- Claim deconfliction via `TaskKind.DEFEND` marker

### Proactive defense task (`builder/task_defend_core.py` — NEW)
Places sentinels to defend infrastructure using approach flow analysis.
- Multi-source BFS from candidate enemy core positions (symmetry-aware)
- BFS from our core for detour filtering
- Approach flow: propagate downstream with detour budget, per-layer normalized
- Coverage tracking: existing sentinel arcs prevent overlap
- Diminishing returns: score / (existing_sentinels + 1)
- Flow-preserving splitter conversion for ammo routing
- Supports harvester as direct ammo source (no splitter needed)

### Gunner fire control (`gunner/__init__.py` — NEW, `main.py`)
- Priority targeting: turrets(4) > transport/harvesters(3) > bots(2) > core(1)
- Rotation toward targets when idle (only with ammo)

### Enemy core inference (`builder/state_update.py`)
- Infers enemy core position from symmetry (ROT default if unresolved)
- Updates when symmetry resolves or enemy core directly seen
- Checks if multiple symmetry candidates agree on same position
- Eliminates symmetries whose mirrored core overlaps own core

### Dynamic exploration (`builder/__init__.py`)
- Explore score scales with map visibility: 95 (<30%), 55 (<50%), 20 (>50%)
- Beats DEFEND_CORE priority early game to ensure map coverage

### Flow model improvements
- `accepts_input_from` now checks turret facing direction (turrets reject ammo from facing side)
- Transport edge-building checks `accepts_input_from` for targets (was missing for transport→turret)
- `_destroy_any_friendly` helper for splitter conversion (destroys conveyors, not just roads)
- `step_off_and_build` helper for impassable building placement

### Updated task policy (`builder/__init__.py`)

| Priority | Task | Condition |
|----------|------|-----------|
| 999 | HEAL_CORE | Core HP < max |
| 180 | DEFEND | Enemy turret near our infra |
| 150 | CONNECT_EXCESS_TI | Flow excess detected |
| 100 | HARVEST_TI | Unharvested Ti ore known |
| 95/55/20 | EXPLORE | <30% / <50% / >50% map seen |
| 90 | DEFEND_CORE | Can afford sentinel |
| 40 | PLACE_SENTINEL | Enemy Ti harvesters visible |
| 25/15 | PATROL | Staleness > 50 / else |
| 10 | HEAL_TURRET | Damaged friendly turret |

### Debug visualiser (`builder/state_dump.py`)
Rewrote for `visualiser.emit()`. Overlay layers: flow_ti, flow_ax, flow_excess, enemy_dist, approach_flow, coverage (my_coverage), en_threat, danger, unseen, staleness. Scalars: scale, sentinels, my_core, en_core_pos, symmetry.

## Bug fixes

### Patrol walkable() crash (inherited from v50)
`task_patrol.py`: `state.walkable(i)` called with flat index instead of `(x, y)`.

### Road/marker blocking step_off_source (`task_connect_excess.py`)
`_step_off_source` didn't whitelist `BuildingRoad` or `BuildingMarker` at conveyor output tile, causing disconnected conveyor placement.

### FIX_EXCESS claims blocking own chain continuation (`builder/helpers.py`)
Excess tile shifts as conveyors are built. FIX_EXCESS claims now ignored entirely.

### Build+move ordering in _execute (`builder/__init__.py`)
Non-road builds now execute before move (build while adjacent, then step).

### Build on own tile (`task_connect_excess.py`)
Builders can build on their own tile. Removed unnecessary step-off logic.

### _move_toward_next direction fix (`task_connect_excess.py`)
Was stepping onto the built tile instead of toward next un-built tile.

### _destroy_friendly missing can_destroy check (`builder/helpers.py`)
Added `can_destroy` guard to prevent GameError when out of range.

### PlaceGunner missing from execute (`builder/helpers.py`)
Added PlaceGunner case to `execute()`.

### Gunner get_stored_resource error (`gunner/__init__.py`)
Wrapped in try/except — gunners don't have storage, API throws.

## Files added
- `attack_patterns.py` — precomputed turret attack offsets
- `gunner/__init__.py` — gunner fire control
- `builder/task_defend.py` — reactive gunner defense
- `builder/task_defend_core.py` — proactive sentinel defense
- `visualiser.py` — copied from v50 root
- `CHANGES.md`, `TODO.md`, `STRATEGY.md`

## Files modified
- `main.py` — Gunner dispatch
- `config.py` — NAV → ASTAR_BUCKET_PYTHON
- `util.py` — COST_DANGER, DIAL_MOD
- `core/__init__.py` — dynamic spawning
- `builder/__init__.py` — policy, DEFEND/DEFEND_CORE wiring, execute ordering
- `builder/task.py` — DEFEND, DEFEND_CORE enums
- `builder/state.py` — danger_zones, en_core_pos, threat arrays, approach_flow, our_dist, enemy_dist
- `builder/state_update.py` — threat map maintenance, symmetry inference, wall invalidation
- `builder/state_update_econ.py` — transport→turret accepts_input_from check
- `builder/state_helpers.py` — turret facing in accepts_input_from
- `builder/state_dump.py` — visualiser overlays
- `builder/task_patrol.py` — walkable() fix
- `builder/task_connect_excess.py` — road whitelist, claim fix, build+move, nav simplification
- `builder/helpers.py` — PlaceGunner, can_destroy, _destroy_any_friendly, step_off_and_build
- `navigation/__init__.py` — pass danger_zones
- `navigation/astar_bucket.py` — danger cost penalty
- `marker/__init__.py` — TaskKind.DEFEND
