# v1000 overhaul plan

Snapshot of where we are and what's broken / weak. We have a solid core but
several bugs are bleeding econ and attack value. This doc enumerates them in
priority order so we don't lose track when context compacts.

Reference plans:
- `ATTACK_MICRO_PLAN.md` — attack micro tier list (diagonal launcher, proximity
  gate, sentinel drill, etc.)
- This doc — bugs and structural overhaul that block / amplify those attack
  micro changes.

## Status

**Just landed (2026-05-02 session)**

- ✅ Foundry: exclude `downstream_of_foundry` from candidates (commit `992738df`).
- ✅ Gunner: re-enable self-destruct on ammo starvation, gated on no enemy in
  vision (commit `6af55949`).

**Bugs known but not yet fixed**, in rough priority order:

### P0 — bleeding econ every game

#### B1. Turrets count as flow consumers → chains stall

- File: `src/builder/mod.rs::_is_flow_consumer` (l. 1099)
- Symptom: chain `harvester → conv1 → conv2 → turret` has no dangling end.
  Turret accepts 1 stack and stalls; further stacks back up; econ lost.
- Root cause: `_is_flow_consumer` includes Gunner/Sentinel/Breach/Launcher.
  This makes splitters with turret outputs "satisfied" and leaves no admit-
  terrain tile that `_check_dangling` can flag.
- Proposed fix: split into PRIMARY (Conveyor / Splitter / Bridge / Foundry /
  Core) and SECONDARY (turrets). `_splitter_satisfied` requires ≥1 PRIMARY
  output. Any conveyor whose only `out_edges` are SECONDARY consumers must
  trigger a downstream dangling tile so we extend / split around the turret.
- Risk: aggressive — many of our existing chain shapes deliberately end at
  turrets. We need to make sure "extend past turret" doesn't keep paving
  conveyors into a non-existent open tile. Likely safer: reuse the same
  approach as `place_offensive_sentinel` / `clear_enemy_turret` — when we
  place a turret on a dangling tip, we *also* place a splitter on the conveyor
  immediately upstream so flow continues to core. The bug is that we don't
  enforce that invariant globally.
- LOC: 60–120.

#### B2. Skip-ore (sometimes don't claim ore right next to us)

- File: `src/builder/helpers.rs::_pick_ore`
- Symptom: bot is on / next to ore but ore_target stays None.
- Candidate gates that may be wrongly rejecting:
  - `is_reachable_p(pi)` — union-find blocks if cost_grid says INF
  - `dist_sq(pi, core_idx) > econ_radius_sq` — outside econ disc on big maps
  - `claims_by_proximity_p` — friend with shorter Chebyshev claim
  - `harvester_would_contaminate_p` — adjacent friendly conveyor with bad
    flow history
  - `harvester_feed_cardinal_p == None` — no viable feed cardinal
- Action: add a per-gate `log()` so the DEBUG_DUMP scope tree records which
  filter dropped the ore tile, then run vs farlands and decode.
- LOC: ~20 LOC of logging.

#### B3. Foundry placement bug fixed but **needs verification**

- We landed the structural exclusion. Run a debug-dump match on a
  multi-foundry map and confirm F2 is no longer placed downstream of F1.

### P1 — bugs that hurt sometimes

#### B4. First-turn TLE on server

- Symptom: server replays show round-1 spike >2 ms, bot despawns next turn.
- Likely culprits:
  - `post_init` runs `init_pnb_chunk(10000)` until ready — a 50×50 map
    builds a `(52×52)` padded grid of DIR8-neighbour lists; ~22k tiles ×
    8 dirs = ~180k push ops. May exceed 2 ms on cold cache.
  - First `update()` populates `vision_mask` for every tile in nearby_tiles
    AND walks `last_vision` (empty on round 1, fine), but calls
    `idx_of(pos)` for ~60 tiles plus all the cascade work.
  - All cascade paths run hot on turn 1 (no incremental shortcut).
- Action: instrument with TRACE_TLE on hetzner build, run vs intgrah/v55,
  drop the per-section ENTER/EXIT trace. We already have the infra
  (`config::TRACE_TLE`).

#### B5. ~~`is_reachable_p` over-restricts offensive ore~~ **WITHDRAWN**

- `is_reachable_p` is a movement-reachability union-find over passable
  tiles, not a flow-reachability check. Correct as a gate — we shouldn't
  try to claim ore we can't physically walk to. No bug here.

### P2 — gaps in attack/defence micro

These are from `ATTACK_MICRO_PLAN.md` plus new defence findings.

#### B6. No diagonal launcher flank
See `ATTACK_MICRO_PLAN.md` Tier 1A.

#### B7. No proximity gate for attacks
See `ATTACK_MICRO_PLAN.md` Tier 1B. Currently 2–3 bots dogpile a single
harvester while another is unguarded.

#### B8. `stalk_enemy` is pure-follow — no fire / no harass

- File: `src/builder/tasks/defense/stalk_enemy.rs`
- Symptom: stalker walks on top of enemy bot without ever firing on enemy
  infrastructure it's standing on.
- Action: add a "fire on this tile if it's enemy infra and we just stepped
  onto it" supplement, mirroring `fire_on_enemy_tile` but as a side-effect
  of stalking.

#### B9. `patrol_late` gates on `adjacent_to_harvester` non-empty

- File: `src/builder/tasks/defense/patrol_late.rs`
- Symptom: a defender out of vision of any friendly harvester does nothing
  useful (falls through to opportunistic / explore / wander). Mid-game,
  this is the common case for a bot that's wandered.
- Action: drop this gate. Defenders should always patrol their last-seen
  region of our econ.

#### B10. No anti-rush / anti-launcher reactive defence

- Symptom: enemy diagonal launcher placement (the exact thing we proposed
  to do offensively) lands in our half and we don't react with a barrier
  / sentinel placement to deny.
- Action: defensive equivalent of `clear_enemy_turret` but specifically
  for nascent enemy infra in our half (their ore claim, their first
  conveyor on our side).

### P3 — cleanup / structural

- `update/markers.rs` placement still adds rendezvous markers without a
  freshness check — bots converge on stale markers from killed harvesters.
  (Not yet verified — needs replay inspection.)
- `clear_enemy_turret` and `place_offensive_sentinel` overlap in code — one
  is "defensive scope" (closer to our core), the other is "offensive scope"
  (closer to enemy core). Should share the dangling-tip iterator with a
  scope predicate parameter.
- `econ_radius_sq = (0.7 * max_dim)²` may be too small on tiny maps and
  too big on huge maps. Per-template tuning?

## Plan of attack

### Phase 1 — verify the foundry fix and ship more bug fixes

1. Local sweep n=104 maps: foundry-fixed v1000 vs pre-foundry-fix snapshot.
   Confirm we don't regress and ideally see uplift on multi-foundry maps.
2. Land **B1 (turret-as-sink)** as the next P0 — biggest single-bug econ
   leak observed.
3. Add per-gate logging to `_pick_ore` for **B2**, run debug_dump match
   on farlands, decode at a turn where bots-on-ore didn't claim.

### Phase 2 — verify with debug_dump on farlands

1. `python scripts/b.py sync && python scripts/b.py build drewfett_v1000 --debug-dump 1`
2. `python scripts/b.py run drewfett_v1000 drewfett_v1000 -m far_lands -r 800`
3. Pull replay; for each suspected bug:
   - **Foundry**: open in visualiser, confirm no F2 placed downstream of F1.
   - **Skip ore**: `scripts/dump_decode.py replays/b/<file> <bot_id> <turn>`
     on a turn where a Free bot is on/near ore. Look for `_pick_ore`
     gate-fire log lines.
   - **First-turn TLE**: open turn-1 scope tree; identify which section
     dominates the budget.

### Phase 3 — attack micro

After P0/P1 land and verify, follow `ATTACK_MICRO_PLAN.md` Tier 1+2:
- A. Diagonal launcher flank (~150 LOC)
- B. Proximity gate (~20 LOC)
- D. Buddy / converge attacks (~80 LOC)

### Phase 4 — defence overhaul

Mirror `ATTACK_MICRO_PLAN.md` for defence, covering B8 / B9 / B10 above
plus the markers / anti-clumping patterns from the attack plan applied
defensively.

## Out of scope (this overhaul)

- Replacing intgrah's chain-routing with a fresh design.
- Removing the role split (Defender / Free) — current ratio works.
- Markers > 8 tags. WS-1 already specced.

## Snapshot of where we are
- Best on actual ladder: 0.3% TLE / 11.1% > 1.5 ms (P5-starts variant).
  Some tail TLEs remain — see B4.
- v1000 vs intgrah/v56 native sweep ~73% (zero resigns) as of last commit.
