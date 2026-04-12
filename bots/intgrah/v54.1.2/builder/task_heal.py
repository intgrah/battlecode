from cambc import Controller, EntityType, Position
from util import DIR8, chebyshev

from .helpers import make_move, move_random, try_heal
from .state import State


def _count_visible_attackers(ct: Controller, my_team, target: Position) -> int:
    """Count enemy builder bots currently in attack range of `target`
    (builder bots fire at their own tile, so anyone within 1 king-step
    of target is potentially dealing 2 dmg/turn to it).

    Bounds guards are load-bearing — same OOB crash mode as
    `_enemy_healer_near` in task_attack.
    """
    n = 0
    w = ct.get_map_width()
    h = ct.get_map_height()
    for d in DIR8:
        p = target.add(d)
        if not (0 <= p.x < w and 0 <= p.y < h):
            continue
        if ct.is_in_vision(p):
            uid = ct.get_tile_builder_bot_id(p)
            if uid is not None and ct.get_team(uid) != my_team:
                n += 1
    if 0 <= target.x < w and 0 <= target.y < h and ct.is_in_vision(target):
        uid = ct.get_tile_builder_bot_id(target)
        if uid is not None and ct.get_team(uid) != my_team:
            n += 1
    return n


def _deconflict_rank(
    ct: Controller, my_team, my_id: int, my_pos: Position, target: Position
) -> int:
    """Count visible friendly builder bots with STRICT priority to
    heal `target` over us — strictly closer by chebyshev, or tied
    with a smaller id. Every bot running this with the same visible
    state gets the same answer, so the top-N closest consistently
    commit and the rest defer."""
    my_d = chebyshev(my_pos, target)
    rank = 0
    for uid in ct.get_nearby_units():
        if uid == my_id:
            continue
        if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
            continue
        if ct.get_team(uid) != my_team:
            continue
        fp = ct.get_position(uid)
        fd = chebyshev(fp, target)
        if fd < my_d or (fd == my_d and uid < my_id):
            rank += 1
    return rank


def _healers_needed(attackers: int) -> int:
    """Healers required to outpace `attackers` hitting a single tile.
    Attackers deal 2 dmg/turn each, healers restore 4 hp/turn each,
    so break-even is ceil(attackers/2). Always at least 1 — one bot
    still comes for chip damage even with no visible attacker."""
    if attackers <= 1:
        return 1
    return (attackers + 1) // 2


def best_healable_building(state: State, ct: Controller) -> Position | None:
    """Pick the most valuable reachable damaged friendly building with
    attacker-aware deconfliction and priority for harvester-adjacent
    infrastructure.

    Deconfliction: each bot ranks itself by chebyshev distance against
    visible friendly builders; only the top-`ceil(attackers/2)` closest
    commit to a target. Others defer to handle a different target.

    Tier structure:
      3 — harvester-adjacent tile, ANY damage, reachable in time
      2 — ordinary damaged building ≥4 HP missing, reachable
      1 — ordinary damaged building ≥4 HP missing, NOT reachable
      0 — minor chip damage on a non-critical tile

    Reach time = chebyshev - 1 (heal range is r²≤2; we only need to
    get adjacent, not on the tile).
    """
    best: Position | None = None
    best_score: tuple[int, int, int] = (0, 0, 0)
    my_pos = ct.get_position()
    my_id = ct.get_id()
    my_team = ct.get_team()
    for pos in state.healable_buildings:
        i = state._idx(pos)
        hp = state.hp[i]
        max_hp = state.max_hp[i]
        damage = max_hp - hp
        if damage <= 0:
            continue

        attackers = _count_visible_attackers(ct, my_team, pos)
        needed = _healers_needed(attackers)
        rank = _deconflict_rank(ct, my_team, my_id, my_pos, pos)
        if rank >= needed:
            if not ct.is_in_vision(pos):
                state.hp[i] = max_hp
            continue

        dist = chebyshev(my_pos, pos)
        turns_to_reach = max(0, dist - 1)
        dmg_per_turn = max(2, attackers * 2)
        turns_to_die = max(1, hp // dmg_per_turn)
        # Allow 1 turn of slippage: even after the tile dies, a single
        # enemy attacker needs turns to fire+destroy+rebuild, so we
        # can still slot in a replacement tile. Multiple attackers
        # overwhelm this, but attackers scales dmg_per_turn above.
        can_reach = turns_to_reach <= turns_to_die + 1
        is_critical = pos in state.adjacent_to_harvester

        if is_critical and can_reach:
            tier = 3
        elif damage >= 4 and can_reach:
            tier = 2
        elif damage >= 4:
            tier = 1
        else:
            tier = 0
        score = (tier, damage, turns_to_die - turns_to_reach)

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


def heal_builders(state: State, ct: Controller) -> bool:
    b = state.get_building(ct.get_position())
    if b and b.team != ct.get_team():
        i = state._idx(ct.get_position())
        if state.hp[i] <= 2:
            return False
        if state.hp[i] <= 6 and ct.get_hp() > 18:
            return False
    return bool(heal_adjacent_builders(state, ct) or heal_self(state, ct))
