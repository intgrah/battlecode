from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingGunner,
    BuildingHarvester,
    BuildingLauncher,
    BuildingSentinel,
    BuildingSplitter,
)
from cambc import (
    Controller,
    Direction,
    EntityType,
    Environment,
    GameConstants,
    Position,
)
from util import (
    DIR4,
    DIR8,
    can_afford,
    chebyshev,
    closest,
    try_move,
)

from .helpers import (
    get_enemy_core_pos,
    make_move,
    move_random,
    try_attack,
    try_place,
)
from .state import State
from .task_explore import explore


def open_tiles(
    state: State, ct: Controller, positions: list[Position]
) -> list[Position]:
    return [
        p
        for p in positions
        if state.is_passable(p)
        and (not ct.is_in_vision(p) or ct.get_tile_builder_bot_id(p) is None)
    ]


def is_allied_transport(state: State, ct: Controller, position: Position) -> bool:
    match state.get_building(position):
        case (
            BuildingConveyor(team=t)
            | BuildingArmouredConveyor(team=t)
            | BuildingSplitter(team=t)
            | BuildingBridge(team=t)
        ) if t == ct.get_team():
            return True
        case _:
            return False


def without_allied_transport(
    state: State, ct: Controller, positions: list[Position]
) -> list[Position]:
    return [pos for pos in positions if not is_allied_transport(state, ct, pos)]


def buildable(state: State, positions: list[Position]) -> list[Position]:
    return [
        p
        for p in positions
        if state.is_buildable(p) and not state.is_friendly_turret(p)
    ]


def nearest_enemy_bot(ct: Controller) -> Position | None:
    builders = ct.get_nearby_units()
    builder_positions = [
        ct.get_position(uid) for uid in builders if ct.get_team(uid) != ct.get_team()
    ]
    if len(builder_positions) == 0:
        return None
    return closest(ct.get_position(), builder_positions)


_BUILDER_DPS: int = 2  # one fire per turn at 2 dmg
_HEAL_RANGE_CHEBY: int = 1  # heal action r²=2 → up to 1 Chebyshev step away


def should_attack(state: State, ct: Controller, pos: Position) -> bool:
    """Strict gate: attack only if we'd destroy the target before any
    visible enemy bot can reach heal range.

    Math: at 2 dmg/turn, destroy_turns = ceil(hp / 2). Each enemy bot
    needs `max(0, Chebyshev(epos, pos) - 1)` turns to reach a tile in
    heal range (1 Chebyshev from target). Attack iff every enemy's
    arrival > destroy_turns; if any enemy gets there in time their
    4 HP/turn heal outpaces our 2 dmg/turn fire and the engagement
    is a Ti sink.

    Carve-out: a 1-shot kill (destroy_turns <= 1) always commits.

    Caller contract: when this returns False the run loop must NOT
    leave the bot camped on `pos` — `run_attack` repositions to a tile
    not in any healer's range, or drops the target entirely.
    """
    bid = ct.get_tile_building_id(pos)
    if bid is None:
        return False

    current_hp = ct.get_hp(bid)
    destroy_turns = (current_hp + _BUILDER_DPS - 1) // _BUILDER_DPS
    if destroy_turns <= 1:
        return True

    my_team = ct.get_team()
    for uid in ct.get_nearby_units():
        if ct.get_team(uid) == my_team:
            continue
        epos = ct.get_position(uid)
        cheby = max(abs(epos.x - pos.x), abs(epos.y - pos.y))
        enemy_arrival = max(0, cheby - _HEAL_RANGE_CHEBY)
        if enemy_arrival < destroy_turns:
            return False
    return True


def _enemy_healer_near(ct: Controller, pos: Position) -> bool:
    """True if any enemy builder bot sits within r²≤2 of `pos` — they
    can heal it for 4 HP/turn which outpaces our 2 dmg/turn fire.
    Lone attackers in this range are wasting Ti.

    The bounds guards are load-bearing: the real cambc engine raises
    `Position out of bounds` on `ct.get_tile_builder_bot_id(n)` when
    `n` is off-map, even if `ct.is_in_vision(n)` didn't reject it
    first. cambcpypy happens to return False for OOB from
    is_in_vision, which is why the hetzner sweeps passed but the
    official-server test crashed on maps where an enemy harvester
    sits at the edge.
    """
    my_team = ct.get_team()
    w = ct.get_map_width()
    h = ct.get_map_height()
    for d in DIR8:
        n = pos.add(d)
        if not (0 <= n.x < w and 0 <= n.y < h):
            continue
        if ct.is_in_vision(n):
            uid = ct.get_tile_builder_bot_id(n)
            if uid is not None and ct.get_team(uid) != my_team:
                return True
    if 0 <= pos.x < w and 0 <= pos.y < h and ct.is_in_vision(pos):
        uid = ct.get_tile_builder_bot_id(pos)
        if uid is not None and ct.get_team(uid) != my_team:
            return True
    return False


def _pick_attack_destination(
    state: State, ct: Controller, target: Position, *, avoid_healers: bool = True
) -> Position | None:
    """Pick a cardinal neighbour of `target` (an enemy harvester) for
    us to stand on and attack. Sort by:
      1. no enemy healer in range — lone attackers lose to healers
      2. lowest HP to destroy (road 5 < conveyor/splitter/bridge 20)
      3. closest to our current position

    When `avoid_healers=True` (default), destinations inside an enemy
    healer's r²≤2 are filtered out entirely — the caller can then try
    a different target harvester. When False, we fall back to any
    walkable candidate (useful when nothing else is viable).
    """
    my_pos = ct.get_position()
    my_team = ct.get_team()
    candidates: list[tuple[int, int, Position]] = []
    for d in DIR4:
        pos = target.add(d)
        if not state.in_bounds(pos):
            continue
        if not state.is_passable(pos):
            continue
        if is_allied_transport(state, ct, pos):
            continue
        if ct.is_in_vision(pos):
            uid = ct.get_tile_builder_bot_id(pos)
            if uid is not None and uid != ct.get_id():
                continue
        b = state.get_building(pos)
        if b is None:
            # Empty terrain — a bot can walk here (building a road
            # on the way) and then place sentinels from it.
            cost = 0
        elif getattr(b, "team", None) == my_team:
            # Friendly road / allied core — fine to stand on. Friendly
            # conveyors/splitters/bridges were already filtered above
            # via `is_allied_transport`, so anything reaching here is
            # safe to land on without breaking our own chain.
            cost = 0
        elif isinstance(b, (BuildingConveyor, BuildingSplitter, BuildingBridge)):
            cost = 20  # enemy transport — can destroy by firing
        else:
            cost = 5  # enemy road, 5 HP
        if avoid_healers and _enemy_healer_near(ct, pos):
            continue
        dist = my_pos.distance_squared(pos)
        candidates.append((cost, dist, pos))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][2]


_DIAGONALS: list[Direction] = [d for d in DIR8 if d not in DIR4]


def _gunner_chain_facing(
    state: State, ct: Controller, pos: Position
) -> Direction | None:
    """Return a diagonal direction such that a gunner placed at
    `pos` facing that way has an enemy conveyor/splitter/bridge as
    the first building in its forward ray. Used to position gunners
    next to enemy harvesters so they eat the harvester's output
    chain tile-by-tile.

    Ray semantics: walk the diagonal out to r²=13, stop at the
    first wall or building. Only success case is "first building is
    enemy transport"; friendly buildings or non-transport enemies
    block the shot and disqualify this direction.
    """
    team = ct.get_team()
    r_sq = GameConstants.GUNNER_VISION_RADIUS_SQ
    for d in _DIAGONALS:
        current = pos
        for _ in range(4):
            current = current.add(d)
            if not state.in_bounds(current):
                break
            if pos.distance_squared(current) > r_sq:
                break
            if state.get_env(current) == Environment.WALL:
                break
            b = state.get_building(current)
            if b is None:
                continue
            if getattr(b, "team", None) == team:
                break
            if isinstance(
                b,
                (
                    BuildingConveyor,
                    BuildingArmouredConveyor,
                    BuildingSplitter,
                    BuildingBridge,
                ),
            ):
                return d
            break
    return None


def run_attack(state: State, ct: Controller) -> None:
    team = ct.get_team()
    enemy_buildings = [
        p
        for p in state.nearby_buildings
        if (b := state.get_building(p)) is not None and b.team != team
    ]
    enemy_harvesters = [
        p
        for p in enemy_buildings
        if isinstance(state.get_building(p), BuildingHarvester)
    ]

    def has_open_side(position: Position) -> bool:
        for direction in DIR4:
            new_position = position.add(direction)
            occupant = 1
            if not state.in_bounds(new_position):
                continue
            if ct.is_in_vision(new_position):
                occupant = ct.get_tile_builder_bot_id(new_position)
            occupied = occupant is not None and occupant != ct.get_id()
            if (
                state.is_passable(position.add(direction))
                and not occupied
                and not is_allied_transport(state, ct, position.add(direction))
            ):
                return True
        return False

    vulnerable_harvesters = [p for p in enemy_harvesters if has_open_side(p)]
    enemy_core = get_enemy_core_pos(state)

    # If we've moved off the tile we last fired at, drop the stale
    # expected-HP tracking — otherwise a future visit to the same
    # tile could misread its pre-heal HP as "healed by enemy".
    if state.last_fire_pos is not None and ct.get_position() != state.last_fire_pos:
        state.last_fire_pos = None

    if (state.offense_turns > 25) or (
        state.offense_target
        and ct.is_in_vision(state.offense_target)
        and (
            not state.is_enemy_building(state.offense_target)
            or (not state.is_passable(state.offense_target))
            or (
                ct.get_tile_builder_bot_id(state.offense_target) is not None
                and ct.get_tile_builder_bot_id(state.offense_target) != ct.get_id()
            )
        )
    ):
        state.offense_target = None
        state.offense_launcher = None
        state.offense_turns = 0
    else:
        state.offense_turns += 1

    if len(vulnerable_harvesters) > 0:
        # Prefer closest harvester with NO enemy builder adjacent
        # (no defender/healer waiting). Fall back to closest of all.
        # This spreads our attackers across lightly-contested targets
        # instead of dogpiling one that already has defenders.
        my_pos = ct.get_position()
        target = None
        for h in sorted(
            vulnerable_harvesters,
            key=lambda p: my_pos.distance_squared(p),
        ):
            if not _enemy_healer_near(ct, h):
                target = h
                break
        if target is None:
            target = closest(my_pos, vulnerable_harvesters)
        on_friendly_conveyor = is_allied_transport(state, ct, ct.get_position())
        if ct.get_position().distance_squared(target) == 1 and not on_friendly_conveyor:
            if state.is_enemy_building(ct.get_position()):
                my_pos = ct.get_position()
                # Check for actual healing: if we stood here last turn
                # and fired, we know what HP we LEFT the tile at. If
                # the current HP is strictly higher, an enemy builder
                # must have healed. Only give up the tile when we have
                # that concrete evidence.
                being_healed = False
                if state.last_fire_pos == my_pos:
                    bid_here = ct.get_tile_building_id(my_pos)
                    if bid_here is not None:
                        current_hp = ct.get_hp(bid_here)
                        if current_hp > state.last_fire_expected_hp:
                            being_healed = True
                if being_healed:
                    alt = _pick_attack_destination(state, ct, target)
                    if alt is not None and alt != my_pos:
                        state.last_fire_pos = None
                        make_move(state, ct, alt)
                        return
                if should_attack(state, ct, my_pos):
                    # Record the expected HP for next turn's healing
                    # check BEFORE firing, because `ct.get_hp(bid)` is
                    # still the pre-fire value right now.
                    bid_here = ct.get_tile_building_id(my_pos)
                    if bid_here is not None:
                        pre_hp = ct.get_hp(bid_here)
                        state.last_fire_pos = my_pos
                        # Builder fire is 2 dmg; clamp to 0.
                        state.last_fire_expected_hp = max(0, pre_hp - 2)
                    try_attack(ct)
                    state.offense_target = my_pos
                    state.offense_turns = 0
                else:
                    # Strict gate refused — heal pressure outpaces our
                    # DPS here. Either find a safer attack tile (one
                    # outside any visible healer's range) or abandon
                    # this target so we go scout the next one.
                    state.last_fire_pos = None
                    alt = _pick_attack_destination(
                        state, ct, target, avoid_healers=True
                    )
                    if alt is not None and alt != my_pos:
                        make_move(state, ct, alt)
                        return
                    state.offense_target = None
                    state.offense_turns = 0

            else:
                build_position = ct.get_position()
                move_random(state, ct)
                direction = build_position.direction_to(enemy_core)
                if direction == build_position.direction_to(target):
                    direction = direction.rotate_right()

                # Cap turrets adjacent to the target harvester at
                # 1 gunner + 1 sentinel. Gunner gets priority when it
                # has a clean diagonal ray onto the enemy conveyor
                # chain — it then eats the chain tile-by-tile while
                # a sentinel applies pressure to the harvester.
                n_gunner = 0
                n_sentinel = 0
                for d in DIR4:
                    nb = state.get_building(target.add(d))
                    if nb is None or nb.team != ct.get_team():
                        continue
                    if isinstance(nb, BuildingGunner):
                        n_gunner += 1
                    elif isinstance(nb, BuildingSentinel):
                        n_sentinel += 1

                if n_gunner == 0:
                    gdir = _gunner_chain_facing(state, ct, build_position)
                    if gdir is not None:
                        try_place(ct, EntityType.GUNNER, build_position, gdir)

                if (
                    n_sentinel == 0
                    and state.get_env(target) == Environment.ORE_TITANIUM
                ):
                    try_place(ct, EntityType.SENTINEL, build_position, direction)

                if ct.can_build_road(build_position):
                    ct.build_road(build_position)
                scout_toward_enemy(state, ct)

        else:
            # Pick any walkable cardinal neighbour of the target. We
            # don't pre-filter by healer range here — bots that show
            # up and start attacking might get out-healed, but giving
            # up on approach over every possible enemy bot nearby is
            # worse: enemy bots are common around enemy harvesters
            # (building them), and we'd reject almost every target.
            destination = _pick_attack_destination(
                state, ct, target, avoid_healers=False
            )
            if destination is None:
                # Original fallback: allow any walkable non-friendly-
                # transport cardinal. This covers cases where
                # _pick_attack_destination is too strict.
                destination = closest(
                    ct.get_position(),
                    without_allied_transport(
                        state,
                        ct,
                        open_tiles(state, ct, [target.add(d) for d in DIR4]),
                    ),
                )
                if destination is None:
                    scout_toward_enemy(state, ct)
                    return
            launcher_location = closest(
                destination,
                buildable(state, [ct.get_position().add(d) for d in DIR8]),
            )
            adjacent_launchers = [
                p
                for p in [ct.get_position().add(d) for d in DIR8]
                if isinstance(state.get_building(p), BuildingLauncher)
            ]
            best_adjacent_launcher = closest(destination, adjacent_launchers)
            if (
                ct.get_position().distance_squared(destination) <= 2
                or ct.get_position().distance_squared(target) < 9
            ):
                make_move(state, ct, destination)
            elif (
                best_adjacent_launcher
                and state.is_walkable(destination)
                and best_adjacent_launcher.distance_squared(destination)
                <= GameConstants.LAUNCHER_VISION_RADIUS_SQ
            ):
                pass
            elif (
                launcher_location
                and not best_adjacent_launcher
                and state.is_walkable(destination)
                and launcher_location.distance_squared(destination)
                <= GameConstants.LAUNCHER_VISION_RADIUS_SQ
                and try_place(ct, EntityType.LAUNCHER, launcher_location)
            ):
                state.offense_launcher = launcher_location
            elif (
                state.offense_launcher
                and state.offense_launcher.distance_squared(ct.get_position()) < 25
            ):
                make_move(state, ct, state.offense_launcher)
            elif (
                state.offense_target
                and state.offense_target.distance_squared(ct.get_position()) < 20
            ):
                make_move(state, ct, state.offense_target)
            else:
                make_move(state, ct, target)

        if (
            ct.get_position().distance_squared(target) == 1
            and state.is_enemy_building(ct.get_position())
            and should_attack(state, ct, ct.get_position())
        ):
            try_attack(ct)
    elif (
        state.offense_target
        and state.offense_launcher
        and isinstance(
            rl := state.get_building(state.offense_launcher), BuildingLauncher
        )
        and rl.team == ct.get_team()
        and ct.get_position().distance_squared(state.offense_target) > 8
    ):
        make_move(state, ct, state.offense_launcher)
    elif state.offense_target:
        make_move(state, ct, state.offense_target)
    else:
        scout_toward_enemy(state, ct)


def scout_toward_enemy(state: State, ct: Controller) -> None:
    en_core = get_enemy_core_pos(state)
    if ct.get_position().distance_squared(en_core) <= 20:
        state.enemy_core_seen = True

    if not state.enemy_core_seen:
        make_move(state, ct, en_core)
    elif ct.get_position().distance_squared(en_core) <= 20 or ct.get_global_resources()[
        0
    ] >= (GameConstants.HARVESTER_BASE_COST[0] + 50) * (
        1 + ct.get_scale_percent() / 100
    ):
        explore(state, ct)
    else:
        dir8 = DIR8[:]
        state.rng.shuffle(dir8)
        my_pos = ct.get_position()
        for d in dir8:
            if try_move(ct, my_pos.add(d)):
                break
