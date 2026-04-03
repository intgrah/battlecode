from action import ActionOnly, Heal, Turn
from cambc import Controller, EntityType, Position

from .helpers import move_toward_with_road, nearest_reachable_around
from .state import State

_ECON_TYPES = frozenset(
    (
        EntityType.HARVESTER,
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
        EntityType.BRIDGE,
        EntityType.FOUNDRY,
    ),
)


def heal_econ(
    state: State,
    ct: Controller,
) -> Turn | None:
    my_team = ct.get_team()
    candidates: list[tuple[float, Position]] = []
    for bid in ct.get_nearby_buildings():
        if ct.get_team(bid) != my_team:
            continue
        if ct.get_entity_type(bid) not in _ECON_TYPES:
            continue
        hp = ct.get_hp(bid)
        max_hp = ct.get_max_hp(bid)
        if hp >= max_hp:
            continue
        candidates.append((hp / max_hp, ct.get_position(bid)))

    candidates.sort()
    for _, target in candidates:
        if ct.can_heal(target):
            print(f"    heal_econ: heal ({target.x},{target.y})")
            return ActionOnly(Heal(target))

        adj = nearest_reachable_around(state, target)
        if adj is None:
            continue
        result = move_toward_with_road(state, ct, adj)
        if result is None:
            continue
        print(f"    heal_econ: nav to ({target.x},{target.y})")
        ct.draw_indicator_line(state.pos, target, 0, 255, 0)
        return result

    return None
