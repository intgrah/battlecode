This project is for the Cambridge Battlecode competition (hosted by University of Cambridge, NOT MIT).

Docs: https://docs.battlecode.cam
CLI: `cambc` (pip install cambc). Python 3.12+. 2ms CPU time per unit per round.

Reference materials from previous MIT Battlecode years are in `ref/`.

The speculative engine in `engine/` was written before the real game released. It is no longer the target game — the real game uses `cambc` and has different mechanics. The speculative engine may still be useful for algorithmic experimentation.

## Real Game Summary

Set on Titan. Objective: destroy enemy core (3x3, 500 HP). Max 2000 rounds. Maps 20x20 to 50x50, guaranteed symmetric.

Resources: titanium (start 1000) and axionite (raw/refined). Move in stacks of 10 via conveyors.

Units (run independent code instances):
- Core: spawns builder bots, vision r²=36, action r²=8 from centre
- Builder bot: only mobile unit, 30 HP, cost 10 Ti, vision r²=20, action r²=2. Builds, heals (10 HP), destroys buildings, self-destructs (20 dmg). Moves on conveyors, roads, allied core.
- Gunner: 40 HP, 10 Ti, vision/attack r²=13, 10 dmg (+10 w/ refined ax), reload 1, 2 ammo/shot
- Sentinel: 30 HP, 15 Ti, vision/attack r²=32, 20 dmg, reload 4, 10 ammo/shot, +3 cooldown stun w/ refined ax
- Breach: 60 HP, 30 Ti + 10 Ax, vision r²=10, attack r²=5, 40 dmg + 20 splash, reload 1, 5 ammo (refined ax only), friendly fire on splash
- Launcher: 30 HP, 20 Ti, vision/attack r²=26, throws builder bots, no ammo

Buildings:
- Conveyor (20 HP, 3 Ti, 1%): 3 inputs, 1 output
- Splitter (20 HP, 6 Ti, 1%): 1 input, 3 rotating outputs
- Bridge (20 HP, 10 Ti, 1%): teleports stack to tile within dist² 9
- Armoured conveyor (50 HP, 10 Ti + 5 refined ax, 1%): like conveyor but tankier
- Harvester (30 HP, 80 Ti, 10%): auto-mines, outputs every 4 rounds
- Foundry (50 HP, 120 Ti, 100%): Ti + raw ax -> refined ax
- Road (10 HP, 1 Ti, 0.5%): walkable
- Barrier (30 HP, 3 Ti, 1%): blocks space
- Marker (1 HP, free): u32 value, only comms between units

Cost scaling: each entity built increases scale by its % contribution. cost = floor(scale * base_cost).

Turrets face a direction, receive ammo from non-facing sides. Harvesters are NOT units (auto-operate).

Communication: markers only (each unit is isolated Python instance, no shared globals).
