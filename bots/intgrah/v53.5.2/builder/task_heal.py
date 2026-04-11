from cambc import Controller, Position
from util import DIR8, chebyshev

from .helpers import make_move, move_random, try_heal
from .state import State


def best_healable_building(state: State, ct: Controller) -> Position | None:
    best: Position | None = None
    best_score: tuple[int, int, int] = (0, 0, 0)
    for pos in state.healable_buildings:
        i = state._idx(pos)
        hp = state.hp[i]
        max_hp = state.max_hp[i]
        damage = max_hp - hp
        dist = chebyshev(ct.get_position(), pos)
        turns_to_die = hp // 2
        if damage < 5 and ct.get_position().distance_squared(pos) > 2:
            closer_friend = False
            for d in DIR8:
                test_position = pos.add(d)
                if state.in_bounds(test_position) and ct.is_in_vision(test_position):
                    builder = ct.get_tile_builder_bot_id(test_position)
                    if builder is not None and ct.get_team(builder) == ct.get_team():
                        closer_friend = True
                        state.ally_sightings[test_position] = ct.get_current_round()
                    elif test_position in state.ally_sightings:
                        del state.ally_sightings[test_position]
                elif (
                    test_position in state.ally_sightings
                    and ct.get_current_round() - state.ally_sightings[test_position] < 4
                ):
                    closer_friend = True

            if closer_friend:
                if not ct.is_in_vision(pos):
                    state.hp[i] = max_hp
                continue

        if damage < 4:
            tier = 0
        elif turns_to_die >= dist:
            tier = 2
        else:
            tier = 1
        score = (tier, damage, turns_to_die - dist)

        if score > best_score:
            best = pos
            best_score = score
    state.healable_buildings = [
        p
        for p in state.healable_buildings
        if state.hp[state._idx(p)] < state.max_hp[state._idx(p)]
    ]
    return best


def best_adjacent_healable_building(state: State, ct: Controller) -> Position | None:
    best: Position | None = None
    best_score: tuple[int, int] = (0, 0)
    for pos in state.healable_buildings:
        i = state._idx(pos)
        hp = state.hp[i]
        max_hp = state.max_hp[i]
        damage = max_hp - hp
        if ct.get_position().distance_squared(pos) > 2:
            continue
        score = (0, damage) if damage < 4 else (1, damage)
        if score > best_score:
            best = pos
            best_score = score
    return best


def run_heal(state: State, ct: Controller) -> bool:
    if state.repair_pos and ct.is_in_vision(state.repair_pos):
        b = state.get_building(state.repair_pos)
        ti = state._idx(state.repair_pos)
        if b and state.hp[ti] < state.max_hp[ti] - 2 and b.team == ct.get_team():
            pass
        else:
            state.repair_pos = None
    repair_pos = best_healable_building(state, ct)
    if (
        repair_pos and repair_pos.distance_squared(ct.get_position()) <= 2
    ) or not state.repair_pos:
        state.repair_pos = repair_pos

    if not state.repair_pos:
        return False

    being_attacked = False
    heal_position = state.repair_pos
    if ct.is_in_vision(heal_position):
        builder = ct.get_tile_builder_bot_id(heal_position)
        being_attacked = builder is not None and ct.get_team(builder) != ct.get_team()

    building_to_heal = best_adjacent_healable_building(state, ct)
    save_money = being_attacked and state.repaired_prev
    if building_to_heal:
        state.repaired_prev = try_heal(
            state, ct, building_to_heal, conserve_ti=save_money
        )
    else:
        state.repaired_prev = False
    make_move(state, ct, state.repair_pos)
    building_to_heal = best_adjacent_healable_building(state, ct)
    if building_to_heal:
        state.repaired_prev = (
            try_heal(state, ct, building_to_heal, conserve_ti=save_money)
            or state.repaired_prev
        )
    return True


def has_wounded_enemy(state: State, ct: Controller, position: Position) -> bool:
    b = state.get_building(position)
    if not b:
        return False
    i = state._idx(position)
    return b.team != ct.get_team() and state.hp[i] < state.max_hp[i]


def heal_adjacent_builders(state: State, ct: Controller) -> bool:
    adjacent_builders = ct.get_nearby_units(2)
    for eid in adjacent_builders:
        if (ct.get_hp(eid) <= ct.get_max_hp(eid) - 4) and ct.get_team(
            eid
        ) == ct.get_team():
            position = ct.get_position(eid)
            if has_wounded_enemy(state, ct, position):
                continue
            if try_heal(state, ct, position, conserve_ti=False):
                return True
    return False


def heal_self(state: State, ct: Controller) -> bool:
    if ct.get_hp() > ct.get_max_hp() - 4:
        return False

    my_pos = ct.get_position()
    if not has_wounded_enemy(state, ct, my_pos):
        try_heal(state, ct, my_pos, conserve_ti=False)
        move_random(state, ct)
        return True

    for d in DIR8:
        if ct.can_move(d) and not has_wounded_enemy(state, ct, my_pos.add(d)):
            ct.move(d)
            try_heal(state, ct, ct.get_position(), conserve_ti=False)
            return True

    return False


def task_heal(state: State, ct: Controller) -> bool:
    b = state.get_building(ct.get_position())
    if b and b.team != ct.get_team():
        i = state._idx(ct.get_position())
        if state.hp[i] <= 2:
            return False
        if state.hp[i] <= 6 and ct.get_hp() > 18:
            return False
    return bool(heal_adjacent_builders(state, ct) or heal_self(state, ct))
