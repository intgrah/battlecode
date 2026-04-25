from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import EntityType
from util.debug import debug as log
from util.directions import DIR8

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


def end_of_turn_heal(self: Builder, ct: Controller) -> None:
    """Opportunistic end-of-turn healing. Heal is a separate action from
    the task action, so we spend it after whatever the task chose. Order:
    1. Self, if damaged (healing is targeted at the builder's own tile).
    2. Visible friendly non-core unit (bot / turret) on a healable tile,
       if damaged — heal is applied to the unit's position.
    3. Core — 3x3 block, heal is tile-targeted but core shares HP across
       all 9 tiles, so we pick any DIR8 cardinal of the core centre that's
       in action range."""
    my_pos = ct.get_position()  # Cannot use self.my_pos since that's the start of turn position, not the current one necessarily..
    if ct.can_heal(my_pos) and ct.get_hp() < ct.get_max_hp():
        log(f"end_of_turn_heal: self at {my_pos}")
        ct.heal(my_pos)
    for unit in ct.get_nearby_units():
        if ct.get_team(unit) != self.my_team:
            continue
        if ct.get_hp(unit) >= ct.get_max_hp(unit):
            continue
        if ct.get_entity_type(unit) == EntityType.CORE:
            for d in DIR8:
                heal_pos = ct.get_position(unit).add(d)
                if ct.can_heal(heal_pos):
                    log(f"end_of_turn_heal: core at {heal_pos}")
                    ct.heal(heal_pos)
                    break
        elif ct.can_heal(ct.get_position(unit)):
            unit_pos = ct.get_position(unit)
            log(f"end_of_turn_heal: friendly unit at {unit_pos}")
            ct.heal(unit_pos)
