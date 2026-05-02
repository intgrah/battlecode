This project is for the Cambridge Battlecode competition (hosted by University of Cambridge, NOT MIT).

Docs: https://docs.battlecode.cam — local copy in `docs/` (run `just docs` to update).
Read the relevant files in `docs/` before writing or modifying bot code.
CLI: `cambc`. Python 3.12 (stdlib only, no pip packages). 2ms CPU time per unit per round (+5% rolling buffer: overage deducted, savings refunded up to cap; if both exhausted, execution is interrupted and `run()` is called fresh next round). 1 GB memory limit per bot (shared across all units — NOT per-unit).

**Sandbox: each unit is its own isolated Python subinterpreter.** There is no shared memory between units. Every module-level constant, every import, every class definition is duplicated into each unit's interpreter. A precomputed table defined at module scope is NOT shared — it is re-constructed and stored once per living unit. So: a 10 MB lookup table × 50 units = 500 MB of real memory consumed against the 1 GB global budget. Any design that sounds like "share this across builders" is impossible. Treat each unit as a completely independent process; the only cross-unit communication is via markers on tiles.

Reference materials from previous MIT Battlecode years are in `ref/`.

## Game Summary

Set on Titan. Objective: destroy enemy core (3x3, 500 HP). Max 2000 rounds. Maps 20x20 to 50x50, guaranteed symmetric (reflection or rotation). Max 50 living units per team (including core). Map cells: empty, wall (impassable, no building), titanium ore, axionite ore.

Resources: titanium (start 500, +10 passive every 4 rounds) and axionite (start 0, raw/refined). Move in stacks of 10 via conveyors and bridges. Raw axionite delivered to core or turrets is destroyed — refine it first. Core can convert refined ax to Ti (1 Ax → 4 Ti) via `c.convert(amount)`.

Turn order: units act in spawn order each round. After all units act, resources are distributed via conveyors. Cooldowns (action and move) decrease by 1 at end of round; actions/movement require cooldown = 0.
A team can call `c.resign(message=None)` to immediately forfeit (optional message saved to replay; terminates execution immediately). Win condition tiebreakers (in order): refined axionite delivered to core, titanium delivered to core, harvesters alive, axionite stored, titanium stored, coinflip. Note: `c.convert()` moves Ax from Ax-collected stat to Ti-collected stat.

### Units (run independent code instances)

- Core: spawns builder bots on any empty core tile (3x3), vision r²=36, action r²=8 from centre. 1 spawn per round (costs action cooldown).
- Builder bot: only mobile unit, 40 HP, 30 Ti, 20% scale, vision r²=20, action r²=2. Builds, heals (4 HP for 1 Ti to ALL friendly entities on target tile; fails if nothing would gain HP), attacks building on own tile (2 dmg for 2 Ti via `can_fire()`/`fire()`), destroys allied buildings (free, unlimited per round). Self-destruct does NO damage (terminates execution immediately). Moving costs +1 move cooldown. Walks on conveyors, splitters, armoured conveyors, bridges, roads (any direction, either team), and allied core. If tile has a builder bot, only walkable buildings (roads and conveyors) can be built there.
- Gunner: 40 HP, 10 Ti, 10% scale, vision/attack r²=13, 10 dmg (25 with refined ax), reload 1, 2 ammo/shot. Fires along forward ray; markers targetable but don't block LoS; walls block but aren't targetable; bots/non-marker buildings block and are targetable. Can rotate to any direction for 10 Ti (`c.rotate(direction)`, 1-turn cooldown).
- Sentinel: 30 HP, 30 Ti, 20% scale, vision/attack r²=32, 18 dmg, reload 3, 10 ammo/shot (titanium). Hits within 1 king-move of facing line within vision range. Refined ax ammo: +5 action/move cooldown stun.
- Breach: 60 HP, 15 Ti + 10 Ax, 10% scale, vision r²=2, attack r²=24, 40 dmg + 20 splash (8 surrounding tiles), reload 1, 5 ammo (refined ax only). 180° cone. Friendly fire on splash (does not damage itself). Accepts all resource types but only stores refined ax as ammo; Ti and raw ax delivered to breach are destroyed.
- Launcher: 30 HP, 20 Ti, 10% scale, vision r²=26, action r²=2 (pickup), throw 0 < r² ≤ 26, reload 1. Throws adjacent builder bots to bot-passable tile. No facing direction, no ammo.

### Buildings

- Road (4 HP, 1 Ti, 0.5%): walkable
- Marker (1 HP, free, no scale): u32 value, only comms between units. Not walkable, counts as building. Any team can build over markers (destroying them). All units (core, builder bots, turrets) can destroy friendly markers for free. Don't block gunner LoS. One per round per unit, separate from action cooldown.
- Barrier (30 HP, 3 Ti, 1%): blocks space
- Conveyor (20 HP, 3 Ti, 1%): cardinal only. 3 inputs, 1 output
- Splitter (20 HP, 6 Ti, 1%): cardinal only. 1 input (back), 3 rotating outputs. Prioritises least recently used direction.
- Bridge (20 HP, 20 Ti, 10%): teleports stack to tile within dist² 9. Accepts from all directions. Bypasses directional restrictions on target building.
- Armoured conveyor (50 HP, 5 Ti + 5 refined ax, 1%): like conveyor but tankier. Immune to builder bot attacks.
- Harvester (30 HP, 20 Ti, 5%): must be placed on ore deposit. Auto-mines, outputs every 4 rounds. First output is immediate on build round. Prioritises least recently used direction. NOT a unit.
- Foundry (50 HP, 40 Ti, 50%): accepts input/output from any side. Feed one stack Ti, then one stack raw ax → outputs one stack refined ax.

Cost scaling: additive. Each entity built increases scale by its % contribution. cost = floor(scale \* base_cost). Scale starts at 1.0x. Destroyed entities remove their scaling contribution.

All units have action r²=2 (for building/markers/destroy) except core (r²=8 from centre). Turrets have separate attack ranges listed above.

Turrets (except launcher) face one of 8 directions, receive ammo from non-facing sides (via conveyors, adjacent harvesters, adjacent foundries, or bridges targeting the turret's tile). Diagonal turrets can be fed from all four cardinal sides. Turrets hold max one stack, only accept when empty. Raw axionite fed to turrets is destroyed. If a builder bot stands on a building, turret attacks hit only the bot.

Communication: markers only (each unit is an isolated Python instance, no shared globals). Can overwrite friendly markers but not enemy markers.

Resources can be sent to enemy buildings — careful with conveyor placement near opponents.

## Codebase Structure

Bots live in `bots/<name>/`. Each bot folder is a self-contained package with a `main.py` containing the `Player` class. Versioned as `v1`, `v2`, ... `v50`. The latest version is the active development target.

Typical bot module layout (v50 style):

- `main.py` — `Player` class, dispatches to `Core` or `Builder` based on `EntityType`
- `core.py` — core spawning logic
- `builder.py` — builder bot decision-making
- `entity.py` — base class for units
- `util.py` — shared constants (directions, deltas)
- `map_belief.py` — map state tracking from partial vision
- `marker.py` — marker encoding/decoding for comms
- `*astar.py`, `bugnav.py` — pathfinding algorithms
- `flow_graph.py`, `flow_astar.py`, `network.py` — conveyor network planning
- `comms.py` — inter-unit communication protocols
- `params.py` — tunable parameters

Analysis scripts live in `scripts/`. Replay analysis via `just analyze`, `just stats`, etc.

## Development Workflow

```
just match v50 v49     # run + print summary stats
just watch v50 v49     # run with live visualiser
just stats             # quick summary of last replay
just analyze           # full analysis of last replay
just lint              # ruff check --fix
just fmt               # ruff format
just f                 # ty + lint + fmt
just submit intgrah/v50  # build + upload to ladder
just status            # check ladder rating
```

## Python Style

Always run `ruff check --fix --unsafe-fixes` and `ruff format` before committing. Run `ty check` for type checking. Never suppress linter warnings with `noqa` comments or by adding rules to the global ignore list — fix the underlying issue instead.

### Type annotations

- Annotate all function signatures and non-trivial variables.
- Use lowercase generics from `collections.abc` and builtins: `list[int]`, `dict[str, int]`, `tuple[int, ...]`, `set[str]`, `Sequence`, `Mapping`, `Iterable`. Never use `typing.List`, `typing.Dict`, `typing.Tuple`, etc.
- Use `dict` only for partial-function mappings (e.g., lookup tables, caches). For structured data with known fields, use `dataclass` instead (or rarely, `NamedTuple`).
- Use `X | Y` union syntax, not `Union[X, Y]` or `Optional[X]`. Write `X | None` instead of `Optional[X]`.
- Use `TYPE_CHECKING` guard for imports only needed by type checkers.

### Immutability and state

- Prefer immutable data structures: tuples over lists for fixed-size data, `frozenset` over `set` for constant collections.
- Avoid mutable default arguments. Use `None` as default and create the mutable object inside the function.
- Avoid mutable module-level state. Constants should be truly constant (tuples, frozensets, `Final`).
- Keep mutable state contained within classes and minimize its scope.

### General conventions

- Use `GameConstants` for game values (e.g., `GameConstants.MAX_TURNS`, `GameConstants.STACK_SIZE`). Do not hardcode numeric constants that exist in the API.
- Share common definitions (direction lists, delta tables, frequently used constants) in a `util.py` module rather than redefining them across files.
- Prefer early returns over deeply nested conditionals.
- Use `match`/`case` for multi-branch dispatch on enums.
- Use comprehensions over manual loop-and-append patterns when the result is a simple transformation.
- Keep functions short and focused. Extract helpers when a function exceeds ~30 lines.
- Use `cambc` API cost getters (`c.get_conveyor_cost()`, etc.) instead of manually computing scaled costs.
- Use `can_*` checks before performing actions to avoid `GameError` exceptions.
- Be mindful of the 2ms CPU budget. Avoid unnecessary allocations, deep recursion, and O(n²) loops over large tile sets.
