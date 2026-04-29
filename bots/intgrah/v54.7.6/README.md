# v54.7.6 — roadmap

Open work, in rough priority order.

## Routing

- **Replace `econ_astar` (A* conv routing)** with something that respects the
  full transport graph + terrain. The current A* uses cost grid + a fixed
  routability bitmap; doesn't model existing flow saturation, doesn't see
  bridges as anything special beyond a 1+9 cost edge. Affordability gate
  (below) depends on this being route-aware.

## Ore / harvester economics

- **Ore use-class beyond the bisector cut.** Each ore should be classified
  as `econ`, `offensive`, `both`, or `ignore` based on bisector position,
  sink saturation, distance, terrain risk (enemy turret cones, walls
  isolating it, etc.). Current code splits sharply at the bisector — too
  coarse.
- **Route-aware affordability gate.** `can_afford_ore_claim` currently uses
  Chebyshev to sink + linear `0.7·CONVEYOR + 0.3·BRIDGE/3` per tile. It
  ignores walls, ignores saturation of the destination trunk, ignores
  exposure on the enemy side. After A* removal, replace the heuristic with
  the actual estimated chain length on the post-routing graph and penalise
  enemy-side tiles.

## Combat / defense

- **Unify offense/defense turret micro.** Both decide "is there something
  worth hitting → where + facing maximises high-value targets in
  line/cone". Same scoring, different chain-extension target afterward
  (own core vs enemy core). Currently duplicated.
- **Defend offensive harvesters too.** Same sentinel/gunner micro applies
  to forward harvesters; offense currently doesn't run the guard pass.
- **Real patrolled defense.** DEFENSE is presently `ECON + patrol_cheap +
  patrol_late`, where `patrol_cheap` is a random walk along upstream
  conveyor edges. Replace with coverage-guaranteed patrol: every owned
  building is seen by some friendly unit on a bounded interval, no
  sneak-attack windows. Coverage-set assignment per round.

## Misc

- Remove TEMP DEBUG logs once their respective bug classes are settled.
- Sweep `log(f"…")` call sites in `_policy.py`, `econ.py` (TEMP DEBUG),
  `build_foundry.py` etc. to use rich `log("tmpl {x}", x=val)` form.
