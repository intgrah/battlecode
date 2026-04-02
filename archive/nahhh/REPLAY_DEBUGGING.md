# Replay Downloading And Decoding

The repo now ships replay tooling under `tools/` that should be preferred over the older `falafel/...` scripts in this note.

Current repo-owned commands:

```sh
venv/bin/python tools/replay_digest.py /abs/path/to/replay.replay26
venv/bin/python tools/replay_trace.py /abs/path/to/replay.replay26 --entity 4 --turn-from 100 --turn-to 140 --only-events
venv/bin/python tools/replay_search.py /abs/path/to/replay.replay26 --pattern connect_follow_unknown
venv/bin/python tools/replay_loops.py /abs/path/to/replay.replay26 --entity 4 --turn-from 300 --turn-to 360
venv/bin/python tools/replay_hotspots.py /abs/path/to/replay.replay26 --team A --limit 10
venv/bin/python tools/eval.py --bot bots/tree_denial_clean
```

The historical workflow below is still useful background, but the protobuf-backed tooling in this repo is now the default path.

This is the current practical workflow for remote replay debugging in this repo.

## What remote `print()` does

- `print(...)` from the bot goes into replay stdout and can be inspected in the replay viewer or extracted by tooling.
- `print(..., file=sys.stderr)` is useful locally in the terminal, but not for remote server runs.
- If you want remote bot-state debugging, emit stdout deliberately and keep it scoped.

Good examples:
- connect state transitions
- nav failure reasons
- selected sink / waypoint / landing
- state transitions, not every tiny internal helper

## Local runs

Important:

- local runs are for behavior, fast iteration, and local profiling
- do not trust local `--tle` as authoritative timing validation
- remote `cambc match test` replays are the source of truth for `exec_time_us` and `tled`

Basic local run:

```sh
venv/bin/cambc run bots/tree_denial_clean starter maps/default_large1.map26
```

Exact seed local run:

```sh
venv/bin/cambc run bots/tree_denial_clean starter maps/default_large1.map26 \
  --seed 835464624 \
  --replay /tmp/large1.replay26
```

Trace-heavy local run:

```sh
CAMBC_DEBUG=1 CAMBC_TRACE_STATE=1 \
venv/bin/cambc run bots/tree_denial_clean starter maps/default_large1.map26 \
  --seed 835464624 \
  --replay /tmp/large1_trace.replay26 \
  > /tmp/large1_trace.log 2>&1
```

Useful env vars:
- `CAMBC_DEBUG=1`: enables `dbg(...)`
- `CAMBC_TRACE_STATE=1`: enables the more verbose `CONNECT_TRACE` / state dumps

## Remote test runs

Single map:

```sh
venv/bin/cambc match test bots/tree_denial_clean bots/starter maps/default_large1.map26
```

Multiple maps in one submission:

```sh
venv/bin/cambc match test bots/tree_denial_clean bots/starter \
  maps/default_large1.map26 \
  maps/default_medium1.map26 \
  maps/pls_buy_cucats_merch.map26
```

Status:

```sh
venv/bin/cambc match tests
```

Important:
- server test runs do not automatically put replay files in the repo
- download replays with `venv/bin/cambc match replay MATCH_ID`

## Downloading remote replays

Current CLI flow:

```sh
venv/bin/cambc match replay MATCH_ID
venv/bin/cambc match replay MATCH_ID --game 3
```

## Current decoding tools

### 1. Digest

Quick summary:

```sh
venv/bin/python tools/replay_digest.py /abs/path/to/replay.replay26
```

What it gives:
- total TLE count
- first TLE rounds
- worst bot ids
- rough mode summaries like `simple_no_wall_follow`, `wall_follow`, etc.

What it does not prove:
- exact internal Python branch path
- full planner state unless we logged it into stdout

### 2. Trace

Focused per-bot replay trace:

```sh
venv/bin/python tools/replay_trace.py /abs/path/to/replay.replay26 \
  --entity 4 \
  --turn-from 100 \
  --turn-to 140 \
  --only-events
```

This is the most useful tool when stdout tracing is present.

What it gives:
- bot positions per round
- moves vs stationary rounds
- stdout lines for that bot/round window
- `exec_time_us` / `tled` for that bot on the traced turns

This is how we diagnosed:
- repeated `plan_clear -> plan_set` churn
- `follow_landing` loops
- soft-hold stalls
- whether a bot actually moved on a TLE round

### 3. Search

Fast stdout search across the whole replay:

```sh
venv/bin/python tools/replay_search.py /abs/path/to/replay.replay26 \
  --pattern connect_follow_unknown
```

Useful variants:

```sh
venv/bin/python tools/replay_search.py /abs/path/to/replay.replay26 \
  --pattern 'control_guard_fallback|guard_blocked|advance_waypoint_stuck' \
  --entity 7 \
  --turn-from 1 \
  --turn-to 40

venv/bin/python tools/replay_search.py /abs/path/to/replay.replay26 \
  --pattern 'CONNECT_TRACE|NAV_TRACE' \
  --entity 4 \
  --turn-from 200 \
  --turn-to 220 \
  --include-turn
```

What it gives:
- matching turns without manually tracing one entity first
- entity ids and positions for each matching stdout turn
- optional full-turn stdout when you need surrounding lines

### 4. Loops

Automatic repeated-pattern detection:

```sh
venv/bin/python tools/replay_loops.py /abs/path/to/replay.replay26 \
  --entity 4 \
  --turn-from 300 \
  --turn-to 360
```

Useful variants:

```sh
venv/bin/python tools/replay_loops.py /abs/path/to/replay.replay26 \
  --team A \
  --turn-from 1 \
  --turn-to 200 \
  --limit 10

venv/bin/python tools/replay_loops.py /abs/path/to/replay.replay26 \
  --entity 4 \
  --turn-from 200 \
  --turn-to 240 \
  --min-cycle 6
```

What it gives:
- long runs of the same normalized stdout turn-signature
- alternating 2-turn cycles
- a fast way to spot `restore_live_tip -> landing_source_ready -> clear_connect_landing` style loops without choosing a regex first

### 5. Hotspots

Whole-replay loop ranking:

```sh
venv/bin/python tools/replay_hotspots.py /abs/path/to/replay.replay26 \
  --team A \
  --limit 10
```

Useful variants:

```sh
venv/bin/python tools/replay_hotspots.py /abs/path/to/replay.replay26 \
  --turn-from 1 \
  --turn-to 200 \
  --limit 15

venv/bin/python tools/replay_hotspots.py /abs/path/to/replay.replay26 \
  --team A \
  --turn-from 250 \
  --turn-to 380 \
  --limit 8
```

What it gives:
- the most suspicious repeated loop windows across the whole replay
- per-entity ranking so you can pick a trace target quickly
- loop summaries biased toward stalls, recovery loops, handoff loops, and repeated restore/clear patterns

## Team attribution caveat

Raw replay events can include both teams.

Do not claim "our bots are still moving after round 400" unless you have actually separated teams.

Safer options:
- use replay viewer directly
- use bot ids/positions you know belong to us
- infer team from cores only if your decoder is explicitly doing that join

## Practical debugging workflow

1. Reproduce remotely on a focused map.
2. Download the replay with `venv/bin/cambc match replay MATCH_ID`.
3. Run `replay_digest.py` to find worst ids and first TLE rounds.
4. If the failure family is ambiguous, run `replay_trace.py` on that id/window.
5. If needed, rerun locally with:
   - exact seed
   - `CAMBC_DEBUG=1`
   - `CAMBC_TRACE_STATE=1`
6. Compare local trace against the remote replay family, not just total score.

## Debugging Principles

- Identify the exact bot and the exact round window first.
- Determine whether the bot is: replanning every round, preserving a dead continuation, stuck in a routing loop, or spending too much CPU in one step.
- Most hard replay bugs are not solved by more generic heuristics — narrow the window, then reason about state.
