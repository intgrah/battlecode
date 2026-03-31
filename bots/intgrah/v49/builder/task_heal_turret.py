from cambc import Controller, Direction, EntityType, GameConstants, Position

from .build import Action, Heal
from .helpers import move_toward_with_road
from .state import State

_TURRET_TYPES = frozenset(
    (
        EntityType.GUNNER,
        EntityType.SENTINEL,
        EntityType.BREACH,
        EntityType.LAUNCHER,
    ),
)


def _find_damaged_turret(ct: Controller) -> Position | None:
    my_team = ct.get_team()
    best: Position | None = None
    best_hp_frac = 1.0
    for bid in ct.get_nearby_buildings():
        if ct.get_team(bid) != my_team:
            continue
        if ct.get_entity_type(bid) not in _TURRET_TYPES:
            continue
        hp = ct.get_hp(bid)
        max_hp = ct.get_max_hp(bid)
        if hp >= max_hp:
            continue
        frac = hp / max_hp
        if frac < best_hp_frac:
            best_hp_frac = frac
            best = ct.get_position(bid)
    return best


def heal_turret(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    target = _find_damaged_turret(ct)
    if target is None:
        return None

    pos = state.pos
    if pos.distance_squared(target) <= GameConstants.ACTION_RADIUS_SQ and ct.can_heal(
        target,
    ):
        return Direction.CENTRE, Heal(target)

    move, build = move_toward_with_road(state, ct, target)
    state.debug_target = (target, 255, 0, 0)
    return move, build
