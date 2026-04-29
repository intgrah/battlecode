"""Helpers shared by the three ore-claim tasks (`claim_ore`,
`guard_harvester_neighbours`, `build_harvester`). The task layer dispatches
priority — these helpers are pure mechanism.

Phases:
  1. `walk_to_ore_claim` — navigate onto the ore tile (with contest
     clearing of any adjacent enemy road/conveyor/splitter/bridge).
  2. `pave_inward_neighbour` — place ONE inward-facing conveyor on a
     cardinal of a friendly Ti harvester or a claimed ore tile, if any
     such cardinal needs guarding.
  3. `step_off_and_build_harvester` — step off the ore tile and place
     the harvester in the same turn.

Walls and friendly harvesters / non-walkable buildings adjacent to the
target count as "already guarded" — the inward ring is only placed on
empty / friendly-road / marker cardinals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingArmouredConveyor,
    BuildingBarrier,
    BuildingBridge,
    BuildingConveyor,
    BuildingHarvester,
    BuildingMarker,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import EntityType, Environment, Position
from util.debug import debug as log
from util.directions import DIR4

from builder.helpers import (
    can_afford,
    harvester_feed_cardinal,
    make_move,
    make_move_or_adjacent,
    on_enemy_side,
    ore_available,
    try_move_with_road,
)

if TYPE_CHECKING:
    from cambc import Controller, Team

    from builder import Builder


def find_contest_target(
    self: Builder,
    pos: Position,
    my_team: Team,
) -> Position | None:
    """Enemy road/conveyor/splitter/bridge cardinal-adjacent to `pos`,
    or None. Such a tile would dump our harvester's output into an
    enemy chain — must be cleared before claim.
    """
    for d in DIR4:
        n = pos.add(d)
        if not self.in_bounds(n):
            continue
        b = self.get_building(n)
        if b is None or b.team == my_team:
            continue
        if isinstance(
            b,
            BuildingRoad | BuildingConveyor | BuildingSplitter | BuildingBridge,
        ):
            return n
    return None


def is_guarded_cardinal(self: Builder, pos: Position) -> bool:
    """A cardinal is "already guarded" — no inward conveyor needed —
    when an enemy can't easily place a parasitic conveyor there. That
    is: walls, harvesters (any team), and any non-{road,marker} building
    occupying the tile.
    """
    if self.get_env(pos) == Environment.WALL:
        return True
    b = self.get_building(pos)
    if b is None:
        return False
    return not isinstance(b, BuildingRoad | BuildingMarker)


def walk_to_ore_claim(self: Builder, ct: Controller, target_pos: Position) -> bool:
    """Walk toward `target_pos`, clearing any contest tile along the way.
    Returns True if the builder is already standing on the ore (claim
    achieved — caller should defer to the next phase) OR if an action
    was taken this turn (still claiming). Returns False only if no
    progress could be made (e.g. no path).
    """
    if self.my_pos == target_pos:
        if not ore_available(self, target_pos):
            log(
                "walk_to_ore_claim: ore {target} no longer available",
                target=target_pos,
            )
            return False
        # On the ore. Claim achieved; caller decides what's next.
        return True

    # Contest: an enemy road/conveyor/splitter/bridge adjacent to the
    # ore must be cleared before we can build the harvester safely.
    contest_pos = find_contest_target(self, target_pos, self.my_team)
    if contest_pos is not None:
        log(
            "walk_to_ore_claim: CONTEST enemy at {contest} adj to ore {target}",
            contest=contest_pos,
            target=target_pos,
        )
        if self.my_pos == contest_pos:
            if self.ti >= 2 and ct.can_fire(self.my_pos):
                ct.fire(self.my_pos)
            return True
        if self.my_pos.distance_squared(contest_pos) <= 2:
            d = self.my_pos.direction_to(contest_pos)
            if ct.can_move(d):
                ct.move(d)
            return True
        return make_move(self, ct, contest_pos)

    # If the ore tile itself has a friendly guard (barrier, conveyor,
    # armoured) placed earlier as the protective ring of an ADJACENT
    # harvester, tear it down so we can walk onto the now-empty tile.
    if self.my_pos.distance_squared(target_pos) <= 2:
        existing = self.get_building(target_pos)
        if isinstance(
            existing,
            BuildingBarrier | BuildingConveyor | BuildingArmouredConveyor,
        ) and ct.can_destroy(target_pos):
            log(
                "walk_to_ore_claim: destroying friendly guard on ore {target}",
                target=target_pos,
            )
            ct.destroy(target_pos)
            self.apply_local_destroy(target_pos)

    log(
        "walk_to_ore_claim: walking toward ore {target} dist²={d}",
        target=target_pos,
        d=self.my_pos.distance_squared(target_pos),
    )
    return try_move_with_road(self, ct, target_pos) or make_move_or_adjacent(
        self,
        ct,
        target_pos,
    )


def needs_harvester_guard(
    self: Builder,
    cardinal: Position,
    target: Position,
    io_reserved: set[Position],
) -> bool:
    """Whether `cardinal` (a tile cardinal to harvester/claimed-ore
    `target`) needs a guard (barrier or inward conveyor) placed.
    False if:
      - the tile is already guarded (wall, harvester, non-walkable bld),
      - it's the builder's own tile,
      - it's reserved as an I/O slot (feed cardinal or already a flow
        consumer),
      - it already has an inward-pointing friendly conveyor pointing AT
        target.
    """
    if cardinal == self.my_pos:
        return False
    if cardinal in io_reserved:
        return False
    if is_guarded_cardinal(self, cardinal):
        return False
    b = self.get_building(cardinal)
    if isinstance(b, BuildingConveyor | BuildingArmouredConveyor):
        # Already an inward conveyor pointing at target?
        if b.team == self.my_team and cardinal.add(b.direction) == target:
            return False
    return True


def place_harvester_guard(
    self: Builder,
    ct: Controller,
    cardinal: Position,
    target: Position,
) -> bool:
    """Place a guard at `cardinal` of `target` (a harvester / claim).
    Picks BARRIER when `cardinal` already has >=3 walkable cardinal
    neighbours (builders can route around the barrier; barriers are
    immune to builder-fire so they're preferred where applicable),
    otherwise places an inward-facing CONVEYOR (walkable, preserves
    connectivity in tight geometry). Tears down a friendly road on the
    tile first if needed. Returns True if a build (or a destroy that
    enables one) action was taken.
    """
    use_barrier = _should_use_barrier(self, cardinal, target)
    etype = EntityType.BARRIER if use_barrier else EntityType.CONVEYOR
    if (
        isinstance(self.get_building(cardinal), BuildingRoad)
        and ct.can_destroy(cardinal)
        and can_afford(self, etype)
    ):
        ct.destroy(cardinal)
        self.apply_local_destroy(cardinal)
    if not can_afford(self, etype):
        return False
    if use_barrier:
        if ct.can_build_barrier(cardinal):
            log(
                "place_harvester_guard: BARRIER at {at} (>=3 walkable cardinals)",
                at=cardinal,
            )
            ct.build_barrier(cardinal)
            return True
        return False
    inward = cardinal.direction_to(target)
    if ct.can_build_conveyor(cardinal, inward):
        log(
            "place_harvester_guard: CONVEYOR at {at} facing {dir} into {target}",
            at=cardinal,
            dir=inward,
            target=target,
        )
        ct.build_conveyor(cardinal, inward)
        return True
    return False


def _should_use_barrier(
    self: Builder,
    guard_pos: Position,
    target: Position,
) -> bool:
    """U-shape local-connectivity check.

    The guard tile `g` sits at one cardinal of `target` (the
    harvester / claim). Define the 5 8-neighbours of `g` excluding
    `target` — the U shape opening away from the harvester:

            top                    (g + d, where d = target -> g)
       ┌────┼────┐
    left_far    right_far          (g + left_diag, g + right_diag)
       │         │
    left_near    right_near        (g + left_perp, g + right_perp)
       │         │
       └─target──┘                 (target = g + opposite of d)

    Barrier at `g` is safe (doesn't locally disconnect) iff:
      - `top` is passable (the U has a "northern bridge" between
        sides), OR
      - one of {left_near, left_far} OR {right_near, right_far} has
        zero passable tiles (no traffic on that side to disconnect).

    Otherwise the only local left-right path runs through `g` and a
    barrier would sever it — fall back to the inward conveyor
    (walkable, preserves connectivity).
    """
    d = target.direction_to(guard_pos)
    top = guard_pos.add(d)
    left_perp = d.rotate_left().rotate_left()  # 90° CCW
    right_perp = d.rotate_right().rotate_right()  # 90° CW
    left_diag = d.rotate_left()  # 45° CCW
    right_diag = d.rotate_right()  # 45° CW

    def passable(p: Position) -> bool:
        return self.in_bounds(p) and self.is_passable(p)

    top_p = passable(top)
    left_p = passable(guard_pos.add(left_perp)) or passable(
        guard_pos.add(left_diag),
    )
    right_p = passable(guard_pos.add(right_perp)) or passable(
        guard_pos.add(right_diag),
    )

    # Use conveyor (return False) iff top is impassable AND both side
    # groups have ≥1 passable; otherwise barrier is locally safe.
    must_use_conveyor = (not top_p) and left_p and right_p
    return not must_use_conveyor


def clear_barriered_feed(
    self: Builder,
    ct: Controller,
    target_pos: Position,
) -> bool:
    """Last-resort: when `harvester_feed_cardinal(target_pos)` returns
    None because every cardinal is blocked, look for a friendly
    barrier on a cardinal closest to the relevant sink and destroy
    it (free for builders). Next turn `harvester_feed_cardinal` will
    pick the now-empty tile as feed, and `guard_harvester_neighbours`
    paves a road on it. Returns True if a destroy was issued.

    Mirrors `harvester_feed_cardinal`'s sink-direction selection so
    the cleared cardinal is the one we'd actually want as feed.
    """
    if on_enemy_side(self, target_pos):
        sink = self.en_core_guess if self.symmetry is not None else None
    else:
        sink = self.ti_sink if self.ti_sink is not None else self.my_core
    if sink is None:
        return False

    candidates: list[Position] = []
    for d in DIR4:
        c = target_pos.add(d)
        if not self.in_bounds(c) or c == self.my_pos:
            continue
        if self.get_env(c) == Environment.WALL:
            continue
        b = self.get_building(c)
        if (
            isinstance(b, BuildingBarrier)
            and b.team == self.my_team
            and ct.can_destroy(c)
        ):
            candidates.append(c)
    if not candidates:
        return False
    chosen = min(candidates, key=lambda c: c.distance_squared(sink))
    log(
        "clear_barriered_feed: destroy friendly BARRIER on {pos} (last-resort feed clear for {target})",
        pos=chosen,
        target=target_pos,
    )
    ct.destroy(chosen)
    self.apply_local_destroy(chosen)
    return True


def step_off_and_build_harvester(
    self: Builder,
    ct: Controller,
    target_pos: Position,
) -> bool:
    """Standing on the ore, step off ONTO THE FEED CARDINAL (the
    harvester's chosen output tile) and place the harvester in the
    same turn. Hard requirement: we always step onto the feed tile —
    that way the next turn the builder can immediately start laying
    the chain at exactly the right spot, no routing detour. If the
    feed tile isn't movable onto right now (a bot's blocking it,
    cooldown, etc.), wait — there's nowhere else worth stepping.
    """
    feed = harvester_feed_cardinal(self, target_pos)
    if feed is None:
        # Caller (`build_harvester`) already gates on this; return
        # False so the task knows nothing happened.
        return False

    d = self.my_pos.direction_to(feed)

    # If the feed isn't walkable yet (marker / empty terrain that
    # the proactive guard pass missed, or never ran for OFFENSE),
    # pave a road on it as a last-resort. Burns this turn's action;
    # the destroy + move + build sequence runs next turn when the
    # feed is walkable.
    if (
        not ct.can_move(d)
        and self.get_cost(feed) > 1
        and can_afford(self, EntityType.ROAD)
        and ct.can_build_road(feed)
    ):
        log(
            "step_off_and_build_harvester: paving feed {feed} for step-off",
            feed=feed,
        )
        ct.build_road(feed)
        return True

    # Tear down any own-road on the ore (if we paved here on arrival).
    # Need to confirm we can step onto the feed tile BEFORE destroying;
    # otherwise we'd lose the road and still be stuck on the ore.
    b = self.get_building(self.my_pos)
    if isinstance(b, BuildingRoad) and ct.can_destroy(self.my_pos):
        if not ct.can_move(d):
            log(
                "step_off_and_build_harvester: feed {feed} blocked; waiting",
                feed=feed,
            )
            return True
        log(
            "step_off_and_build_harvester: destroy own ROAD at {at}, step to feed {feed}",
            at=self.my_pos,
            feed=feed,
        )
        ct.destroy(self.my_pos)
        self.apply_local_destroy(self.my_pos)

    if ct.can_move(d):
        log(
            "step_off_and_build_harvester: step {d} to feed {feed}",
            d=d,
            feed=feed,
        )
        ct.move(d)
        if ct.can_build_harvester(target_pos):
            log(
                "step_off_and_build_harvester: HARVESTER placed on {target}",
                target=target_pos,
            )
            ct.build_harvester(target_pos)
            self.ore_target = None
        else:
            log(
                "step_off_and_build_harvester: stepped to {feed} but "
                "can_build_harvester({target}) is False — building at {bld}",
                feed=feed,
                target=target_pos,
                bld=type(self.get_building(target_pos)).__name__
                if self.get_building(target_pos) is not None
                else "None",
            )
        return True
    log(
        "step_off_and_build_harvester: cannot move to feed {feed}; waiting",
        feed=feed,
    )
    return True


def adjacent_pave_targets(self: Builder, pos: Position) -> list[Position]:
    """Tiles cardinal to `pos` that are friendly Ti harvesters OR a
    claimed-but-unbuilt ore tile (the builder is currently standing on
    one of {ore_target, ax_ore_target, offensive_ore_target} and needs
    its inward ring placed). Used by `guard_harvester_neighbours` to find
    pave targets reachable from `pos`.
    """
    out: list[Position] = []
    claimed_targets: set[Position] = set()
    for tgt in (
        self.ore_target,
        self.ax_ore_target,
        self.offensive_ore_target,
    ):
        if tgt is not None and self.my_pos == tgt:
            claimed_targets.add(tgt)
    for d in DIR4:
        n = pos.add(d)
        if not self.in_bounds(n):
            continue
        b = self.get_building(n)
        if (
            isinstance(b, BuildingHarvester)
            and b.team == self.my_team
            and self.get_env(n) == Environment.ORE_TITANIUM
        ):
            out.append(n)
            continue
        if n in claimed_targets:
            out.append(n)
    return out
