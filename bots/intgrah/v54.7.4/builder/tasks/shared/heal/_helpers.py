"""Shared helpers for the heal leaves: enemy-attacker counting,
multi-builder deconfliction, healer-count math, wounded-enemy detection,
and the "I'm low-HP on an enemy tile, fight to death instead of heal"
bail-out gate that all three leaves consult.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import EntityType
from util.metrics import chebyshev

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


def count_visible_attackers(self: Builder, target: Position) -> int:
    """Count enemy builder bots currently in attack range of `target`
    (builder bots fire at their own tile, so anyone within 1 king-step
    of target is potentially dealing 2 dmg/turn to it).
    """
    return sum(1 for p in self.enemy_bots if p.distance_squared(target) <= 2)


def deconflict_rank(
    self: Builder,
    ct: Controller,
    my_pos: Position,
    target: Position,
) -> int:
    """Count visible friendly builder bots with STRICT priority to heal
    `target` over us — strictly closer by chebyshev, or tied with a
    smaller id. Every bot running this with the same visible self gets
    the same answer, so the top-N closest consistently commit and the
    rest defer.
    """
    my_d = chebyshev(my_pos, target)
    rank = 0
    for uid in ct.get_nearby_units():
        if uid == self.my_id:
            continue
        if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
            continue
        if ct.get_team(uid) != self.my_team:
            continue
        fp = ct.get_position(uid)
        fd = chebyshev(fp, target)
        if fd < my_d or (fd == my_d and uid < self.my_id):
            rank += 1
    return rank


def healers_needed(attackers: int) -> int:
    """Healers required to outpace `attackers` hitting a single tile.
    Attackers deal 2 dmg/turn each, healers restore 4 hp/turn each, so
    break-even is ceil(attackers/2). Always at least 1 — one bot still
    comes for chip damage even with no visible attacker.
    """
    if attackers <= 1:
        return 1
    return (attackers + 1) // 2


def has_wounded_enemy(self: Builder, position: Position) -> bool:
    """True iff `position` hosts a damaged enemy building. Used to
    detect tiles where a friendly builder is mid-kill and shouldn't be
    pulled away by a heal.
    """
    b = self.get_building(position)
    if not b:
        return False
    i = self.idx(position)
    return b.team != self.my_team and self.hp[i] < self.max_hp[i]


def fight_to_death(self: Builder, ct: Controller) -> bool:
    """True iff we're standing on an enemy building at low HP and
    should spend our remaining actions firing rather than healing.
    Mirrors the gate at the top of `_heal_builders` in the legacy file:
    bail out of any heal when we're at HP<=2 (on enemy tile), or HP<=6
    while still mostly intact (>18 HP max means we're probably a fresh
    bot still committing to the kill).
    """
    b = self.get_building(self.my_pos)
    if not (b and b.team != self.my_team):
        return False
    i = self.idx(self.my_pos)
    if self.hp[i] <= 2:
        return True
    return self.hp[i] <= 6 and ct.get_hp() > 18
