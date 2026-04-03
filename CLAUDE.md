This project is for the Cambridge Battlecode competition (hosted by University of Cambridge, NOT MIT).

Docs: https://docs.battlecode.cam — local copy in `docs/` (run `just docs` to update).
Read the relevant files in `docs/` before writing or modifying bot code.
CLI: `cambc`. Python 3.12 (stdlib only, no pip packages). 2ms CPU time per unit per round (+5% buffer). 1 GB memory limit per bot.

Reference materials from previous MIT Battlecode years are in `ref/`.

## Game Summary

Set on Titan. Objective: destroy enemy core (3x3, 500 HP). Max 2000 rounds. Maps 20x20 to 50x50, guaranteed symmetric (reflection or rotation). Max 50 living units per team (including core).

Resources: titanium (start 500, +10 passive every 4 rounds) and axionite (raw/refined). Move in stacks of 10 via conveyors and bridges. Raw axionite delivered to core or turrets is destroyed — refine it first. Core can convert refined ax to Ti (1 Ax → 4 Ti) via `c.convert(amount)`.

Win condition tiebreakers (in order): refined axionite delivered, titanium delivered, harvesters alive, axionite stored, titanium stored, coinflip. Note: `c.convert()` moves Ax from Ax-collected stat to Ti-collected stat.

### Units (run independent code instances)

- Core: spawns builder bots on any empty core tile (3x3), vision r²=36, action r²=8 from centre. 1 spawn per round.
- Builder bot: only mobile unit, 30 HP, 30 Ti, 20% scale, vision r²=20, action r²=2. Builds, heals (4 HP for 1 Ti to ALL friendly entities on target tile), attacks building on own tile (2 dmg for 2 Ti), destroys allied buildings (free, unlimited per round). Self-destruct does NO damage. Walks only on conveyors, roads, allied core.
- Gunner: 40 HP, 10 Ti, 10% scale, vision/attack r²=13, 10 dmg (30 with refined ax), reload 1, 2 ammo/shot. Targets closest non-empty tile in facing direction. Markers targetable but don't block; walls block but aren't targetable. Can rotate to any direction for 10 Ti (`c.rotate(direction)`, 1-turn cooldown).
- Sentinel: 30 HP, 30 Ti, 20% scale, vision/attack r²=32, 18 dmg, reload 3, 10 ammo/shot. Hits within 1 king-move of facing line. Refined ax ammo: +5 action/move cooldown stun.
- Breach: 60 HP, 15 Ti + 10 Ax, 10% scale, vision r²=13, attack r²=5, 40 dmg + 20 splash (8 surrounding tiles), reload 1, 5 ammo (refined ax only). 180° cone. Friendly fire on splash.
- Launcher: 30 HP, 20 Ti, 10% scale, vision r²=26, action r²=2 (pickup), throw r²=26, reload 1. Throws adjacent builder bots to bot-passable tile. No facing direction, no ammo.

### Buildings

- Road (5 HP, 1 Ti, 0.5%): walkable
- Marker (1 HP, free, no scale): u32 value, only comms between units. Not walkable, counts as building. Destroyable for free. One per round per unit, separate from action cooldown.
- Barrier (30 HP, 3 Ti, 1%): blocks space
- Conveyor (20 HP, 3 Ti, 1%): cardinal only. 3 inputs, 1 output
- Splitter (20 HP, 6 Ti, 1%): cardinal only. 1 input (back), 3 rotating outputs. Prioritises least recently used direction.
- Bridge (20 HP, 20 Ti, 10%): teleports stack to tile within dist² 9. Accepts from all directions.
- Armoured conveyor (50 HP, 5 Ti + 5 refined ax, 1%): like conveyor but tankier
- Harvester (30 HP, 20 Ti, 5%): auto-mines, outputs every 4 rounds. First output is immediate on build round. Prioritises least recently used direction. NOT a unit.
- Foundry (50 HP, 40 Ti, 100%): Ti + raw ax -> refined ax

Cost scaling: additive. Each entity built increases scale by its % contribution. cost = floor(scale \* base_cost). Scale starts at 1.0x.

All units have action r²=2 (for building/markers/destroy) except core (r²=8 from centre). Turrets have separate attack ranges listed above.

Turrets face a direction, receive ammo from non-facing sides. Diagonal turrets can be fed from all four sides. Turrets hold max one stack, only accept when empty. Raw axionite fed to turrets is destroyed. If a builder bot stands on a building, turret attacks hit only the bot.

Communication: markers only (each unit is an isolated Python instance, no shared globals).

Resources can be sent to enemy buildings — careful with conveyor placement near opponents.

## Codebase Structure

Bots live in `bots/<name>/`. Each bot folder is a self-contained package with a `main.py` containing the `Player` class. Versioned as `v1`, `v2`, ... `v39`. The latest version is the active development target.

Typical bot module layout (v39 style):

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
just snapshot          # freeze current version, create next
just match v39 v38     # run + print summary stats
just watch v39 v38     # run with live visualiser
just stats             # quick summary of last replay
just analyze           # full analysis of last replay
just lint              # ruff check --fix
just fmt               # ruff format
just f                 # lint + fmt
just submit            # upload latest version to ladder
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
