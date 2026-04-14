# v54 TODO — Micro and Pathfinding Improvements

Reference list from the session. Items are grouped by system; check as you go.

## Current state (2026-04-11)

- **`move_search` = MoveHeapAstar** (heap-based A*, chebyshev heuristic,
  8 neighbours, reads padded `cost_grid`). **Known-good on the real
  server — went 5-0 on the 5-large-map test.**
- `conv_search` = bucket `AStarSearch` with padded grid + 20 bridges
  + relaxation on. Working.
- **NavBfs / PassableGrid** (adgato port) exists at
  `builder/algorithms/nav_bfs.py` but is **not wired up** — it's
  dead code while we fall back to MoveHeapAstar.
- State still instantiates `state.pass_grid` and `state.nav` in
  `State.__init__`, and `state_update_map.py` feeds the pass_grid
  in both branches of the vision update. Small ongoing cost, but
  doesn't affect pathfinding while `move_search = MoveHeapAstar()`.

## Healing micro

- [ ] **Match healers to attackers 1:2.** Heal does 4 HP/turn, attacker
      fire does 2 HP/turn, so one healer counters two attackers. Current
      `_deconflict_rank` only tracks who's closest — doesn't scale the
      number of committed healers with the number of visible attackers.
      On a 3-attacker tile, we need ≥2 healers committed, not just 1.

## Attack micro

- [ ] **Allow 2 gunners per enemy harvester** (was capped at 1). Keep
      sentinel cap at 1.
- [ ] **Gunner placement: any conveyor in LoS** — not just diagonals.
      The constraint is "don't face into the harvester", but any
      direction (including cardinal) that clears an enemy conveyor
      along its ray is valid. Current `_gunner_chain_facing` only
      checks 4 diagonals.
- [ ] **Attack roads near ore that's adjacent to enemies.** Take
      control of ore BEFORE the enemy places a harvester on it. Drop
      gunners / sentinels there so when they do place one, we already
      have turret cover.
- [ ] **Chain interception during enemy build-up.** When enemy chains
      are partially built (tiles open / unfinished), target those
      open-end tiles. Easier to disrupt before they're a closed loop.
- [ ] **Target conveyors feeding enemy core.** Drop gunners in LoS of
      them for sustained damage even after we move on.
- [ ] **Avoid enemy gunner firing lines in `_pick_attack_destination`.**
      Currently filters by `is_passable` + healer proximity — doesn't
      check if the tile is in an enemy gunner/sentinel attack pattern.
      Use the `_turret_blocked_tiles` pattern from nav_bfs.py.
- [ ] **Prioritise low-HP targets the bot can kill in ≤10 rounds.**
      Builder fire = 2 dmg/turn. Road = 5 HP (3 shots), conveyor = 20 HP
      (10 shots). Prefer tiles we can actually finish before enemies
      converge.
- [ ] **"Don't die" guard.** Before committing to attack a tile, check:
      visible attackers ≥ my HP bucket → retreat. Heals already run
      first in OFFENSE_TASKS but there's no "cancel current attack if
      doomed" inside `run_attack`.
- [x] **~~Remove barrier placement near enemy harvester.~~** Done —
      deleted the `else: try_place(BARRIER)` branch. Bot now just
      drops the attempted gunner/sentinel and moves on.

## Movement pathfinding

- [x] **MoveHeapAstar (heap-based A*).** Current default. Server 5-0
      validated.
- [x] `_turret_blocked_tiles` helper (gunner/sentinel ray avoidance) —
      exists in pathfind.py but is only called from the dead NavBfs
      class. Not used by MoveHeapAstar.

### Gunner/sentinel avoidance in MoveHeapAstar (deferred)

- [ ] **Soft-penalise enemy gunner firing-line tiles in `cost_grid`.**
      Add a new `state.adjacent_to_enemy_gunner_ray: set[Position]`
      set maintained in `state_update_map.py`, analogous to
      `state.adjacent_to_enemy_launcher`. In
      `update_splittable_locations`, bump `cost_grid[i] += 15` for
      tiles in the set. MoveHeapAstar picks these up for free via
      its existing cost_grid read path. This gives "route around
      gunners" without changing the pathfinder at all.

### NavBfs (adgato port) — WON'T-DO short-term

- [x] Initial port exists at `builder/algorithms/nav_bfs.py`
      (PassableGrid + NavBfs, close to adgato/mesh).
- [ ] **Fix the per-bot pnb init cost.** The blocker for actually
      using NavBfs: `PassableGrid.init_pnb_chunk` does ~2500 tiles ×
      2 list allocations = ~5-10ms on CPython per Builder instance.
      First 5-6 turns of each bot's life return None from `search`
      because `grid.ready` is False → bot can't pathfind → enemy
      gets a free opening. The fix is to **make PassableGrid
      module-level** (one per game, shared across all Builder
      instances) and have per-bot NavBfs register as `grid.navs`.
      Adgato/mesh does this implicitly — when you look at builder.py
      it creates one grid per bot but the bot count there is small
      and the init cost is amortised differently. For v54 with
      12+ builders we need explicit sharing.
- [ ] **Only after sharing works**: re-test BFS on server. If still
      slower than MoveHeapAstar, drop the whole port.
- [ ] **Only after sharing works**: port adgato's `tile_codec` diff
      cache so `state_update_map.py` skips unchanged tiles. Separate
      optimisation from the BFS port itself.

## Measurement

- [x] Confirmed `move_search = MoveHeapAstar` wins 5-0 on real server.
      All BFS variants attempted so far (including adgato-exact port
      at 1-4) were worse because of the per-bot pnb init-cost problem.
- [ ] Re-sweep on hetzner + submit a server match test after each
      TODO item lands.
