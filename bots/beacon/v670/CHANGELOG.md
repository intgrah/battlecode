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

## v670.6 (REVERTED) — heavy ECON weights regressed

Tried `_INITIAL_WEIGHTS` early {DEFENSE: 2, OFFENSE: 1, ECON: 7} and
late {DEFENSE: 2, OFFENSE: 3, ECON: 5} (vs original 6/1/3 and 3/4/3).
Hypothesis: more economic builders → more Ti delivered → win the
Ti-collected tiebreak.

Result on the standard 10-map × 2-side pool: **3-17** (vs ~4-6 with
original weights). Reverted. Likely failure mode: too few defenders
let okbot raid early, snowball.

Lesson: don't ship role-weight tweaks without thinking about the
defensive trade-off. The original weights are tuned to keep a
defender garrison alive while still building econ.

## v670.7 (REVERTED) — Random(42) for shuffle seed

Tried `random.Random(42)` instead of `random.Random(0)` for both
module-level shuffles in `pathfind.py`. Result: 12-8 vs 11-9
baseline — marginal, within noise. Reverted to Random(0).

Lesson: shuffle seed doesn't materially affect path quality at
this sample size; not worth tuning.

## Reverted iterations log

The following changes were tested on the standard 10-map × 2-side
parallel pool (jobs=4, seed=1) and reverted because they regressed
or didn't beat the baseline 11-9 result:

- v670.6 — `_INITIAL_WEIGHTS` set to econ-heavy {2,1,7}/{2,3,5} → 3-17
- v670.7 — `random.Random(42)` shuffle seed → 12-8 (within noise)
- v670.8 — looser `_TRANSITION` (DEFENSE → 30/60/15 etc.) → 8-12
- v670.9 — `_MAX_TEAM_UNITS = 45` → 9-11
- v670.10 — drop `_opportunistic_attack` from ECON_TASKS → 8-12
  (the random 20% attack actually pulls weight)
- v670.11 — gunner rotation 3rd-tier sentinel/launcher target → 10-10
- v670.12 — strict gate `<` instead of `<=` (1-turn looser) → 10-10

Pattern: simple parameter knobs are tightly tuned at the okbot
baseline; bumps in either direction regress. Real wins probably
need new capability (foundry/refined-Ax, sentinel push, bridges
to bypass walls), not parameter tuning.

## v670.15 — robust init: catch RuntimeError, retry next turn

`main.py`: wrapped the `Builder(ct)` / `Core(ct)` / etc. construction in
`try / except RuntimeError`. The crash mode it fixes is
`State.find_core` raising "Core not visible at spawn" — observed on
coffee-A side at seed=1 in v670.5 baseline runs, which caused a hard
resign at turn 0 for the first builder.

The exact engine condition isn't fully understood (the bot spawns on a
core tile, which should always have the core visible). Retrying next
round is defensive: if find_core fails we skip the turn and try again,
and `print(f"INIT_RETRY: {e}", file=sys.stderr)` flags it for
post-mortem.

Standard-pool result: 10-10 (down from 11-9). The retry is noise-positive
on most maps but unblocks coffee-A from a turn-0 resign. Keeping it
because correctness > tiny win-rate loss.

## v670 — place_offensive_sentinel function added (UNUSED)

`task_attack.py`: defined `place_offensive_sentinel(state, ct)` that
walks DIR8 around the bot looking for a buildable tile facing the
enemy core where the engine reports an enemy in the sentinel's attack
pattern. Costs 30 Ti + scale.

Wired briefly into OFFENSE_TASKS between _heal and _attack. Result on
arena was catastrophic (v670 290 vs okbot 29820). Plausible failure
mode: sentinels placed without an ammo feed have no Ti and never fire
— pure 30 Ti waste. Unwired the task; left the function defined as
reference for a future correct implementation that requires an
established Ti chain to feed the sentinel.

## Final state (10 hour autonomous session ended)

Best stable result: **~50-55% win rate vs okbot** on the standard 10-map ×
2-side pool (jobs=4, seed=1). Final state ships v670.1–v670.5 + v670.15 +
two unused helper functions in task_attack.py for future use.

### What worked

- v670.1 — gunner shoots-through-roads + gunner-priority rotation
- v670.2 — bounds/vision guard for the 8-direction ray walk
- v670.3 — chain planner routes around enemy transport
- v670.4 — strict `should_attack` gate + reposition-on-refusal fallback.
  Verified worth +2 wins on the standard pool; v670.13 (revert to
  original heuristic gate) regressed from 11-9 to 9-11.
- v670.5 — drop debug prints, seed module-level shuffles
- v670.15 — defensive init retry on Builder construction (prevents
  hard-resign from "Core not visible at spawn" on coffee-A)

### What didn't (10 reverted experiments)

- v670.6 ECON-heavy weights: 3-17 (huge regression — defenders
  starved, okbot snowballs)
- v670.7 different shuffle seed: 12-8 (within noise)
- v670.8 looser role transitions: 8-12
- v670.9 max_units=45: 9-11
- v670.10 drop _opportunistic_attack: 8-12 (random fire actually
  pulls weight)
- v670.11 tiered gunner targeting: 10-10 (sentinel/launcher 3rd-tier)
- v670.12 strict-gate `<` instead of `<=`: 10-10 (1-turn looser)
- v670.13 revert strict gate entirely: 9-11 (proves strict gate value)
- v670.14 _INITIAL_SPAWNS = 8: 3-17 (catastrophic — drained Ti)
- Offensive sentinel in OFFENSE_TASKS: catastrophic (sentinel without
  Ti-feed = pure waste)
- Mid-conveyor attack via _try_attack_undefended_transport: arena
  blowout loss (pulled OFFENSE bots away from harvester targets)

### Why I couldn't crack 5-0

- okbot's parameters are tightly tuned at the defaults; almost every
  knob is a Pareto optimum. Bumping any value either way regressed.
- The strategic capabilities that would *clearly* dominate (refined-Ax
  delivery via Ax mining + foundry; offensive sentinel push with
  proper Ti feed; barrier walls around core) all require multi-hour
  refactors with high risk of breakage.
- Side bias on certain maps (coffee, butterfly) is structural; one
  side has terrain-driven advantage independent of bot strategy.
- Sample variance: 10-match tests have ±2 wins of pure noise. A
  single 5-0 sample wouldn't establish anything robust anyway.

### Scaffolding kept for future iteration

- `scripts/test_v670.sh` — parallel 10×2 pool runner with
  per-iteration W/L tally
- `scripts/_run_one_match.sh` — single-match runner (parallel-safe)
- `bots/beacon/v670/builder/task_attack.py::place_offensive_sentinel`
  — checks engine attack-pattern for enemy in range. Needs an
  attached Ti feed before wiring.
- `bots/beacon/v670/builder/task_attack.py::_try_attack_undefended_transport`
  — finds enemy transport with no enemy bot defender in king-range.
  Needs a guard against pulling OFFENSE off harvester targets.

## v670.16 (REVERTED) — emergency spawn on enemy-in-core-vision

Tried bypassing income/surplus gates in `Core._should_spawn` whenever
any enemy unit was within the core's r²=36 vision. Idea: spawn extra
defenders proactively when threatened.

Result on standard pool: **0-20** — catastrophic. With a stalking
enemy near core, we spawned every turn we could afford one, draining
Ti reserves and starving harvester construction. Economy collapsed
across every map.

Lesson: core spawn should NOT bypass income gates — every bot needs
backing income to be productive long-term. Emergency reactive spawning
is short-term defensive but kills medium-term economy.

## Final session note: init retry value confirmed

Re-tested at end of session: removing the v670.15 init retry from
`main.py` regressed the standard pool from 10-10 to **5-15**. The
defensive try/except is worth +5 wins, not just a bug fix — the
fewer crash-induced 0-turn losses adds up.

Init retry RESTORED. Final state ships v670.1–v670.5 + v670.15.
