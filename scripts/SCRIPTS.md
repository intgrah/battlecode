# Analysis Scripts

All scripts take a replay path as first argument, defaulting to `replay.replay26`.

## Core

**replay_parse.py** -- Shared library. Parses protobuf replays and collects per-team stats in a single pass: entities placed/removed/alive, resource history, income rate, conveyor flow, builder idle turns, self-destructs (distinguished from enemy kills via damage tracking), exec time, TLEs. Used by stats, economy, spatial.

**replay_stats.py** (`just stats`) -- One-page game summary. Winner, resources, harvesters, income rates, damage/kills/self-destructs, build counts, first-built milestones, conveyor throughput.

## Economy

**replay_economy.py** (`just economy`) -- Per-team economy over time. First income turn, harvester count/connectivity, income rate at quartiles, collected/spent, infrastructure counts, Ti curve samples.

**replay_throughput.py** -- Delivery pipeline analysis. First delivery to core, harvester-to-delivery latency, flow loss (harvester output vs core delivery), delivery efficiency vs theoretical max, delivery rate in time windows, throughput saturation (in-degree >= 4), chain length as latency proxy.

## Builder Behavior

**replay_builders.py** -- Per-builder action breakdown (move/idle/build_*/spawn/die percentages). Stuck detection (10+ consecutive idle turns). Avg lifetime, builds per builder, max distance from core, round trips.

**replay_spatial.py** (`just spatial`) -- Builder spread, idle percentage, moves per team, infrastructure ratio (transport vs roads), first harvester/conveyor timing.

## Conveyor Network

**replay_network.py** (`just network`) -- Ore utilization (seen/harvested/blocked), conveyor activity (active vs dead), per-harvester flow and connectivity, bottleneck tile, theoretical max income.

**replay_graph.py** (`just graph`) -- Directed graph analysis of conveyor chains. Chain roots (no input), dead ends, per-harvester chain tracing with hop count and straight-line ratio, live vs dead conveyors, shared trunk tiles.

**replay_flow.py** (`just flow`) -- Betweenness centrality of conveyor tiles (how many harvester chains pass through each tile). Identifies critical tiles whose destruction affects multiple harvesters.

**replay_health.py** (`just health`) -- Chain health over time. Harvester connectivity sampled every 20 turns, break/repair events, destruction cause detection (enemy raid vs self-destroy), cost scale breakdown, harvester adjacency analysis (wasted conveyors).

**replay_deep.py** (`just deep`) -- Combined time-series analysis. Max-flow connectivity snapshots every 100 turns, builder activity breakdown, raid impact (conveyor destructions and harvesters disconnected), core delivery rate in time windows.

## Combat & Defense

**replay_combat.py** (`just combat`) -- Damage dealt by target type, damage window and peak DPS, self-destruct events and timing, builder losses (killed vs self-destructed), turret stats (built/alive/shots/efficiency), enemy buildings destroyed, raid arrivals near enemy core.

**replay_vulnerability.py** -- Final-state vulnerability analysis. Single points of failure (tiles whose destruction disconnects N harvesters), defense coverage (% transport tiles within turret range), harvester defense, exposed tiles to enemy turrets.

## Map & Territory

**replay_map.py** (`just map`) -- ASCII map rendering at a given turn. Entity grid with team coloring, builder heatmaps per team with coverage stats. Supports turn selection and mode filtering.

**replay_territory.py** -- Exploration and expansion over time. Exploration coverage (% passable tiles seen), ore discovery rate, ore harvested vs seen, territorial radius (furthest building from core), enemy proximity to core. Timeline snapshots at t=50,100,200,500,1000,1500,1999.

## Batch

**batch_analyze.py** -- Aggregates replay_parse stats across a directory of replays. Overall win rate, per-opponent and per-map breakdown, avg/median of key metrics for both us and opponents.

## Utilities

**replay_parse.py** -- Shared parser (see Core above).

**download_match.py** -- Downloads all game replays for a match ID from the platform API.

**tournament.py** -- Local round-robin tournament runner, bot versioning (snapshot/latest/list/prune).
