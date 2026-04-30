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
        and p not in state.friendly_turret_ray_tiles
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


def _enemy_healer_near(ct: Controller, pos: Position) -> bool:
    """True if any enemy builder bot sits within r²≤2 of `pos` — they
    can heal it for 4 HP/turn which outpaces our 2 dmg/turn fire.
    Lone attackers in this range are wasting Ti.

    The bounds guards are load-bearing: the real cambc engine raises
    `Position out of bounds` on `ct.get_tile_builder_bot_id(n)` when
    `n` is off-map, even if `ct.is_in_vision(n)` didn't reject it
    first. cambc_pypy happens to return False for OOB from
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


def _friendly_bot_adjacent(ct: Controller, pos: Position) -> bool:
    """True if any friendly builder bot (other than us) sits on a
    cardinal neighbour of `pos`. Used to skip harvesters already
    being attacked by another bot — spreads us across targets
    instead of dogpiling. Vision-only: if we can't see the tile
    we assume nobody is there.
    """
    my_team = ct.get_team()
    my_id = ct.get_id()
    w = ct.get_map_width()
    h = ct.get_map_height()
    for d in DIR4:
        n = pos.add(d)
        if not (0 <= n.x < w and 0 <= n.y < h):
            continue
        if not ct.is_in_vision(n):
            continue
        uid = ct.get_tile_builder_bot_id(n)
        if uid is not None and uid != my_id and ct.get_team(uid) == my_team:
            return True
    return False


def _min_friendly_chebyshev(ct: Controller, pos: Position) -> int:
    """Chebyshev distance from `pos` to the nearest OTHER friendly
    builder bot. Used to score attack spacing: an enemy healer
    (heal radius r²≤2 ≈ 1 king-move) can cover at most one of us
    when we're ≥3 chebyshev apart, so we prefer targets that are
    well away from our other attackers.
    """
    my_team = ct.get_team()
    my_id = ct.get_id()
    best = 999
    for uid in ct.get_nearby_units():
        if uid == my_id:
            continue
        if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
            continue
        if ct.get_team(uid) != my_team:
            continue
        d = chebyshev(pos, ct.get_position(uid))
        best = min(best, d)
    return best


def _pick_conveyor_target(
    state: State, ct: Controller, enemy_core: Position, my_pos: Position
) -> Position | None:
    """Pick an enemy conveyor/bridge/splitter tile to attack, falling
    back when no harvester is vulnerable. Preference in order:
      1. near enemy core (r²≤25)
      2. conveyor currently carrying a Ti stack (visible flow)
    Spacing: prefer tiles far from our other attackers (cap at
    chebyshev 3 — past that point spacing gains are moot since one
    enemy healer already can't reach two of us).
    """
    my_team = ct.get_team()
    best: Position | None = None
    best_score: tuple[int, int, int] | None = None
    for pos in state.nearby_buildings:
        b = state.get_building(pos)
        if b is None or getattr(b, "team", None) == my_team:
            continue
        if not isinstance(
            b,
            (
                BuildingConveyor,
                BuildingArmouredConveyor,
                BuildingSplitter,
                BuildingBridge,
            ),
        ):
            continue
        if not state.is_passable(pos):
            continue
        if pos in state.attack_tile_blacklist:
            continue
        if pos in state.friendly_turret_ray_tiles:
            continue
        if ct.is_in_vision(pos):
            uid = ct.get_tile_builder_bot_id(pos)
            if uid is not None and uid != ct.get_id():
                continue
        if _enemy_healer_near(ct, pos):
            continue
        near_core = pos.distance_squared(enemy_core) <= 25
        has_flow = False
        if ct.is_in_vision(pos):
            bid = ct.get_tile_building_id(pos)
            if bid is not None and ct.get_stored_resource(bid) is not None:
                has_flow = True
        if near_core:
            tier = 0
        elif has_flow:
            tier = 1
        else:
            continue
        spacing = _min_friendly_chebyshev(ct, pos)
        my_dist = my_pos.distance_squared(pos)
        score = (tier, -min(spacing, 3), my_dist)
        if best_score is None or score < best_score:
            best = pos
            best_score = score
    return best


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
    candidates: list[tuple[int, int, int, Position]] = []
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
        if pos in state.attack_tile_blacklist:
            continue
        # Standing here would block our own gunner/sentinel shot —
        # the engine treats friendly bots as LoS obstacles. Don't
        # attack from inside one of our turrets' kill lanes.
        if pos in state.friendly_turret_ray_tiles:
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
        # Soft-deprioritise tiles that sit in an enemy gunner/sentinel
        # firing ray. We don't filter them out — sometimes the only
        # way to hit the harvester is to cross a ray — but we'd rather
        # stand somewhere safer if equivalent on cost and distance.
        in_ray = 1 if pos in state.enemy_turret_ray_tiles else 0
        dist = my_pos.distance_squared(pos)
        candidates.append((in_ray, cost, dist, pos))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][3]


def _gunner_chain_facing(
    state: State, ct: Controller, pos: Position
) -> Direction | None:
    """Return a direction (any of DIR8) such that a gunner placed at
    `pos` facing that way has an enemy conveyor/splitter/bridge as
    the first building in its forward ray. Used to position gunners
    next to enemy harvesters so they eat the harvester's output
    chain tile-by-tile.

    Ray semantics: walk the direction out to r²=13, stop at the
    first wall or building. Only success case is "first building is
    enemy transport"; friendly buildings or non-transport enemies
    (including the harvester itself) block the shot and disqualify
    this direction — so the "don't face into the harvester" constraint
    is enforced implicitly by the isinstance check.
    """
    team = ct.get_team()
    r_sq = GameConstants.GUNNER_VISION_RADIUS_SQ
    for d in DIR8:
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
    if state.attack_tile_blacklist:
        state.attack_tile_blacklist = {
            p: n - 1 for p, n in state.attack_tile_blacklist.items() if n > 1
        }
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
        # Target preference, in order:
        #   1. closest harvester with no enemy healer in range AND
        #      no friendly bot already attacking it — spreads us
        #      across lightly-contested targets.
        #   2. closest with no enemy healer in range (dogpiles if we
        #      have to, but avoids healers).
        #   3. closest of all (last resort).
        my_pos = ct.get_position()
        sorted_harvesters = sorted(
            vulnerable_harvesters,
            key=my_pos.distance_squared,
        )
        target = None
        for h in sorted_harvesters:
            if not _enemy_healer_near(ct, h) and not _friendly_bot_adjacent(ct, h):
                target = h
                break
        if target is None:
            for h in sorted_harvesters:
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
                    # Don't come back to this tile for 5 turns — the
                    # enemy healer in range will just out-heal us
                    # again. Let the picker try a different neighbour
                    # (or a different harvester entirely once this
                    # tile is off the table).
                    state.attack_tile_blacklist[my_pos] = 5
                    alt = _pick_attack_destination(state, ct, target)
                    if alt is not None and alt != my_pos:
                        state.last_fire_pos = None
                        make_move(state, ct, alt)
                        return
                # Always fire — maintain pressure even if an enemy
                # healer is nearby. being_healed detection (above)
                # handles rotation when we're truly outpaced.
                bid_here = ct.get_tile_building_id(my_pos)
                if bid_here is not None:
                    pre_hp = ct.get_hp(bid_here)
                    state.last_fire_pos = my_pos
                    state.last_fire_expected_hp = max(0, pre_hp - 2)
                try_attack(ct)
                state.offense_target = my_pos
                state.offense_turns = 0

            else:
                build_position = ct.get_position()
                move_random(state, ct)
                direction = build_position.direction_to(enemy_core)
                if direction == build_position.direction_to(target):
                    direction = direction.rotate_right()

                # Cap turrets adjacent to the target harvester at
                # 2 gunners + 1 sentinel. Gunners eat the enemy
                # conveyor chain tile-by-tile along their ray; stacking
                # a second gunner on the opposite side roughly doubles
                # chain pressure. Sentinel applies harvester pressure.
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

                if n_gunner < 2:
                    gdir = _gunner_chain_facing(state, ct, build_position)
                    if gdir is not None:
                        try_place(ct, EntityType.GUNNER, build_position, gdir)

                if (
                    n_sentinel == 0
                    and state.get_env(target) == Environment.ORE_TITANIUM
                ):
                    try_place(ct, EntityType.SENTINEL, build_position, direction)

                if ct.can_build_road(build_position) and not state.get_building(
                    build_position
                ):
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

        if ct.get_position().distance_squared(target) == 1 and state.is_enemy_building(
            ct.get_position()
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
        # No vulnerable harvester and no cached offense target —
        # spread out to an enemy conveyor target instead. Prefer
        # core-proximal flow tiles, then visible-flow tiles. Spacing
        # score keeps us away from our other attackers so a single
        # enemy healer can't cover two of us.
        conveyor_target = _pick_conveyor_target(
            state, ct, enemy_core, ct.get_position()
        )
        if conveyor_target is not None:
            if ct.get_position() == conveyor_target:
                try_attack(ct)
            else:
                make_move(state, ct, conveyor_target)
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
