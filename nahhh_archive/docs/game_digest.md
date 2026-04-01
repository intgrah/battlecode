# Game Digest For Agents

This is the local short-form reference for Cambridge Battlecode. Treat [llms.txt](/Users/jakewright/Code/cambc/llms.txt) as the index of record, and check the linked official docs whenever a rule, API detail, or stat matters.

## Core Constraints

- Units run independent instances of the same submitted code. The core, builder bots, and turrets are units; harvesters are not.
- Units take turns in spawn order. After all units act, resource distribution happens.
- Builder bots are the only mobile units. Most strategy is builder allocation, logistics, and combat construction.
- The official game limit is 2000 rounds. If both cores live, tiebreakers are: (1) refined axionite delivered to core, (2) titanium delivered to core, (3) harvesters alive, (4) stored resources. Raw axionite is destroyed when given to a core or turret — only Foundry-refined axionite counts.
- The server budget is 2ms CPU per unit per round with a small buffer. If a unit times out, it is interrupted and `run()` starts fresh next round.

## Coding Implications

- Build around local, cheap decisions. Heavy global planning and repeated full-map scans are usually the wrong default.
- Use IDs, positions, and cached state instead of constructing expensive abstractions in hot paths. The API is intentionally ID-based for speed.
- Query current costs through controller getters rather than hard-coding scaling assumptions.
- Treat in-memory `self` state as a cache, not the only source of truth. Timeouts can interrupt a turn mid-plan.
- Use markers, stdout, and debug indicators deliberately. They are part of the development loop, not optional polish.

## Strategy Implications

- Optimize for match wins, not isolated tactics. Stable economy and resource delivery matter because of long-game tiebreakers.
- Make opening roles explicit and cheap to compute.
- Separate fast pathing from expensive recovery logic. The normal case should be simple and branch-light.
- Prefer protocols that degrade gracefully under congestion, partial vision, or stale local state.

## Source Links

- Official overview: https://docs.battlecode.cam/spec/overview
- Controller API: https://docs.battlecode.cam/api/controller
- Builder bot spec: https://docs.battlecode.cam/spec/builder-bot
- Resources and costs: https://docs.battlecode.cam/spec/resources
- Match format: https://docs.battlecode.cam/getting-started/matches
