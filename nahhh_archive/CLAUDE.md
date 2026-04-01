# CLAUDE.md

**Do not introduce excessive complexity.** Before adding a new flag, subsystem, or fix layer, ask whether the problem can be solved by simplifying the existing model. Read the Complexity Guardrails section below and the Ax economy postmortem in memory before proposing multi-mechanism changes.

## What This Is

Cambridge Battlecode bot repository. You write Python bots that control units (core, builder bots, turrets) to mine titanium and axionite, build logistics networks, and win by destruction or tiebreaker score. Each unit runs an independent instance of the same code. The game lasts up to 2000 rounds.

## Active Bot

`bots/tree_denial_clean/` is the current competitive bot. Ti-only economy — infra bot + Ti builders connect harvesters to core via conveyor/bridge chains. Key bot docs:

- `bots/tree_denial_clean/DESIGN.md` — architecture, state machines, mechanisms
- `bots/tree_denial_clean/TODO.md` — prioritized task list and known issues

Keep `DESIGN.md` and `TODO.md` up to date as you make changes. After completing a task, mark it done in `TODO.md` and update `DESIGN.md` if the architecture changed.

Reference/opponent bots: `bots/starter/`, `bots/harvester_punisher/`, `bots/ore_capper/`.

## Source of Truth

- [Controller API](https://docs.battlecode.cam/api/controller.md) — complete reference for all methods available to bots. Go here first for any API questions.
- `llms.txt` — indexes the official docs (game rules, entity stats, enums, constants, CLI behavior).

## Commands

All commands run through the repo-local virtualenv:

```bash
# Run a local match
venv/bin/cambc run <bot> <opponent> <map>

# Reproduce with fixed seed + replay
venv/bin/cambc run <bot> <opponent> --seed 835464624 --replay /tmp/run.replay26

# Watch a replay
venv/bin/cambc watch <replay>

# Remote TLE-enforced test match
venv/bin/cambc match test <bot> <opponent> <map>

# Submit bot to ladder
venv/bin/cambc submit <bot>

# Queue unrated matches against 10 teams above us
python tools/challenge.py

# Debug with saved replay + logs (always do this — don't pipe stderr to grep)
CAMBC_DEBUG=1 venv/bin/cambc run <bot> <opponent> <map> --seed 7 --replay /tmp/debug.replay26 2>/tmp/debug.log
# Then grep the log file and watch the replay separately
grep "pattern" /tmp/debug.log
venv/bin/cambc watch /tmp/debug.replay26
```

## Validation Flow

1. Make a change
2. Run targeted matches on relevant maps with `--replay` and `2>log` to verify behavior
3. For behavior bugs: run with `CAMBC_DEBUG=1`, always saving both replay (`--replay`) and stderr (`2>file`) to files. Never pipe stderr directly to grep — the replay and full log must be preserved so the user can cross-reference visual behavior with log output without rerunning (runs are non-deterministic).
4. For timing: use local profiling + remote `cambc match test` (do not trust local `--tle`)

## Debugging Workflow

When investigating behavior bugs, don't sift through excessive log output. Instead:
1. Run a debug match saving replay + log to files
2. Point the user to the replay path and the relevant round number so they can visually inspect
3. Only grep logs for targeted queries (specific unit id, specific state transition) — not broad sweeps

The user cross-references the visual replay with log output. Providing the replay path and approximate round is more useful than pages of log analysis.

## Implementation Principles

- Keep hot paths branch-light and allocation-light. 2ms CPU budget per unit per round.
- State on `self` is a cache — timeouts can interrupt mid-turn, so `run()` must recover.
- Derive roles from cheap local facts (entity type, spawn order, position).
- Route around bare ore tiles so future harvesters aren't blocked.
- Use `_classify_tile` to gate conveyor placement — it enforces ore avoidance and enemy detection.
- Test with replays and eval, not unit tests. Attach map, seed, and replay when debugging.
- **Every code path must have a debug log.** If a builder can take an action (move, build, heal, explore, wait), log what it's doing and why. Silent code paths cause oscillation bugs that are impossible to diagnose. Use `dbg()` in every branch.

## Complexity Guardrails

These rules exist because the dual Ti/Ax Foundry economy was shelved after cascading complexity made the bot fragile. See memory for the full postmortem.

- **Don't layer fixes on fixes.** If bug fix #3 in the same area needs a new flag gating behavior across 5+ methods, the underlying model is wrong. Step back and simplify before adding more special cases.
- **One boolean flag gating many methods is a code smell.** The `connecting_ax` flag appeared in 10+ conditionals across routing, planning, validation, and placement. That means the abstraction boundary is in the wrong place. Either split the code paths cleanly or redesign.
- **Hard-block over soft-penalty for safety constraints.** Soft A* cost penalties create "works on 35/37 maps" behavior that's painful to debug. If a tile must be avoided (contamination, enemy core), block it outright. Only use cost penalties for preferences ("prefer shorter paths"), not constraints ("never contaminate").
- **A* plans go stale.** Other units build between plan computation and execution. Always re-validate the next step's placement tile AND its output tile. If invalid, re-plan from chain_end — don't retry the same blocked step forever.
- **Propose the simplest viable approach first.** Before adding a new subsystem (barriers, per-type trees, foreign conveyor direction checking), ask: can we solve this with existing mechanisms? Can we avoid the problem entirely by constraining what we attempt?
- **Scope each fix to one mechanism.** If fixing a routing bug requires changes to A* cost model, plan validation, placement rejection, AND a new state variable, that's four mechanisms — too many. Find a fix that touches one or two.

## Coding Style

Python, 4-space indent. `UPPER_SNAKE_CASE` for module constants, `snake_case` for methods/variables, `CamelCase` for classes. Match existing patterns in the active bot.

## File Layout (tree_denial_clean)

- `main.py` — core + builder state machines, connect-back, infra bot, classify_tile
- `astar.py` — A* pathfinding for walking (8-dir) and connect-back chain planning (conveyor+bridge)
- `nav.py` — legacy bugnav pathfinder (no longer imported)
- `markers.py` — marker encoding/decoding
- `constants.py` — direction tables, shared config, debug helper

## Commits

Short imperative subjects under ~72 chars. Examples: `Optimize fortress bridge picker hot paths`, `Add tree_denial_clean bot with dual-Foundry Ax economy`. Use `Checkpoint ...` for temporary milestones only.
