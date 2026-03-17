# Beating "test" -- Opponent Breakdown

Record: 3W-15L across 18 games (2 matches).

## Their Strategy

Minimal economy, maximum raiding. 2-5 harvesters with short chains close to core. Mass builder bots (200-290 per game) that walk to our base and self-destruct on our conveyors.

## Key Numbers

### Economy

- Harvesters: 2-5 (we build 7-18)
- Conveyor chains: short (3-8 hops), compact, close to core
- Income: steady 5-15/t throughout the game, never drops to zero
- Roads built: 160-750 (used purely for builder movement, not resource transport)

### Raiding

- Builders spawned: 112-291 per game
- Self-destructs: 81-192 per game
- Builder time moving: 87-94%
- Builder time idle: 6-11%
- Round trips to our base: 1000-1700 per game
- Our conveyors destroyed per game: 81-192

### Result

- Our final income: 0/t in every loss (all chains cut)
- Our Ti collected in losses: 4-8k
- Their Ti collected: 10-29k

## Why It Works Against Us

1. Our conveyors are 20 HP. One self-destruct (20 dmg) kills one.
2. Our chains are long (7-14 hops) with many single points of failure.
3. We have zero turrets defending infrastructure.
4. Our builders are 28-63% idle, theirs are 87-94% moving.
5. Our builders average 74-215 turn lifetimes. Theirs average 300-437 turns.
6. We lose every conveyor we ever built in most losses (100% conveyor loss rate).

## Why We Win the 3 Games We Win

| Game                         | Map   | Key difference                                                              |
| ---------------------------- | ----- | --------------------------------------------------------------------------- |
| intgrah_vs_test_g3           | 50x30 | Big map. We out-raided 149 SD vs 131. Our income held at 12/t.              |
| test_vs_intgrah_g3           | 30x30 | Their economy collapsed (3.4k Ti). We destroyed 66 conveyors, lost only 38. |
| intgrah_vs_test_g4 (match 2) | 30x30 | We collected 14.5k vs their 3.4k. Final income 5/t vs 0/t.                  |

Common thread: in wins, their conveyor losses exceed ours, and their final income drops to 0. We win when we do to them what they do to us -- but better.

## What Must Change

### 1. Defend conveyor chains

Even 1-2 sentinels covering the main trunk would shut down self-destruct rushes. Sentinel: r²=32 vision, 20 dmg per shot. A builder bot has 30 HP -- two sentinel shots kill it before it reaches the conveyor. With refined axionite ammo, sentinel also stuns (+3 cooldown), preventing the self-destruct action entirely.

### 2. Compact chain routing

The problem isn't harvester count -- more harvesters is strictly better for income. The problem is that each harvester adds a long, undefended chain. Route chains to merge into a defended trunk early. A harvester 15 tiles away doesn't need 15 exposed conveyor tiles -- it needs a short spur to the nearest defended trunk line.

### 3. Use roads for travel, conveyors only for supply

Test builds 160-750 roads for builder movement. We use conveyors for both travel and transport, creating 82% dead conveyor rates. Roads are cheaper (1 Ti, 0.5% scale vs 3 Ti, 1% scale) and don't create fake transport paths.

### 4. Increase raiding efficiency

Their builders are 93% moving, ours are 32-68%. Their builders make 1000+ round trips, ours make 167-295. We need faster builder cycling: spawn, walk to enemy, self-destruct, repeat.

### 5. Armoured conveyors on critical tiles

Armoured conveyors have 50 HP -- a self-destruct only does 20 dmg. Two self-destructs needed to kill one. Costs 10 Ti + 5 refined Ax, but on the 3-5 most critical tiles (single points of failure), this doubles durability. Requires a foundry, but that also wins tiebreaker #1.

### 6. Small map adaptation

We lose 100% of small map games (20x20, 21x21). On small maps, the raider travel distance is tiny -- they reach our base in ~10 turns. Defense is even more critical here. Sentinels covering the trunk are mandatory. Harvest everything, but funnel all chains through a defended corridor.
