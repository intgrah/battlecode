# Analysis Scripts

## Analysis Package (`analysis/`)

The primary analysis system. Modular sections with typed reports.

```bash
just analyze replay.replay26              # all sections
just analyze replay.replay26 -s summary   # one section
just stats replay.replay26                # shortcut for summary
just full replay.replay26                 # all sections, single process
```

### Sections

- **summary** -- Winner, entity counts, resources, milestones, exec time/TLE
- **economy** -- Income rates (peak/final/quartiles), delivery efficiency, flow loss
- **combat** -- Damage dealt/received, DPS windows, turret stats, kills, raids
- **defense** -- Turret coverage of harvesters/conveyors, core defense, exposure
- **network** -- Harvester connectivity, dead conveyors, max flow, SPOFs, Steiner tree
- **spatial** -- Vision coverage, ore discovery, map control, building reach
- **bots** -- Builder actions, idle/stuck/oscillation, lifetimes, clustering
- **compare** -- Head-to-head team comparison across 20+ metrics

### Infrastructure

- `parse.py` -- Loads protobuf replay, extracts map metadata
- `scan.py` -- Single-pass timeline scanner producing `ScanData`
- `snapshot.py` -- Game state reconstruction at sampled turns
- `graph.py` -- NetworkX-based conveyor graph analysis (connectivity, max flow, SPOFs)
- `constants.py` / `types.py` -- Shared types and game constants

## Event Debugger

**replay_debug.py** -- Event-driven replay debugger producing LLM-readable narratives.

```bash
just debug replay.replay26                    # all events
just explain replay.replay26                  # high-priority only, compact
just debug-team replay.replay26 A             # filter to team A
just debug-entity replay.replay26 47          # follow one entity
just debug replay.replay26 --turns 200-300    # turn range
just debug replay.replay26 --event break,combat
just debug replay.replay26 --json             # structured JSON output
```

## Other Scripts

- **replay_map.py** (`just map`) -- ASCII map rendering at a given turn, builder heatmaps
- **replay_markers.py** -- Marker communication analysis (write rate, overwrites)
- **replay_full.py** (`just full`) -- Runs all analysis sections in one process
- **batch_analyze.py** -- Aggregates stats across a directory of replays
- **online_analyze.py** -- Analyze recent online matches from the platform API
- **trace_builder.py** -- Early-game builder narrative with oscillation detection
- **raid_trace.py** -- Chronological threat event list
- **verify_network.py** -- Compares bot network beliefs against ground truth
- **download_match.py** -- Downloads replays for a match ID
- **tournament.py** -- Local round-robin tournament runner
