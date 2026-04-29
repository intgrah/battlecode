"""Helpers shared by the three ore-claim tasks (`claim_ore`,
`pave_inward_conveyors`, `build_harvester`). The task layer dispatches
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
    harvester_io_cardinals,
    make_move,
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
    if isinstance(b, BuildingRoad | BuildingMarker):
        return False
    return True


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
        if (
            isinstance(
                existing,
                BuildingBarrier | BuildingConveyor | BuildingArmouredConveyor,
            )
            and ct.can_destroy(target_pos)
        ):
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
    return try_move_with_road(self, ct, target_pos) or make_move(
        self, ct, target_pos,
    )


def needs_inward_guard(
    self: Builder,
    cardinal: Position,
    target: Position,
    io_reserved: set[Position],
) -> bool:
    """Whether `cardinal` (a tile cardinal to harvester/claimed-ore
    `target`) needs an inward-facing conveyor placed. False if:
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


def place_inward_conveyor(
    self: Builder,
    ct: Controller,
    cardinal: Position,
    target: Position,
) -> bool:
    """Place an inward-facing friendly conveyor at `cardinal` pointing
    at `target`. Tears down a friendly road on the tile first if needed.
    Returns True if a build (or a destroy that enables one) action was
    taken.
    """
    inward = cardinal.direction_to(target)
    if (
        isinstance(self.get_building(cardinal), BuildingRoad)
        and ct.can_destroy(cardinal)
        and can_afford(self, EntityType.CONVEYOR)
    ):
        ct.destroy(cardinal)
        self.apply_local_destroy(cardinal)
    if can_afford(self, EntityType.CONVEYOR) and ct.can_build_conveyor(
        cardinal, inward,
    ):
        log(
            "place_inward_conveyor: CONVEYOR at {at} facing {dir} into {target}",
            at=cardinal,
            dir=inward,
            target=target,
        )
        ct.build_conveyor(cardinal, inward)
        return True
    return False


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
            "step_off_and_build_harvester: step {d} to feed {feed}, place HARVESTER on {target}",
            d=d,
            feed=feed,
            target=target_pos,
        )
        ct.move(d)
        if ct.can_build_harvester(target_pos):
            ct.build_harvester(target_pos)
            self.ore_target = None
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
    its inward ring placed). Used by `pave_inward_conveyors` to find
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
