# CLAUDE.md

## What This Is

Cambridge Battlecode bot repository. You write Python bots that control units (core, builder bots, turrets) to mine titanium and axionite, build logistics networks, and win by destruction or tiebreaker score. Each unit runs an independent instance of the same code. The game lasts up to 2000 rounds.

## Active Bot

`bots/tree_denial_clean/` is the current competitive bot. It has a dual Ti/Ax economy with Foundries for refined Axionite production. See `bots/tree_denial_clean/DESIGN.md` for architecture details.

Reference/opponent bots: `bots/starter/`, `bots/harvester_punisher/`, `bots/ore_capper/`.

## Source of Truth

Use `llms.txt` for game rules, entity stats, Controller API, enums, constants, and CLI behavior. Prefer it over memory. It indexes the official docs.

## Commands

All commands run through the repo-local virtualenv:

```bash
# Run a local match
venv/bin/cambc run bots/tree_denial_clean starter maps/default_large1.map26

# Reproduce with fixed seed + replay
venv/bin/cambc run bots/tree_denial_clean starter --seed 835464624 --replay /tmp/run.replay26

# Local eval suite (5 deterministic cases)
venv/bin/python tools/eval.py --bot bots/tree_denial_clean

# Watch a replay
venv/bin/cambc watch replay.replay26

# Remote TLE-enforced test match
venv/bin/cambc match test bots/tree_denial_clean bots/starter maps/default_large1.map26

# Debug output
CAMBC_DEBUG=1 venv/bin/cambc run bots/tree_denial_clean starter maps/default_small1.map26 2>&1 | grep "pattern"
```

## Validation Flow

1. Make a change
2. Run `venv/bin/python tools/eval.py --bot bots/tree_denial_clean` — expect 5/5 wins
3. Check Ax and Ti production in eval output — regressions matter
4. For behavior bugs: run with `CAMBC_DEBUG=1`, grep stderr, inspect replays
5. For timing: use local profiling + remote `cambc match test` (do not trust local `--tle`)

## Implementation Principles

- Keep hot paths branch-light and allocation-light. 2ms CPU budget per unit per round.
- State on `self` is a cache — timeouts can interrupt mid-turn, so `run()` must recover.
- Derive roles from cheap local facts (entity type, spawn order, position).
- Route around bare ore tiles so future harvesters aren't blocked.
- Use `_classify_tile` to gate conveyor placement — it enforces ore avoidance, enemy detection, and contamination prevention.
- Test with replays and eval, not unit tests. Attach map, seed, and replay when debugging.

## Coding Style

Python, 4-space indent. `UPPER_SNAKE_CASE` for module constants, `snake_case` for methods/variables, `CamelCase` for classes. Match existing patterns in the active bot.

## File Layout (tree_denial_clean)

- `main.py` — core + builder state machines, connect-back, infra bot, classify_tile
- `nav.py` — bugnav pathfinder
- `markers.py` — marker encoding/decoding
- `constants.py` — direction tables, shared config, debug helper

## Commits

Short imperative subjects under ~72 chars. Examples: `Optimize fortress bridge picker hot paths`, `Add tree_denial_clean bot with dual-Foundry Ax economy`. Use `Checkpoint ...` for temporary milestones only.
