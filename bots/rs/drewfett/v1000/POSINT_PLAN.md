# PosInt rewrite — drewfett v1000

## Why

CPython spends a lot of time on Position-class operations:
- `Position(x, y)` constructor — ~200ns/call
- `pos.x` / `pos.y` LOAD_ATTR — ~50ns each
- `pos.add(d)` — ~280ns even with our monkey-patch (was 930ns)
- `pos.distance_squared(q)` — ~150ns (method call)
- `builder.in_bounds(pos)` — ~200ns (method call → arithmetic)
- `builder.idx(pos)` — ~250ns (method call → mul + add)

Per turn the bot does **thousands** of these operations across vision,
ore picking, foundry-target search, neighbor walks. After all our
mechanical optimizations settlement still sits at ~1.36ms p50 with
30-46% of 64-turn windows hitting the 2ms TLE cap on AWS Linux ARM
(ladder spec).

Adgato's `bots/adgato/sprint4ax` (pure Python) demonstrates the lever:
represent every tile as a single `int` index `idx = y * stride + x`,
neighbours as integer addition `idx + d` where `d ∈ {-stride, ±1, ±stride±1}`,
and look up squared distance / Manhattan / Chebyshev / in-bounds via
precomputed tables indexed by `p - q + OFFSET`.

Per-op savings (conservative):
| op | Position-based | PosInt | Δ per call |
|---|---|---|---|
| neighbour walk `pos.add(d)` | ~280ns | `p + d` ~10ns | -270ns |
| `Position(x, y)` ctor | ~200ns | (no ctor) | -200ns |
| `pos.distance_squared(q)` | ~150ns | `dist_sq[p - q + OFF]` ~50ns | -100ns |
| `builder.in_bounds(pos)` | ~200ns | `valid[p]` ~80ns | -120ns |
| `builder.idx(pos)` | ~250ns | identity | -250ns |
| `pos.y * MAX_WIDTH + pos.x` | ~150ns | identity | -150ns |

A typical hot-loop iteration (60 tiles × 8 neighbours × ~5 of these
ops) saves on the order of **0.5–1ms per turn** if applied
comprehensively. That's the bracket we need to fall under the 2ms TLE
cap.

## Constraint

Behaviour MUST match the current Python version exactly. This is a
data-layout change, not algorithmic. Same logic, same per-call
behaviour, same gameplay. Same cambc engine API at the boundary.

## Design

### `PosInt` representation

**Following sprint4ax exactly** — `STRIDE = 2 * MAX_WIDTH = 100`, NOT `MAX_WIDTH`.
The 2× stride is essential: with stride=50, two different `(dy, dx)` pairs can
alias onto the same `p - q` value (e.g. `dy=1, dx=-49` → 1 vs `dy=0, dx=1` → 1),
breaking the dist-table lookup. Stride=100 guarantees `|dx| < stride/2` so
`p - q` uniquely determines `(dy, dx)`. Half the per-tile array slots
(`x ∈ [50, 99]`) are unused "holes" and stay at their initial value forever.

```rust
pub type PosInt = i32;
pub const STRIDE: i32 = 2 * MAX_WIDTH as i32;       // 100
pub const BOUND_RANGE: usize = STRIDE as usize * MAX_WIDTH; // 5000
pub const MAX_DELTA: i32 = (MAX_WIDTH as i32 - 1) * STRIDE + (MAX_WIDTH as i32 - 1); // 4949
pub const DIST_OFFSET: i32 = MAX_DELTA;             // 4949
pub const DIST_TABLE_LEN: usize = 2 * MAX_DELTA as usize + 1; // 9899
```

- `idx_of(pos: Position) -> PosInt = pos.y * STRIDE + pos.x`
- `pos_of(idx: PosInt) -> Position = Position { x: idx % STRIDE, y: idx / STRIDE }`
- DIR4 deltas: `[-100, 1, 100, -1]` (N, E, S, W)
- DIR8 deltas: `[-100, -99, 1, 101, 100, 99, -1, -101]`

### Precomputed tables on Builder

```rust
pub dist_sq:       Vec<i32>,   // length DIST_TABLE_LEN; squared euclidean
pub manhat:        Vec<i32>,   // length DIST_TABLE_LEN; manhattan
pub chebyshev:     Vec<i32>,   // length DIST_TABLE_LEN; chebyshev
pub posint_valid:  Vec<u8>,    // length BOUND_RANGE; 1 iff in-bounds
```

Distance tables are populated **eagerly in `Builder::new()`** for the worst-case
50×50 grid (sprint4ax does this in `__init__`). `posint_valid` requires the
real map dims so it's filled in once they're known (`resolve_my_core` /
`init_world` analog). Smaller maps are a strict subset of the 50×50 range so
no lazy fallback is needed.

### Boundary conversion policy

- **cambc engine API** (`ct.get_*`, `ct.move`, `ct.build_*`) takes/returns
  `Position`. Convert at the boundary using `idx_of` / `pos_of`.
- **Internal state, helpers, hot loops** — `PosInt` everywhere.
- **Friendly to readers**: `idx_of(pos)` and `pos_of(idx)` are visibly
  named so it's obvious where conversion happens.

## Phasing

Each phase is independently shippable. After every phase: build native,
translate, run dna+settlement on AWS, verify outcomes match the
pre-rewrite baseline (dna win at turn 482, settlement 504 vs 907
buildings).

### Phase 1 — Infrastructure (no behaviour change)

- Add `PosInt` typedef, helpers, DIR4_INT / DIR8_INT constants in a new
  `src/util/posint.rs` module.
- Add `dist_sq`, `manhat`, `chebyshev`, `posint_valid` fields to Builder
  (and any other entity types that need them; sprint4ax has only Builder).
- Populate `dist_sq` / `manhat` / `chebyshev` eagerly in `Builder::new()` —
  the grid is fixed-size (50×50) so no map dims needed.
- Populate `posint_valid` in the existing first-turn init hook
  (`init_world` / `resolve_my_core`), which has `ct.get_map_width/height`.
- Bot still uses Position everywhere — tables exist but unused.
- Verify: bot plays identically (dna p50, settlement p50 unchanged within noise).

### Phase 2 — Convert visible_* typed lists to PosInt

- `visible_ti_ore_idx: Vec<PosInt>`, `visible_ax_ore_idx`,
  `visible_harvesters_idx`. Populate during `update_vision` with
  `idx_of(pos)`.
- Update consumers: `_pick_ore` family, `update_ore_denial`,
  `update_map_econ` Pass 1 — iterate the int lists directly.
- Per-tile work uses `env[p]`, `building_kind[p]`, `building_team[p]`
  (all already PosInt-indexed arrays — no change to those).
- Inner DIR loops use `p + DIR_INT[i]` and `dist_sq[p - q + OFF]`.
- Convert back to Position only when calling cambc (e.g. `try_build`,
  inserting into engine-typed sets).

### Phase 3 — Convert hot loop bodies

- `update_vision` inner DIR8 expansion (currently uses `nx, ny` ints
  via DIR8_DELTA — easy port to `p + DIR8_INT[i]`).
- `harvester_would_contaminate`, `harvester_feed_cardinal` (helpers.rs)
  — DIR8/DIR4 loops, lots of `pos.add` calls.
- `update_map_econ` Pass 1 inner loops.
- `update_foundry_target` `_foundry_local_ok` and `_is_zero_length_foundry_spot`.
- `econ_astar.search_unidirectional` already uses `node_i: i32` for the
  inner loop (mostly PosInt-equivalent). Verify and tighten.

### Phase 4 — Convert state field types

This is the biggest change. Fields in Builder/UnitState that hold
Position become PosInt-typed:

- `HashSet<Position>` → `HashSet<PosInt>` for: `adjacent_to_harvester`,
  `adjacent_to_unconnected_harvester`, `ti_harvester_adjacent`,
  `ax_harvester_adjacent`, `reaches_core`, `reaches_foundry`,
  `ti_upstream`, `ax_upstream`, `upstream_of_dangling`,
  `congested_junctions`, `upstream_of_congestion`, `my_foundries`,
  `my_harvesters`, `is_multi_input`, `junctions`,
  `adjacent_to_enemy_launcher`, `enemy_turret_ray_tiles`,
  `friendly_turret_ray_tiles`, `deny_ore_neighbours`, `dangling_set`,
  `unreachable_dangling`.
- `HashMap<Position, X>` → `HashMap<PosInt, X>` for: `attack_tile_blacklist`,
  `saw_ore_claim`, `saw_threat_at`.
- `Vec<Position>` already-PosInt-indexed (e.g. `nearby_tiles`,
  `nearby_buildings`, `healable_buildings`, `core_edges`).
  Add parallel `Vec<PosInt>` versions populated alongside.
- Engine-boundary fields (`enemy_bots: HashSet<Position>`,
  `friendly_bots`, `all_bots`) — KEEP as Position because the engine
  fills them and other code expects Position. Or convert at boundary.
  Decide case-by-case.

### Phase 5 — Convert task signatures

Tasks (`builder/tasks/*.rs`) currently take/return `Position`. Convert
to `PosInt` internally; convert at engine boundaries (when calling
`ct.move(d)`, `ct.build_*(pos)`, etc.).

This is the most invasive phase touching many files but each task is
self-contained.

### Phase 6 — Bug2 planner / nav

`builder/algorithms/{nav, bug2_planner, reachability}.rs` already use
`i32` indices for the most part. Ensure consistency, eliminate residual
`Position`.

## Risk

The big risk is silently wrong gameplay — converting `Position` to
`PosInt` and back at every boundary creates many sites where a bug can
swap x/y, drop the `+ STRIDE` term, or mis-index. Mitigations:

- **Tight test loop**: after every phase, run dna and settlement on AWS,
  check Winner, Buildings, Units match the pre-rewrite outcome
  exactly. Any divergence = regression to debug before next phase.
- **Type-driven**: distinguish `PosInt` from `i32` if pyrust allows
  newtype. If not, name boundary functions clearly (`idx_of`, `pos_of`)
  so review can spot conversion errors.
- **Native build first**: every change builds clean natively (Rust's
  type checker catches half the swap errors) BEFORE translating.

## Stop conditions

After each phase, decide:
- If turn p50 dropped meaningfully (~10%+ phase-over-phase): continue.
- If outcomes regressed: revert and debug.
- If we've cleared TLE budget on settlement (<5% windows >2ms): we
  can stop with margin.

## Estimated effort

- Phase 1: 1-2 hours (mechanical, no behaviour change).
- Phase 2: 2-3 hours (consumers in helpers.rs, turrets.rs, econ.rs).
- Phase 3: 3-4 hours (multiple helper files).
- Phase 4: 4-6 hours (state field renames, careful audit).
- Phase 5: 4-6 hours (every task file).
- Phase 6: 1-2 hours (algorithms tighten-up).

Total full rewrite: ~16-23 hours of focused work. The early phases (1-3)
are the cheapest and probably already break the 2ms barrier on most
maps; phases 4-6 are diminishing returns and only worth doing if 1-3
isn't enough.

---

## Implementation log (post-rewrite)

### What landed

- Phase 1: dist tables + posint_valid scaffold (additive, parity-clean)
- Phase 2a: per-tile arrays widened to BOUND_RANGE = 5000 (stride=100 layout)
- Phase 2b: `visible_*` ore/harvester lists → Vec<PosInt>
- Phase 3: hot DIR-loop bodies use PosInt arithmetic + posint_valid bounds check
- Phase 4: `HashSet<Position>` → `HashSet<PosInt>` for ~20 fields, `HashMap<Position, X>` → `HashMap<PosInt, X>` for 3 fields
- pos_of cache: alias prelude pre-builds `_POS_TABLE` of 5000 Positions, `Position.lookup` bound to its `__getitem__`
- `_pick_ore` wired to use `dist_sq[my_idx - pi + DIST_OFFSET]` instead of `pos.distance_squared(q)`

### What didn't pan out (yet)

**The other 56+ `distance_squared` callsites are NOT wired** to use the dist tables. They still take Position and call the native `.distance_squared` method. Wiring them requires either Phase 5 (push PosInt through function signatures) or accepting a marginal ~40ns/call win at sites that pay 2× idx_of conversion overhead.

### AWS Graviton3 (m7g.4xlarge) settlement self-vs-self benchmark, --tle 0

| variant                             | windows | p50    | p95    | max    | TLE%   |
|-------------------------------------|---------|--------|--------|--------|--------|
| Pre-PosInt (gc on)                  | 1542    | 1065µs | 1558µs | 1730µs | 37.9%  |
| Pre-PosInt (gc OFF)                 | 1542    | 1051µs | 1538µs | 1709µs | 36.2%  |
| Phases 1-3 + cache (gc on)          | 1265    | 1245µs | 1662µs | 1922µs | 47.3%  |
| Phases 1-3 + cache (gc OFF)         | 1220    | 1231µs | 1652µs | 1904µs | 46.8%  |
| Phase 4 + cache (gc on)             | 1265    | 1238µs | 1664µs | 1916µs | 47.4%  |
| Phase 4 + cache (gc OFF)            | 1265    | 1242µs | 1664µs | 1936µs | 47.3%  |

PosInt is **slower** on AWS Graviton even with the pos_of cache. GC was not
the cause (disabling gc improves both variants by ~1-2% only).

### Mac M-series benchmark

On Mac the same code shows the OPPOSITE — Phases 1-3 cut p50 from ~1336µs
to 660µs (-50%) and TLE from ~29% to 6.7%. Mac was misleading; AWS is
ladder-spec hardware.

### Hypothesis for the AWS regression

Phase 2a doubled per-tile array allocations from 2500→5000 entries. Each
array (env, building_kind, hp, etc.) goes from ~70KB → ~140KB. Graviton3
has 64KB L1 / 1MB L2 per core; doubled arrays spill from L1, hurting
iterations. M-series Mac has a larger L1 so doesn't suffer the same way.

The PosInt arithmetic savings don't recover the cache cost.

### Verdict

Reverting PosInt may be the right call. Pre-PosInt at 1051µs / 36% TLE is
strictly better than every PosInt variant on AWS. The Mac wins didn't
transfer.

The actual ladder server (different hardware again) is the next data
point. If even the ladder server shows a regression, revert.
