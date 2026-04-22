# bugnav-viewer

Interactive viewer + offline benchmark harness for pathfinding algorithms on
`.map26` maps, targeting the Cambridge Battlecode 2026 unit navigation problem.

## Problem

Each builder bot in Battlecode is its own isolated Python subinterpreter with
no shared memory. It gets **2 ms of CPU per round** (with a small rolling
buffer; overrun kills the turn). Per-turn worst-case cost is what matters —
you can't amortise work across turns, because a single overrun turn "dies".

Each bot sees only what lies within its sensor disc: squared radius r² ≤ 20
(69 cells). Anything outside must be remembered from past sensing or
optimistically / pessimistically assumed. Maps are 20×20 to 50×50,
8-connected (diagonals cost 1), all pass/wall (ore is walkable).

The task: given a start, goal, and a sensor-limited view of the map, move
one step per turn toward the goal so that
- you actually arrive (completeness),
- the total path length is close to optimal (quality),
- and the worst-case per-turn work fits in 2 ms on CPython
  (`~30 μs` PyPy = `~300 μs` CPython budget headroom).

"Full-map BFS" is the quality ceiling (assuming uniform cost). Plain bug
algorithms are the cheap floor but have pathological cases. This viewer
exists to explore the space in between.

## Approach

- **Viewer** (`src/main.rs`, `src/app.rs`, `src/ui.rs`) — eframe/egui GUI.
  Pick an algorithm and map, click start + goal, step / play / reset. Shows
  visited cells, frontier, current pos, and the best-known path.
- **Benchmark** (`src/bin/benchmark.rs`) — runs N random start/goal pairs
  per map across all maps, times out at `--iters`, and reports per-algorithm
  convergence + path-length-ratio quantiles against ground-truth BFS.
- **Ground truth** — `pathfinder::shortest_path` runs full 8-connected BFS
  on the whole map (not available to the algorithms under test). Used only
  to decide reachability and the denominator of the quality ratio.

### Metrics

For each (algo, start, goal):
- `reach`, `false_un`, `tle` — outcome when BFS says reachable.
- `corr_un`, `un_tle` — outcome when BFS says unreachable.
- `conv%` = reached / BFS-reachable. Completeness proxy.
- `p50..p100` — quantiles of `(algo path length) / (BFS path length)`
  over reached trials. Quality proxy.

## Algorithm catalogue

Each algorithm lives in `src/algorithms/`. All use the shared sensor /
wall-follow / Bresenham / local BFS utilities in `bug_common.rs`.

| name | file | idea |
|---|---|---|
| BFS | `bfs.rs` | offline reference only, not benchmarked |
| Bug0 | `bug0.rs` | greedy dir + right-hand-rule boundary follow; `hit_dist_sq` guard so it eventually leaves concave obstacles |
| Bug1 | `bug1.rs` | classical: circumnavigate, record closest point, return to it. Cycle + progress guarantee (`global_min_dist_sq`) |
| Bug1+LoS | `bug1.rs` | Bug1 with a Bresenham LoS shortcut when goal visible |
| Bug2 | `bug2.rs` | classical m-line follower (incomplete by design) |
| DistBug | `distbug.rs` | leave wall when `d(pos, goal) - F < d_best`, with F = free-space distance along king-direction ray |
| VisBug-21 / -22 | `visbug21.rs`, `visbug22.rs` | jump-along-m-line + LoS shortcut |
| TangentBug | `tangentbug.rs` | pick visible discontinuity (O_i) minimising `d(pos, O_i) + d(O_i, goal)`; leave when `min d(c, goal)` over visible boundary drops below `d_best` |
| BFS+Bug1 | `bfsbug.rs` | local BFS in the 69-cell sensor window first; Bug1 as the completeness backstop |
| Memory+BFS | `mem_bfs.rs` | bounded (500 expansions) BFS over *discovered* cells with optimistic unknowns, `pnb` flat adjacency list (matches production bot), Bug1 fallback |
| Memory+A* | `mem_astar.rs` | same structure as Memory+BFS but with a Chebyshev-heuristic priority queue — same budget buys a longer effective horizon |
| LookaheadBug | `lookahead_bug.rs` | simulate a greedy/wall-follow bug `bug_pos` 6 steps ahead inside the sensor disc, run a 3-iter BFS flood from `bug_pos`, pick the real agent's neighbour that minimises `(penalty, bfs_dist, bug_dist)` |
| LookaheadBug+FullMap | `lookahead_bug.rs` | same algorithm, initialised with all cells discovered |

## Current numbers

68 maps × 100 random start/goal pairs × 1000-iter cap (matches the 2000-round
game limit):

```
algo              n    reach false_un      tle  corr_un   un_tle    conv%     p50     p90     p99    p100
----------------------------------------------------------------------------------------------------
Bug0           6800     6228        0       36        1      535    99.4    1.12    3.20   11.91   79.60
Bug1           6800     6163        0      101      479       57    98.4    2.62    8.74   25.00  163.00
Bug1+LoS       6800     6211        0       53      479       57    99.2    1.84    6.32   16.28   79.60
Bug2           6800     5154     1078       32      519       17    82.3    1.18    3.44   14.44  110.00
DistBug        6800     5741       18      505      451       85    91.7    1.07    2.71   10.11   79.60
VisBug-21      6800     5734      509       21      524       12    91.5    1.20    3.12   11.00   86.45
VisBug-22      6800     6212       36       16      529        7    99.2    1.10    2.49    8.63   72.36
TangentBug     6800     5444      724       96      531        5    86.9    1.25    2.61    8.88   72.36
BFS+Bug1       6800     6116        0      148      526       10    97.6    1.00    2.07    7.25   40.50
Memory+BFS     6800     6251        1       12      508       28    99.8    1.00    1.79    6.16   35.08
Memory+A*      6800     6257        1        6      518       18    99.9    1.00    1.48    3.43   18.39
LookaheadBug   6800     5196        0     1068        0      536    83.0    1.00    1.60    5.09   17.50
LookaheadBug+FullMap 6800  5196     0     1068        0      536    83.0    1.00    1.60    5.09   17.50
```

## Findings

1. **Classical bug algorithms are fragile.** Bug2 is incomplete (1078
   false-unreach). VisBug-21, TangentBug inherit a similar m-line /
   leaving-condition issue and mis-classify hundreds of reachable pairs.
   Bug0 happens to converge often but its p100 is 79× optimal.

2. **Memory makes a huge difference.** Accumulating discovered cells turns
   a local algorithm into a local-planner-on-global-belief. Memory+BFS at a
   500-expansion budget reaches 99.8% convergence with p99 = 6.16×.

3. **Goal-directed expansion strictly dominates uniform BFS at equal
   budget.** Memory+A* (same structure, Chebyshev heuristic, same budget)
   halves p99 (3.43 vs 6.16) and halves p100 (18.39 vs 35.08) vs Memory+BFS.
   That's the current best operating point.

4. **LookaheadBug gives great path quality when it converges but low
   convergence.** It's structurally vision-bounded: the 6-step simulation
   + 3-iter validator BFS cannot reason past the 69-cell disc. On maps where
   the obstacle is larger than the disc, it oscillates and TLEs (1068 TLE
   cases at 1000-iter cap).

5. **"Full map" is a no-op for LookaheadBug.** The algorithm only queries
   passability inside the sensor disc (`in_vision` gates every probe, and
   `sense()` discovers every disc cell at each step). Handing it full map
   knowledge changes no query result. To actually exploit full-map
   information you need an algorithm whose expansion horizon is not disc-
   bounded — that's what Memory+BFS and Memory+A* are.

6. **Budget, not algorithmic cleverness, seems to be the binding
   constraint.** At 500 expansions Memory+A* looks cheap-enough for 2 ms
   Python, and it's already near the BFS ceiling. The remaining gap is
   concentrated in a long tail of maps where even 500 A* expansions don't
   see around the obstacle.

## Running

From the repo root:

```
# viewer
cargo run --release --manifest-path pkg/Cargo.toml -p bugnav-viewer -- <map>

# benchmark (default: 100 pairs/map, 1000 iter cap)
cargo run --release --manifest-path pkg/Cargo.toml -p bugnav-viewer --bin benchmark

# worst-case trials for a specific algorithm
cargo run --release --manifest-path pkg/Cargo.toml -p bugnav-viewer --bin benchmark -- \
    --pairs 100 --iters 1000 --worst Memory+A* --worst-n 10
```

### Benchmark flags

| flag | default | meaning |
|---|---|---|
| `--pairs N` / `-n N` | 100 | random start/goal pairs per map |
| `--iters N` / `-i N` | 1000 | per-trial step cap (matches 2000-round game but allows slack) |
| `--worst ALGO[,ALGO…]` | — | after the summary, print the N worst-ratio trials for each named algorithm |
| `--worst-n K` | 10 | how many to print per `--worst` algo |

## File layout

```
pkg/bugnav/viewer/
├── Cargo.toml
├── README.md
├── assets -> ../../visualiser/viewer/assets   (symlink, sprite atlas)
└── src/
    ├── main.rs                     CLI + eframe::run_native entry
    ├── app.rs                      eframe::App state
    ├── ui.rs                       sidebar + map panel
    ├── render.rs                   snapshot overlay rendering
    ├── grid.rs                     Grid { w, h, walls } + .map26 loader
    ├── pathfinder.rs               Pathfinder trait, Snapshot, AlgoSpec registry,
    │                               offline ground-truth BFS
    ├── bin/benchmark.rs            offline benchmark harness
    └── algorithms/
        ├── mod.rs
        ├── bug_common.rs           shared: DIRS, sensed_cells, wall_follow_step,
        │                           bresenham, local_bfs, dist_sq, has_los, …
        ├── bfs.rs                  reference
        ├── bug0.rs … bug2.rs
        ├── distbug.rs
        ├── visbug21.rs visbug22.rs
        ├── tangentbug.rs
        ├── bfsbug.rs               BFS (local) + Bug1 fallback
        ├── mem_bfs.rs              bounded BFS over discovered cells
        ├── mem_astar.rs            bounded A* over discovered cells
        └── lookahead_bug.rs        bug-simulate ahead, BFS-validate direction
```
