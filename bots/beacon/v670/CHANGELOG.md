# v670 changelog

Forked from `bots/beacon/okbot` (the imported v51 sprint submission).
Goal: beat okbot 5-0 in random-map pool tests.

## v670.0 — initial fork (snapshot of okbot)

Identical code to okbot at fork time.

## v670.1 — gunner micro: shoot through friendly roads, prioritise threatening gunners then bots

`gunner/__init__.py`

- **Rule 1 (firing):** the firing path is "clear" if all friendly
  blockers between us and the enemy are roads or markers (not just
  markers). Engine fires at the first blocker — a friendly road in the
  way takes 10 dmg and dies (it had 4 HP), unblocking the path for
  next turn's shot. Net cost: 1 turn + the road's 1 Ti, in exchange
  for being able to shoot at otherwise-unreachable enemies.
- **Rule 2 (rotation):** prioritise enemy gunners (any in r²≤13 of us
  is a threat that can rotate and shoot us next turn), then enemy
  bots. Other turret types (sentinel, launcher, breach) are not used
  to pick rotation direction.

Reachability of the rotation target uses the same Rule 1 walk: only
friendly roads/markers as bypassable in between.

## v670.2 — bounds/vision guard for ray walk

`gunner/__init__.py`

Added `ct.is_in_vision(cur)` check inside `_ray_walk_via_roads`. The
8-direction sweep in `_try_rotate_to_enemy` was walking off-map from
edge gunners and crashing the engine with "Position is not in vision".
Pre-fix: 3/5 maps lost via early resign. Post-fix: clean runs.

## v670.3 — chain planner routes around enemy transport

`builder/state_update_map.py`

Port of intgrah's commit 98084d87 ("enemy roads should be walkable,
but not buildable"). The original `cost_grid`/`conveyor_cost_grid`
update set cost=1 for ANY transport building (any team), so the
conveyor planner happily routed chains through enemy transport and
then failed at placement (`is_buildable` rejects enemy buildings).

Now: friendly transport stays at cost=1; enemy transport gets cost=1
for movement (still walkable per game rules) but conveyor_cost=INF so
the chain planner routes around.

## v670.4 — strict attack gate + reposition fallback

`builder/task_attack.py`

Replace `should_attack`'s 5-clause heuristic with the precise rule:

- destroy_turns = ceil(building_hp / 2)  (builder DPS = 2)
- enemy_arrival = max(0, Chebyshev(epos, target) - 1)  (heal range = 1 Chebyshev)
- attack iff every visible enemy bot's arrival > destroy_turns
- 1-shot kills always commit

When the gate refuses, the run loop now repositions the bot to a
non-healer-range tile via `_pick_attack_destination(avoid_healers=True)`,
or drops the target entirely. Earlier draft of the rule froze
attackers in place because `state.offense_target = my_pos` was set
unconditionally; fix scopes that reset to the fire branch only.

## v670.5 — drop debug prints, seed module-level shuffles

- `builder/__init__.py` and `builder/state_update.py`: removed
  `print(f"  map={t1 - t0}us")` and friends. They ran every turn for
  every unit and called `ct.get_cpu_time_elapsed()` 5–7 times per turn
  alongside f-string formatting. No code reads them.
- `builder/algorithms/pathfind.py`: replaced `random.shuffle(_DIR8_DELTA)`
  and `random.shuffle(_CONV_NEIGHBORS)` with `random.Random(0).shuffle(...)`.
  These were module-level shuffles using the unseeded global RNG, so
  every fresh process got a different DIR8 expansion order — same map +
  same engine seed gave different game outcomes. Strategy unchanged
  (the order is still an arbitrary permutation), but reproducibility
  restored, which is needed for honest A/B testing.
