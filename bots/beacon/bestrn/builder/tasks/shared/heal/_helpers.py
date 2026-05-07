"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/shared/heal/_helpers.py`.

Shared helpers for the heal leaves: enemy-attacker counting,
multi-builder deconfliction, healer-count math, wounded-enemy detection,
and the "I'm low-HP on an enemy tile, fight to death instead of heal"
bail-out gate that all three leaves consult.
"""

from __future__ import annotations

from cambc import EntityType
from util.metrics import chebyshev


def count_visible_attackers(self_, target):
    """
    Count enemy builder bots currently in attack range of `target`
    (builder bots fire at their own tile, so anyone within 1 king-step
    of target is potentially dealing 2 dmg/turn to it).
    """
    n = 0
    for p in self_.enemy_bots:
        if p.distance_squared(target) <= 2:
            n += 1
    return n


def deconflict_rank(self_, ct, my_pos, target):
    """
    Count visible friendly builder bots with STRICT priority to heal
    `target` over us — strictly closer by chebyshev, or tied with a
    smaller id. Every bot running this with the same visible self gets
    the same answer, so the top-N closest consistently commit and the
    rest defer.
    """
    my_d = chebyshev(my_pos, target)
    rank = 0
    for uid in ct.get_nearby_units(None):
        if uid == self_.my_id:
            continue
        if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
            continue
        if ct.get_team(uid) != self_.my_team:
            continue
        fp = ct.get_position(uid)
        fd = chebyshev(fp, target)
        if fd < my_d or (fd == my_d and uid < self_.my_id):
            rank += 1
    return rank


def healers_needed(attackers):
    """
    Healers required to outpace `attackers` hitting a single tile.

    Attackers deal 2 dmg/turn each, healers restore 4 hp/turn each, so
    break-even is ceil(attackers/2). Always at least 1 — one bot still
    comes for chip damage even with no visible attacker.
    """
    if attackers <= 1:
        return 1
    return (attackers + 1) // 2


def has_wounded_enemy(self_, position):
    """
    True iff `position` hosts a damaged enemy building. Used to
    detect tiles where a friendly builder is mid-kill and shouldn't be
    pulled away by a heal.
    """
    __opt_tuple = self_.get_building(position)
    if __opt_tuple is None:
        return False
    _kind, team = __opt_tuple
    i = self_.idx(position)
    return team != self_.my_team and self_.hp[i] < self_.max_hp[i]


def fight_to_death(self_, ct):
    """
    True iff we're standing on an enemy building at low HP and
    should spend our remaining actions firing rather than healing.
    Mirrors the gate at the top of `_heal_builders` in the legacy file:
    bail out of any heal when we're at HP<=2 (on enemy tile), or HP<=6
    while still mostly intact (>18 HP max means we're probably a fresh
    bot still committing to the kill).
    """
    __opt_tuple = self_.get_building(self_.my_pos)
    if __opt_tuple is None:
        return False
    _kind, team = __opt_tuple
    if team == self_.my_team:
        return False
    i = self_.idx(self_.my_pos)
    if self_.hp[i] <= 2:
        return True
    return self_.hp[i] <= 6 and ct.get_hp(None) > 18
