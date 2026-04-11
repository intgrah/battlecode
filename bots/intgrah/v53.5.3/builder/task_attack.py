from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingHarvester,
    BuildingLauncher,
    BuildingSentinel,
    BuildingSplitter,
)
from cambc import (
    Controller,
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

from builder.helpers import (
    get_enemy_core_pos,
    make_move,
    move_random,
    try_attack,
    try_place,
)
from builder.state import State
from builder.task_explore import task_xplore


def open_tiles(
    state: State, ct: Controller, positions: list[Position]
) -> list[Position]:
    return [
        p
        for p in positions
        if state.in_bounds(p)
        and state.is_passable(p)
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


def should_attack(state: State, ct: Controller, pos: Position) -> bool:
    enemy_builder = nearest_enemy_bot(ct)
    i = state._idx(pos)
    return (
        (enemy_builder is None)
        or chebyshev(ct.get_position(), enemy_builder) > 2
        or state.hp[i] <= state.max_hp[i] - 4
        or state.hp[i] <= 4
        or can_afford(ct, EntityType.HARVESTER)
    )


def task_attack(state: State, ct: Controller) -> None:
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
        target = closest(ct.get_position(), vulnerable_harvesters)
        on_friendly_conveyor = is_allied_transport(state, ct, ct.get_position())
        if ct.get_position().distance_squared(target) == 1 and not on_friendly_conveyor:
            if state.is_enemy_building(ct.get_position()):
                if should_attack(state, ct, ct.get_position()):
                    try_attack(ct)
                state.offense_target = ct.get_position()
                state.offense_turns = 0

            else:
                build_position = ct.get_position()
                move_random(state, ct)
                direction = build_position.direction_to(enemy_core)
                if direction == build_position.direction_to(target):
                    direction = direction.rotate_right()
                if state.get_env(target) == Environment.ORE_TITANIUM:
                    num_existing_sentinels = 0
                    for d in DIR4:
                        nb = state.get_building(target.add(d))
                        if (
                            isinstance(nb, BuildingSentinel)
                            and nb.team == ct.get_team()
                        ):
                            num_existing_sentinels += 1
                    if num_existing_sentinels < 2:
                        try_place(ct, EntityType.SENTINEL, build_position, direction)
                    else:
                        try_place(ct, EntityType.BARRIER, build_position)
                elif state.get_env(target) == Environment.ORE_AXIONITE:
                    try_place(ct, EntityType.BARRIER, build_position)
                else:
                    try_place(ct, EntityType.BARRIER, build_position)
                if ct.can_build_road(build_position):
                    ct.build_road(build_position)
                scout_toward_enemy(state, ct)

        else:
            destination = closest(
                ct.get_position(),
                without_allied_transport(
                    state,
                    ct,
                    open_tiles(state, ct, [target.add(d) for d in DIR4]),
                ),
            )
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
        task_xplore(state, ct)
    else:
        dir8 = DIR8[:]
        state.rng.shuffle(dir8)
        my_pos = ct.get_position()
        for d in dir8:
            if try_move(ct, my_pos.add(d)):
                break
