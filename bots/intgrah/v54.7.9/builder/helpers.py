from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingArmouredConveyor,
    BuildingBarrier,
    BuildingBridge,
    BuildingConveyor,
    BuildingCore,
    BuildingFoundry,
    BuildingHarvester,
    BuildingMarker,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import Controller, Direction, EntityType, Environment, Position, ResourceType
from util.constants import BASE_COST, INF, MAX_WIDTH
from util.debug import Scope
from util.debug import debug as log
from util.directions import DIR4, DIR8
from util.metrics import claims_by_proximity, manhattan

if TYPE_CHECKING:
    from builder import Builder


def make_move(self: Builder, ct: Controller, target: Position) -> bool:
    """Return True iff this call actually issued a move. 'Already at target'
    and 'no plan' both return False — neither advances the builder, so the
    caller shouldn't treat the turn as productive.

    Uses bug2-bounded planner with dp_step path-follower. Plan state lives
    on `self.bugnav` and persists across turns for the same goal.
    """
    if self.my_pos == target:
        log("make_move: already on target {target}", target=target)
        return False
    next_move = self.bugnav.step(self, target)
    if next_move is None:
        # Bugnav can't find a plan that progresses (typically two builders
        # head-butting in a corridor — both planners route through each
        # other's tile). Take a random unblocked step to break the
        # deadlock; one builder yielding lets the other progress.
        if move_random(self, ct):
            log(
                "make_move: bugnav stuck, took random step {start}->{target}",
                start=self.my_pos,
                target=target,
            )
            return True
        log(
            "make_move: FAILED {start}->{target} (bugnav: no plan, random step also blocked)",
            start=self.my_pos,
            target=target,
        )
        return False
    log(
        "make_move: bugnav {start}->{target} step {next}",
        start=self.my_pos,
        target=target,
        next=next_move,
    )
    return try_move_with_road(self, ct, next_move)


def try_move_dir(ct: Controller, d: Direction) -> bool:
    if ct.can_move(d):
        log("try_move_dir: moving {dir}", dir=d)
        ct.move(d)
        return True
    return False


def try_move_to(self: Builder, ct: Controller, target_pos: Position) -> bool:
    d = self.my_pos.direction_to(target_pos)
    if ct.can_move(d):
        log(
            "try_move_to: {start}->{target} dir {dir}",
            start=self.my_pos,
            target=target_pos,
            dir=d,
        )
        dx = target_pos.x - self.my_pos.x
        dy = target_pos.y - self.my_pos.y
        self.explore_heading = (
            (dx > 0) - (dx < 0),
            (dy > 0) - (dy < 0),
        )
        ct.move(d)
        return True
    return False


def try_move_with_road(self: Builder, ct: Controller, target_pos: Position) -> bool:
    if self.get_cost(target_pos) > 1 and ct.can_build_road(target_pos):
        log(
            "try_move_with_road: paving road at {target} (cost={cost} > 1)",
            target=target_pos,
            cost=self.get_cost(target_pos),
        )
        ct.build_road(target_pos)
    return try_move_to(self, ct, target_pos)


def try_attack(ct: Controller, pos: Position) -> bool:
    if ct.can_fire(pos):
        log("try_attack: firing on {pos}", pos=pos)
        ct.fire(pos)
        return True
    return False


def ti_needed(self: Builder, etype: EntityType) -> int:
    base = BASE_COST[etype][0]
    scale = self.scale
    foundry = (
        int(BASE_COST[EntityType.FOUNDRY][0] * scale)
        if self.round >= 500 and self.ax_harvester_adjacent
        else 0
    )
    """Once we've committed to an Ax economy (round >= 500 with at least
    one Ax harvester visible), keep enough Ti banked for a foundry so
    other builders can't drain the colony before it's placed.
    """
    match etype:
        case EntityType.FOUNDRY:
            return int(base * scale)
        case EntityType.HARVESTER:
            reserve = 10 if self.round < 35 else 20
            return int((base + reserve) * (1 + scale)) + foundry
        case EntityType.LAUNCHER:
            return int((base + 15) * (1 + scale)) + foundry
        case EntityType.SENTINEL | EntityType.GUNNER:
            return int(base * (1 + scale)) + foundry
        case _:
            return int(base * scale) + foundry


def can_afford(self: Builder, etype: EntityType) -> bool:
    return self.ti >= ti_needed(self, etype)


def required_ti_for_ore_claim(
    self: Builder,
    ore_pos: Position,
    sink_pos: Position,
) -> int:
    """Heuristic Ti cost to walk to `ore_pos`, place a harvester, ring
    it inward (worst case 3 sides), and route the chain back to
    `sink_pos`. Used as an affordability gate when picking new ore
    targets — a builder shouldn't commit to ore it can't realistically
    deliver from. Cost mix assumes ~70% conveyor / ~30% bridge along
    the chain (bridges hop r²<=9, ~3 tiles per build).

    Distances are Manhattan (roads/conveyors connect cardinally).
    Crowding/saturation penalty is applied at the leniency level
    (see `ore_claim_leniency`).
    """
    s = self.scale
    h_cost = int(BASE_COST[EntityType.HARVESTER][0] * (1 + s))
    c_cost = int(BASE_COST[EntityType.CONVEYOR][0] * s)
    b_cost = int(BASE_COST[EntityType.BRIDGE][0] * s)
    r_cost = max(int(BASE_COST[EntityType.ROAD][0] * s), 1)
    d_pos = manhattan(self.my_pos, ore_pos)
    d_sink = manhattan(ore_pos, sink_pos)
    walk_cost = d_pos * r_cost
    ring_cost = 3 * c_cost
    chain_cost = int(d_sink * (0.7 * c_cost + 0.3 * b_cost / 3))
    return h_cost + ring_cost + chain_cost + walk_cost


def ore_claim_leniency(self: Builder) -> float:
    """Leniency multiplier on `required_ti_for_ore_claim`. Decaying
    exponential in friendly harvester count: starts at 0.8 with no
    harvesters (commit to a claim with only 80% of the estimated cost
    in hand — incoming income covers the rest), asymptotes to 2.4
    once the colony is fully built up (trunk saturated, routes
    detour, want >2x the optimistic estimate before risking a
    distant claim). Harvester-count rather than round number so a
    slow start delays the gate until we've actually built up.

        n=0   → 0.80
        n=4   → 1.10
        n=8   → 1.27
        n=16  → 1.66
        n=32  → 2.07
        n→∞   → 2.40
    """
    n = len(self.my_harvesters)
    return 0.8 + 1.6 * (1 - 0.95**n)


def can_afford_ore_claim(
    self: Builder,
    ore_pos: Position,
    sink_pos: Position,
) -> bool:
    return self.ti >= int(
        required_ti_for_ore_claim(self, ore_pos, sink_pos) * ore_claim_leniency(self),
    )


def try_place(
    self: Builder,
    ct: Controller,
    etype: EntityType,
    pos: Position,
    extra: Direction | Position | None = None,
    *,
    destroy: bool = True,
) -> bool:
    if not can_afford(self, etype):
        log(
            "try_place: cannot afford {etype} at {pos} "
            "(have {have}, need {need}; base {base}, scale {scale:.2f})",
            etype=etype,
            pos=pos,
            have=self.ti,
            need=ti_needed(self, etype),
            base=BASE_COST[etype][0],
            scale=self.scale,
        )
        return False
    if destroy and ct.can_destroy(pos):
        log(
            "try_place: destroying existing building at {pos} for {etype}",
            pos=pos,
            etype=etype,
        )
        ct.destroy(pos)
        self.apply_local_destroy(pos)
    if ct.can_build(etype, pos, extra):
        log(
            "try_place: built {etype} at {pos} extra={extra} (ti={ti}, scale={scale:.2f})",
            etype=etype,
            pos=pos,
            extra=extra,
            ti=self.ti,
            scale=self.scale,
        )
        ct.build(etype, pos, extra)
        return True
    log(
        "try_place: controller rejected {etype} at {pos} extra={extra} (can_build False)",
        etype=etype,
        pos=pos,
        extra=extra,
    )
    return False


def trace_downstream(
    self: Builder,
    start_pos: Position,
    target_head: Position | None,
    path: list[Position] | None = None,
) -> list[Position]:
    if path is None:
        path = []
    current_pos = start_pos
    while True:
        path.append(current_pos)
        bld = self.get_building(current_pos)
        match bld:
            case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
                current_pos = current_pos.add(d)
            case BuildingSplitter(direction=d):
                for sd in DIR4:
                    if sd == d.opposite():
                        continue
                    new_pos = current_pos.add(sd)
                    if target_head:
                        new_path = trace_downstream(
                            self,
                            new_pos,
                            target_head,
                            path=path.copy(),
                        )
                        if new_path and target_head in new_path:
                            return new_path
                    elif self.get_building(new_pos) is None:
                        path.append(new_pos)
                        return path
                current_pos = current_pos.add(d)
            case BuildingBridge(target=t):
                current_pos = t
            case _:
                break
        if current_pos in path:
            break
    return path


def try_heal(
    self: Builder,
    ct: Controller,
    position: Position,
    *,
    conserve_ti: bool = True,
) -> bool:
    if conserve_ti and self.repair_pos is not None:
        i = self.idx(self.repair_pos)
        if not self.buildings[i] or self.hp[i] > self.max_hp[i] - 4:
            return False
    if ct.can_heal(position):
        log("try_heal: healing {pos}", pos=position)
        ct.heal(position)
        return True
    return False


def move_random(self: Builder, ct: Controller) -> bool:
    dir8 = DIR8.copy()
    self.rng.shuffle(dir8)
    for direction in dir8:
        if ct.can_move(direction):
            ct.move(direction)
            return True
    return False


def trace_upstream(self: Builder, position: Position) -> list[Position]:
    path: list[Position] = []
    feeders = [position]
    while feeders:
        position = feeders[0]
        feeders = self.get_in_edges(position)
        if position in path:
            break
        path.append(position)
    return path


def ore_available(self: Builder, pos: Position) -> bool:
    b = self.get_building(pos)
    if b is not None:
        if isinstance(b, BuildingRoad | BuildingMarker | BuildingBarrier) or (
            isinstance(
                b,
                BuildingConveyor | BuildingArmouredConveyor,
            )
            and is_inward_guard(self, pos)
        ):
            pass
        else:
            return False
    return not (pos in self.all_bots and self.all_bots[pos] != self.my_id)


def harvester_feed_cardinal(self: Builder, ore_pos: Position) -> Position | None:
    """The cardinal of `ore_pos` chosen as the future flow-feed slot —
    the empty cardinal closest to the relevant sink. Reserved per
    harvester so the harvester always has at least one consumer side.

    Sink direction is bisector-aware: harvesters on our side feed back
    toward `ti_sink` / `my_core`. Harvesters on the enemy side
    (offensive) feed FORWARD toward `enemy_core`, so the gap left in
    the surrounding barrier ring opens toward the push, not back home.

    Returns None if every cardinal already hosts a flow consumer or the
    builder, or if no sink is known. Excludes the builder's own tile
    (transient: the builder will step off; that tile may become the
    feed too, but it's already an I/O slot regardless of sink choice).
    """
    if on_enemy_side(self, ore_pos):
        sink = self.en_core_guess if self.symmetry is not None else None
    else:
        sink = self.ti_sink if self.ti_sink is not None else self.my_core
    if sink is None:
        log(
            "harvester_feed_cardinal({ore}): no sink — symmetry unresolved",
            ore=ore_pos,
        )
        return None
    # Two-tier preference:
    #   tier 1: an existing outward flow consumer adjacent to the ore
    #           IS the harvester's actual feed — bridges (omnidirectional)
    #           and conveyors/splitters whose direction points AWAY from
    #           the ore. The builder steps off onto these (walkable),
    #           and the chain extension picks up from there.
    #   tier 2: an unbuilt cardinal where we'll later place a flow
    #           consumer — empty terrain, friendly road, marker.
    # Walls / harvesters / foundries / cores / barriers / inward-pointing
    # conveyors are always rejected.
    tier1: list[Position] = []
    tier2: list[Position] = []
    classification: dict[Position, str] = {}
    for d in DIR4:
        c = ore_pos.add(d)
        if not self.in_bounds(c):
            continue
        if c == self.my_pos:
            classification[c] = "my_pos"
            continue
        if self.get_env(c) == Environment.WALL:
            classification[c] = "wall"
            continue
        b = self.get_building(c)
        if (
            isinstance(
                b,
                BuildingBridge | BuildingConveyor | BuildingArmouredConveyor | BuildingSplitter,
            )
            and b.team != self.my_team
        ):
            # Enemy transports never feed our chain — their flow goes
            # somewhere we don't control.
            classification[c] = "enemy_transport"
            continue
        if isinstance(b, BuildingBridge):
            # Inward iff the bridge would deliver its stack back into the
            # harvester tile. ore_pos is a harvester — its raw output is
            # destroyed there.
            if b.target == ore_pos:
                classification[c] = "inward_guard: bridge target == ore"
                continue
            tier1.append(c)
            classification[c] = "tier1: bridge"
            continue
        if isinstance(b, BuildingConveyor | BuildingArmouredConveyor):
            # 1 output (along `direction`), 3 inputs. Inward iff its
            # output points at the ore.
            if c.add(b.direction) == ore_pos:
                classification[c] = "inward_guard: conveyor output -> ore"
                continue
            tier1.append(c)
            classification[c] = "tier1: outward conveyor"
            continue
        if isinstance(b, BuildingSplitter):
            # Splitter has 3 outputs (direction, +90°, -90°) and 1 input
            # from the back (opposite of direction). Outward iff the back
            # faces the ore — only then does the splitter accept the
            # harvester's output AND keep all 3 outputs pointing away.
            if c.add(b.direction.opposite()) == ore_pos:
                tier1.append(c)
                classification[c] = "tier1: outward splitter"
            else:
                classification[c] = "inward_guard: splitter back not -> ore"
            continue
        if isinstance(
            b,
            BuildingFoundry | BuildingCore | BuildingHarvester | BuildingBarrier,
        ):
            classification[c] = type(b).__name__
            continue
        # Escape check (tier 2 only): when the builder steps off the
        # ore onto c, the harvester sits on ore_pos. The builder must
        # be able to move to at least one passable tile in c's
        # U shape — top (across from ore_pos), left/right perp, and
        # left/right far-diagonal corners — otherwise trapped.
        # Same U shape as the barrier-vs-conveyor heuristic.
        d_away = ore_pos.direction_to(c)
        u_shape = (
            c.add(d_away),
            c.add(d_away.rotate_left().rotate_left()),
            c.add(d_away.rotate_right().rotate_right()),
            c.add(d_away.rotate_left()),
            c.add(d_away.rotate_right()),
        )
        has_escape = any(self.in_bounds(p) and self.is_passable(p) for p in u_shape)
        if not has_escape:
            classification[c] = "no_escape"
            continue
        tier2.append(c)
        classification[c] = "tier2: " + (type(b).__name__ if b is not None else "empty")

    chosen: Position | None = None
    chosen_tier = "none"
    if tier1:
        chosen = min(tier1, key=lambda c: c.distance_squared(sink))
        chosen_tier = "tier1"
    elif tier2:
        chosen = min(tier2, key=lambda c: c.distance_squared(sink))
        chosen_tier = "tier2"

    del chosen_tier  # Was used for debugging

    # Verbose per-cardinal breakdown only when no feed was found —
    # that's the diagnostic case. When feed is chosen, a single
    # summary line is enough.
    if chosen is None:
        with Scope(f"feed_pick_{ore_pos.x}_{ore_pos.y}"):
            log("feed_pick({ore}): NONE", ore=ore_pos)
            for d in DIR4:
                c = ore_pos.add(d)
                if not self.in_bounds(c):
                    continue
                log("  {c}: {status}", c=c, status=classification.get(c, "?"))

    return chosen


def harvester_io_cardinals(self: Builder, ore_pos: Position) -> set[Position]:
    """Cardinals of `ore_pos` that must NOT be barriered: they are (or
    will become) the harvester's flow input/output side.

    Excluded:
    - The cardinal already hosts a friendly transport (conveyor / armoured
      conveyor / splitter / bridge), foundry, core, or another harvester
      — already a flow path or blocked by a sibling harvester.
    - The builder's own current tile (will become the chain feed when
      the builder steps off the ore).
    - The cardinal returned by `harvester_feed_cardinal` (chosen feed
      direction toward the sink).
    """
    cardinals = [ore_pos.add(d) for d in DIR4 if self.in_bounds(ore_pos.add(d))]
    reserved: set[Position] = set()
    for c in cardinals:
        if c == self.my_pos:
            reserved.add(c)
            continue
        b = self.get_building(c)
        if isinstance(
            b,
            BuildingConveyor
            | BuildingArmouredConveyor
            | BuildingSplitter
            | BuildingBridge
            | BuildingFoundry
            | BuildingCore
            | BuildingHarvester,
        ):
            reserved.add(c)

    feed = harvester_feed_cardinal(self, ore_pos)
    if feed is not None:
        reserved.add(feed)
    return reserved


def harvester_barrier_saturated(self: Builder, ore_pos: Position) -> bool:
    """True iff at least 3 of `ore_pos`'s 4 in-bounds cardinals already
    host a barrier. Used to prevent placing a 4th barrier and sealing
    the harvester off — different builders may compute different feed
    cardinals and disagree on which side to leave open, so each
    barrier-placement site must independently refuse to fill the last
    open cardinal.
    """
    barriers = 0
    for d in DIR4:
        c = ore_pos.add(d)
        if not self.in_bounds(c):
            continue
        if isinstance(self.get_building(c), BuildingBarrier):
            barriers += 1
    return barriers >= 3


def pick_ore_target(self: Builder) -> Position | None:
    return _pick_ore(self, Environment.ORE_TITANIUM)


def pick_ax_ore_target(self: Builder) -> Position | None:
    return _pick_ore(self, Environment.ORE_AXIONITE)


def pick_offensive_ti_ore_target(self: Builder) -> Position | None:
    """Pick an enemy-side Ti ore tile (more than r²=20 closer to enemy
    core than to ours) for an offensive harvester. Requires symmetry to
    be resolved; returns None otherwise.
    """
    if self.symmetry is None:
        return None
    enemy_core = self.en_core_guess
    best_target = None
    min_dist = INF
    for pos in self.nearby_tiles:
        if self.get_env(pos) != Environment.ORE_TITANIUM:
            continue
        match self.get_building(pos):
            case BuildingHarvester():
                continue
            case None | BuildingRoad() | BuildingMarker() | BuildingBarrier():
                pass
            case BuildingConveyor() | BuildingArmouredConveyor():
                if not is_inward_guard(self, pos):
                    continue
            case _:
                continue
        if not self.is_reachable(pos):
            continue
        d = self.my_pos.distance_squared(pos)
        if not ore_available(self, pos):
            continue
        if (
            pos.distance_squared(enemy_core)
            >= pos.distance_squared(self.my_core) - self.bisector_margin_r2
        ):
            continue
        if harvester_would_contaminate(self, pos):
            continue
        if not claims_by_proximity(
            self.my_pos,
            self.my_id,
            pos,
            (
                (fb_pos, fb_id)
                for fb_pos, fb_id in self.all_bots.items()
                if fb_id != self.my_id and fb_pos in self.friendly_bots
            ),
        ):
            continue
        if d < min_dist:
            min_dist = d
            best_target = pos
    return best_target


def harvester_would_contaminate(self: Builder, pos: Position) -> bool:
    """True if placing a harvester on `pos` would leak the ore into an
    opposite-resource transport chain adjacent to it. A Ti harvester dumps
    titanium into every cardinal neighbour, which is bad if any neighbour
    is a friendly conveyor/bridge/splitter/armoured-conveyor that carries
    (or will carry) raw/refined axionite — and vice versa for Ax.

    Combines two checks so a vision-limited builder doesn't miss a known
    contamination:
    - Structural: the neighbour's upstream tree reaches a harvester on a
      bad-resource ore tile.
    - Empirical: the neighbour's flow_history shows a bad resource stack
      any time in the last 8 observed ticks.

    Exception for Ax ore: if exactly one cardinal neighbour is a pure
    friendly `BuildingConveyor` carrying Ti and there are NO heavy hostile
    neighbours (armoured / bridge / splitter), allow placement. That Ti
    conveyor is the designated foundry spot — the `build_foundry` task
    will replace it with a foundry once the zero-length Ax chain
    connects.
    """
    ore_env = self.get_env(pos)
    if ore_env == Environment.ORE_TITANIUM:
        bad_upstream = self.ax_upstream
        bad_flows = {ResourceType.RAW_AXIONITE, ResourceType.REFINED_AXIONITE}
    elif ore_env == Environment.ORE_AXIONITE:
        bad_upstream = self.ti_upstream
        bad_flows = {ResourceType.TITANIUM}
    else:
        return False
    pure_ti_conveyor_count = 0
    heavy_hostile_count = 0
    hostile_found = False
    for d in DIR4:
        n = pos.add(d)
        if not self.in_bounds(n):
            continue
        b = self.get_building(n)
        if not isinstance(
            b,
            BuildingConveyor
            | BuildingArmouredConveyor
            | BuildingSplitter
            | BuildingBridge,
        ):
            continue
        if b.team != self.my_team:
            continue
        ni = n.y * MAX_WIDTH + n.x
        is_bad = n in bad_upstream or any(
            r in bad_flows for r, _rid in self.flow_history[ni]
        )
        if not is_bad:
            continue
        hostile_found = True
        if ore_env == Environment.ORE_AXIONITE:
            if isinstance(b, BuildingConveyor):
                pure_ti_conveyor_count += 1
            else:
                heavy_hostile_count += 1
    if not hostile_found:
        return False
    return not (
        ore_env == Environment.ORE_AXIONITE
        and heavy_hostile_count == 0
        and pure_ti_conveyor_count == 1
    )


def on_enemy_side(self: Builder, pos: Position) -> bool:
    """True if `pos` is more than `self.bisector_margin_r2` closer to
    enemy_core than to ours. The margin scales linearly with map size
    (computed in `post_init`); on a 50x50 map it's 20, smaller on
    smaller maps.
    Mirrors the rule used by `_pick_ore` for harvester placement, so econ
    routing of harvester outputs uses the same split: ours-side tiles are
    routed home, enemy-side tiles are left for OFFENSE's `push_extend`.
    Requires symmetry to be resolved; returns False otherwise.
    """
    if self.symmetry is None:
        return False
    enemy_core = self.en_core_guess
    return (
        pos.distance_squared(self.my_core)
        > pos.distance_squared(enemy_core) + self.bisector_margin_r2
    )


def is_inward_guard(self: Builder, pos: Position) -> bool:
    """True if `pos` hosts a friendly conveyor whose flow direction
    points at an adjacent friendly harvester. Such conveyors are
    harvester guards (placed by the proactive ring); their flow goes
    INTO the harvester (where it's destroyed), so they aren't real
    consumers and shouldn't be picked as Ti-sinks. We're also allowed
    to destroy them when claiming the ore underneath as a new harvester."""
    b = self.get_building(pos)
    if not isinstance(b, BuildingConveyor | BuildingArmouredConveyor):
        return False
    if b.team != self.my_team:
        return False
    target = pos.add(b.direction)
    if not self.in_bounds(target):
        return False
    target_b = self.get_building(target)
    return isinstance(target_b, BuildingHarvester) and target_b.team == self.my_team


def _pick_ore(self: Builder, wanted: Environment) -> Position | None:
    enemy_core = self.en_core_guess
    best_target = None
    min_dist = INF
    for pos in self.nearby_tiles:
        if self.get_env(pos) != wanted:
            continue
        match self.get_building(pos):
            case BuildingHarvester():
                continue
            case None | BuildingRoad() | BuildingMarker() | BuildingBarrier():
                pass
            case BuildingConveyor() | BuildingArmouredConveyor():
                # Allow only if it's our own inward guard pointing at
                # an adjacent friendly harvester — we'll destroy it
                # before claiming. Outward / sideways / enemy conveyors
                # still block.
                if not is_inward_guard(self, pos):
                    continue
            case _:
                continue
        if not self.is_reachable(pos):
            continue
        d = self.my_pos.distance_squared(pos)
        if not ore_available(self, pos):
            continue
        # Bisector gate: skip ore that is more than r²=20 closer to enemy
        # core than to ours. Routing such ore home is expensive, and if we
        # could afford it we'd already have economic dominance.
        if (
            pos.distance_squared(self.my_core)
            > pos.distance_squared(enemy_core) + self.bisector_margin_r2
        ):
            continue
        # Contamination gate: skip an ore if placing a harvester there would
        # leak Ti into an Ax chain (or Ax into a Ti chain) via an adjacent
        # transport tile.
        if harvester_would_contaminate(self, pos):
            continue
        # Feed-availability gate: skip ores with no viable feed cardinal
        # (e.g. boxed in by enemy transports / walls / friendly inward
        # guards / harvesters). Without a feed slot the harvester can't
        # be built or its output goes nowhere we control.
        if harvester_feed_cardinal(self, pos) is None:
            continue
        # Coordination: skip an ore tile if any visible friendly builder is
        # strictly closer. Each builder ends up claiming the ores it is
        # nearest to, so several builders don't converge on the same tile
        # and deadlock while one places the harvester.
        if not claims_by_proximity(
            self.my_pos,
            self.my_id,
            pos,
            (
                (fb_pos, fb_id)
                for fb_pos, fb_id in self.all_bots.items()
                if fb_id != self.my_id and fb_pos in self.friendly_bots
            ),
        ):
            continue
        if d < min_dist:
            min_dist = d
            best_target = pos
    return best_target


_UPSTREAM_MAX_NODES = 80
_DOWNSTREAM_MAX_NODES = 80


def upstream_tree(self: Builder, start: Position) -> set[Position]:
    """BFS backwards via `in_edges` — all friendly transport tiles whose
    output structurally reaches `start`.
    """
    visited: set[Position] = {start}
    queue: list[Position] = [start]
    while queue and len(visited) < _UPSTREAM_MAX_NODES:
        pos = queue.pop()
        for u in self.in_edges[pos.y * MAX_WIDTH + pos.x]:
            if u in visited:
                continue
            visited.add(u)
            queue.append(u)
    return visited


def downstream_tree(self: Builder, start: Position) -> set[Position]:
    """BFS forwards via `out_edges`."""
    visited: set[Position] = {start}
    queue: list[Position] = [start]
    while queue and len(visited) < _DOWNSTREAM_MAX_NODES:
        pos = queue.pop()
        for out in self.out_edges[pos.y * MAX_WIDTH + pos.x]:
            if out in visited:
                continue
            visited.add(out)
            queue.append(out)
    return visited


def chain_has_foundry(self: Builder, start: Position) -> bool:
    """Any friendly foundry in the up-or-downstream tree of `start`?"""
    for pos in upstream_tree(self, start):
        b = self.get_building(pos)
        if isinstance(b, BuildingFoundry) and b.team == self.my_team:
            return True
    for pos in downstream_tree(self, start):
        b = self.get_building(pos)
        if isinstance(b, BuildingFoundry) and b.team == self.my_team:
            return True
    return False


def ax_feeds_target(self: Builder, target: Position) -> bool:
    """Ax is (or will be) delivered to `target`. True iff any cardinal
    feeder is structurally downstream of an Ax harvester OR an Ax harvester
    is directly cardinal (the zero-length-chain case — harvesters aren't in
    `in_edges`, so the structural check alone misses them).
    """
    for feeder in self.in_edges[target.y * MAX_WIDTH + target.x]:
        if feeder in self.ax_upstream:
            return True
    for d in DIR4:
        n = target.add(d)
        if not self.in_bounds(n):
            continue
        ni = n.y * MAX_WIDTH + n.x
        nb = self.buildings[ni]
        if (
            isinstance(nb, BuildingHarvester)
            and nb.team == self.my_team
            and self.env[ni] == Environment.ORE_AXIONITE
        ):
            return True
    return False


def tile_has_ax_flow(self: Builder, pos: Position) -> bool:
    """True if flow_history on `pos` shows raw or refined Ax in the last 8
    observed ticks.
    """
    for r, _rid in self.flow_history[pos.y * MAX_WIDTH + pos.x]:
        if r in (ResourceType.RAW_AXIONITE, ResourceType.REFINED_AXIONITE):
            return True
    return False
