"""
Helpers shared by the three ore-claim tasks (`claim_ore`,
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

from cambc import Direction, EntityType, Environment
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller, ControllerApi, Position, Team
if TYPE_CHECKING:
    from builder import Builder
from builder.helpers import (
    can_afford,
    harvester_feed_cardinal,
    make_move,
    make_move_or_adjacent,
    on_enemy_side,
    ore_available,
    try_move_with_road,
)
from util.debug import debug as log
from util.directions import DIR4, delta_to_dir
from util.visualiser import auto_wrap_position


def find_contest_target(builder, pos, my_team):
    """
    Enemy road/conveyor/splitter/bridge cardinal-adjacent to `pos`,
    or None. Such a tile would dump our harvester's output into an
    enemy chain — must be cleared before claim.
    """
    for d in DIR4:
        n = pos.add(d)
        if not builder.in_bounds(n):
            continue
        __opt_tuple = builder.get_building(n)
        if __opt_tuple is None:
            continue
        kind, team = __opt_tuple
        if team == my_team:
            continue
        if (
            kind == EntityType.ROAD
            or kind == EntityType.CONVEYOR
            or kind == EntityType.SPLITTER
            or kind == EntityType.BRIDGE
        ):
            return n
    return None


def is_guarded_cardinal(builder, pos):
    """
    A cardinal is "already guarded" — no inward conveyor needed —
    when an enemy can't easily place a parasitic conveyor there. That
    is: walls, harvesters (any team), and any non-{road,marker} building
    occupying the tile.
    """
    if builder.env[builder.idx(pos)] == Environment.WALL:
        return True
    kind = builder.building_kind[builder.idx(pos)]
    if kind is None:
        return False
    return not (kind == EntityType.ROAD or kind == EntityType.MARKER)


def walk_to_ore_claim(builder, ct, target_pos):
    """
    Walk toward `target_pos`, clearing any contest tile along the way.

    Returns True if the builder is already standing on the ore (claim
    achieved — caller should defer to the next phase) OR if an action
    was taken this turn (still claiming). Returns False only if no
    progress could be made (e.g. no path).
    """
    if builder.state.my_pos == target_pos:
        if not ore_available(builder, target_pos):
            args = {}
            args[str("target")] = auto_wrap_position(target_pos)
            log("walk_to_ore_claim: ore {target} no longer available", args)
            return False
        return True
    contest_pos = find_contest_target(builder, target_pos, builder.state.my_team)
    contest_pos = contest_pos
    if contest_pos is not None:
        args = {}
        args[str("contest")] = auto_wrap_position(contest_pos)
        args[str("target")] = auto_wrap_position(target_pos)
        log("walk_to_ore_claim: CONTEST enemy at {contest} adj to ore {target}", args)
        if builder.state.my_pos == contest_pos:
            if builder.state.ti >= 2 and ct.can_fire(builder.state.my_pos):
                ct.fire(builder.state.my_pos)
            return True
        if builder.state.my_pos.distance_squared(contest_pos) <= 2:
            dx = contest_pos.x - builder.state.my_pos.x
            dy = contest_pos.y - builder.state.my_pos.y
            d = delta_to_dir(dx, dy)
            if d is not None and (ct.can_move(d)):
                ct.move(d)
            return True
        return make_move(builder, ct, contest_pos)
    if (
        builder.state.my_pos.distance_squared(target_pos) <= 2
        and (
            (builder.building_kind[builder.idx(target_pos)] is not None)
            and (
                builder.building_kind[builder.idx(target_pos)] == EntityType.BARRIER
                or builder.building_kind[builder.idx(target_pos)] == EntityType.CONVEYOR
                or builder.building_kind[builder.idx(target_pos)]
                == EntityType.ARMOURED_CONVEYOR
            )
        )
        and ct.can_destroy(target_pos)
    ):
        args = {}
        args[str("target")] = auto_wrap_position(target_pos)
        log("walk_to_ore_claim: destroying friendly guard on ore {target}", args)
        ct.destroy(target_pos)
        builder.apply_local_destroy(target_pos)
    args = {}
    args[str("target")] = auto_wrap_position(target_pos)
    args[str("d")] = builder.state.my_pos.distance_squared(target_pos)
    log("walk_to_ore_claim: walking toward ore {target} dist²={d}", args)
    return try_move_with_road(builder, ct, target_pos) or make_move_or_adjacent(
        builder, ct, target_pos
    )


def needs_harvester_guard(builder, cardinal, target, io_reserved):
    """
    Whether `cardinal` (a tile cardinal to harvester/claimed-ore
    `target`) needs a guard (barrier or inward conveyor) placed.
    """
    if cardinal == builder.state.my_pos:
        return False
    if cardinal in io_reserved:
        return False
    if is_guarded_cardinal(builder, cardinal):
        return False
    ci = builder.idx(cardinal)
    kind = builder.building_kind[ci]
    team = builder.building_team[ci]
    if (
        (
            (kind is not None)
            and (kind == EntityType.CONVEYOR or kind == EntityType.ARMOURED_CONVEYOR)
        )
        and team == builder.state.my_team
        and not (not builder.out_edges[ci])
        and builder.out_edges[ci][0] == target
    ):
        return False
    return True


def place_harvester_guard(builder, ct, cardinal, target):
    """Place a guard at `cardinal` of `target` (a harvester / claim)."""
    use_barrier = _should_use_barrier(builder, cardinal, target)
    etype = EntityType.BARRIER if use_barrier else EntityType.CONVEYOR
    if (
        builder.building_kind[builder.idx(cardinal)] == EntityType.ROAD
        and ct.can_destroy(cardinal)
        and can_afford(builder, etype)
    ):
        ct.destroy(cardinal)
        builder.apply_local_destroy(cardinal)
    if not can_afford(builder, etype):
        return False
    if use_barrier:
        if ct.can_build_barrier(cardinal):
            args = {}
            args[str("at")] = auto_wrap_position(cardinal)
            log("place_harvester_guard: BARRIER at {at} (>=3 walkable cardinals)", args)
            ct.build_barrier(cardinal)
            return True
        return False
    dx = target.x - cardinal.x
    dy = target.y - cardinal.y
    inward = delta_to_dir(dx, dy)
    if inward is None:
        return False
    if ct.can_build_conveyor(cardinal, inward):
        args = {}
        args[str("at")] = auto_wrap_position(cardinal)
        args[str("dir")] = f"{inward}"
        args[str("target")] = auto_wrap_position(target)
        log("place_harvester_guard: CONVEYOR at {at} facing {dir} into {target}", args)
        ct.build_conveyor(cardinal, inward)
        return True
    return False


def _should_use_barrier(builder, guard_pos, target):
    """U-shape local-connectivity check."""
    dx = guard_pos.x - target.x
    dy = guard_pos.y - target.y
    d = delta_to_dir(dx, dy)
    if d is None:
        return False
    top = guard_pos.add(d)
    left_perp = rotate_left(rotate_left(d))
    right_perp = rotate_right(rotate_right(d))
    left_diag = rotate_left(d)
    right_diag = rotate_right(d)
    passable = lambda p: (
        builder.in_bounds(p) and builder.cost_grid[builder.idx(p)] != 1000000
    )
    top_p = passable(top)
    left_p = passable(guard_pos.add(left_perp)) or passable(guard_pos.add(left_diag))
    right_p = passable(guard_pos.add(right_perp)) or passable(guard_pos.add(right_diag))
    must_use_conveyor = not top_p and left_p and right_p
    return not must_use_conveyor


def clear_barriered_feed(builder, ct, target_pos):
    """
    Last-resort: when `harvester_feed_cardinal(target_pos)` returns
    None because every cardinal is blocked, look for a friendly
    barrier on a cardinal closest to the relevant sink and destroy
    it (free for builders). Next turn `harvester_feed_cardinal` will
    pick the now-empty tile as feed, and `guard_harvester_neighbours`
    paves a road on it. Returns True if a destroy was issued.
    """
    sink = (
        (builder.en_core_guess if (builder.symmetry is not None) else None)
        if on_enemy_side(builder, target_pos)
        else (t if ((t := builder.ti_sink) is not None) else builder.my_core)
    )
    sink = sink
    if sink is None:
        return False
    candidates: list[Position] = []
    for d in DIR4:
        c = target_pos.add(d)
        if not builder.in_bounds(c) or c == builder.state.my_pos:
            continue
        if builder.env[builder.idx(c)] == Environment.WALL:
            continue
        if (
            builder.building_kind[builder.idx(c)] == EntityType.BARRIER
            and builder.building_team[builder.idx(c)] == builder.state.my_team
            and ct.can_destroy(c)
        ):
            candidates.append(c)
    if not candidates:
        return False
    chosen = (
        min(candidates, key=lambda c: c.distance_squared(sink)) if candidates else None
    )
    args = {}
    args[str("pos")] = auto_wrap_position(chosen)
    args[str("target")] = auto_wrap_position(target_pos)
    log(
        "clear_barriered_feed: destroy friendly BARRIER on {pos} (last-resort feed clear for {target})",
        args,
    )
    ct.destroy(chosen)
    builder.apply_local_destroy(chosen)
    return True


def step_off_and_build_harvester(builder, ct, target_pos):
    """
    Standing on the ore, step off ONTO THE FEED CARDINAL (the
    harvester's chosen output tile) and place the harvester in the
    same turn.
    """
    feed = harvester_feed_cardinal(builder, target_pos)
    if feed is None:
        return False
    dx = feed.x - builder.state.my_pos.x
    dy = feed.y - builder.state.my_pos.y
    d = delta_to_dir(dx, dy)
    if d is None:
        return False
    if (
        not ct.can_move(d)
        and builder.cost_grid[builder.idx(feed)] > 1
        and can_afford(builder, EntityType.ROAD)
        and ct.can_build_road(feed)
    ):
        args = {}
        args[str("feed")] = auto_wrap_position(feed)
        log("step_off_and_build_harvester: paving feed {feed} for step-off", args)
        ct.build_road(feed)
        return True
    if builder.building_kind[
        builder.idx(builder.state.my_pos)
    ] == EntityType.ROAD and ct.can_destroy(builder.state.my_pos):
        if not ct.can_move(d):
            args = {}
            args[str("feed")] = auto_wrap_position(feed)
            log("step_off_and_build_harvester: feed {feed} blocked; waiting", args)
            return True
        args = {}
        args[str("at")] = auto_wrap_position(builder.state.my_pos)
        args[str("feed")] = auto_wrap_position(feed)
        log(
            "step_off_and_build_harvester: destroy own ROAD at {at}, step to feed {feed}",
            args,
        )
        p = builder.state.my_pos
        ct.destroy(p)
        builder.apply_local_destroy(p)
    if ct.can_move(d):
        args = {}
        args[str("d")] = f"{d}"
        args[str("feed")] = auto_wrap_position(feed)
        log("step_off_and_build_harvester: step {d} to feed {feed}", args)
        ct.move(d)
        if ct.can_build_harvester(target_pos):
            args = {}
            args[str("target")] = auto_wrap_position(target_pos)
            log("step_off_and_build_harvester: HARVESTER placed on {target}", args)
            ct.build_harvester(target_pos)
            builder.ore_target = None
        else:
            kind = builder.building_kind[builder.idx(target_pos)]
            args = {}
            args[str("feed")] = auto_wrap_position(feed)
            args[str("target")] = auto_wrap_position(target_pos)
            args[str("bld")] = f"{k!r}" if (k := kind) is not None else str("None")
            log(
                "step_off_and_build_harvester: stepped to {feed} but can_build_harvester({target}) is False — building at {bld}",
                args,
            )
        return True
    args = {}
    args[str("feed")] = auto_wrap_position(feed)
    log("step_off_and_build_harvester: cannot move to feed {feed}; waiting", args)
    return True


def adjacent_pave_targets(builder, pos):
    """
    Tiles cardinal to `pos` that are friendly Ti harvesters OR a
    claimed-but-unbuilt ore tile. Used by `guard_harvester_neighbours` to find
    pave targets reachable from `pos`.
    """
    out: list[Position] = []
    claimed_targets: set[Position] = set()
    for tgt in [
        builder.ore_target,
        builder.ax_ore_target,
        builder.offensive_ore_target,
    ]:
        t = tgt
        if t is not None and (builder.state.my_pos == t):
            claimed_targets.add(t)
    for d in DIR4:
        n = pos.add(d)
        if not builder.in_bounds(n):
            continue
        if (
            builder.building_kind[builder.idx(n)] == EntityType.HARVESTER
            and builder.building_team[builder.idx(n)] == builder.state.my_team
            and builder.env[builder.idx(n)] == Environment.ORE_TITANIUM
        ):
            out.append(n)
            continue
        if n in claimed_targets:
            out.append(n)
    return out


def rotate_right(d):
    match d:
        case Direction.NORTH:
            return Direction.NORTHEAST
        case Direction.NORTHEAST:
            return Direction.EAST
        case Direction.EAST:
            return Direction.SOUTHEAST
        case Direction.SOUTHEAST:
            return Direction.SOUTH
        case Direction.SOUTH:
            return Direction.SOUTHWEST
        case Direction.SOUTHWEST:
            return Direction.WEST
        case Direction.WEST:
            return Direction.NORTHWEST
        case Direction.NORTHWEST:
            return Direction.NORTH
        case Direction.CENTRE:
            return Direction.CENTRE


def rotate_left(d):
    match d:
        case Direction.NORTH:
            return Direction.NORTHWEST
        case Direction.NORTHEAST:
            return Direction.NORTH
        case Direction.EAST:
            return Direction.NORTHEAST
        case Direction.SOUTHEAST:
            return Direction.EAST
        case Direction.SOUTH:
            return Direction.SOUTHEAST
        case Direction.SOUTHWEST:
            return Direction.SOUTH
        case Direction.WEST:
            return Direction.SOUTHWEST
        case Direction.NORTHWEST:
            return Direction.WEST
        case Direction.CENTRE:
            return Direction.CENTRE
