"""Core unit — spawns builder bots and assigns roles via markers."""

from __future__ import annotations

from cambc import Controller, GameConstants, Position
from marker import MarkerRole
from unit import Unit
from util import BUILDER_CAP, DIR8, ROLE_SCHEDULE, Role


class Core(Unit):
    def __init__(self, ct: Controller) -> None:
        self.core_pos: Position = ct.get_position()
        self.spawned: int = 0

    def run(self, ct: Controller) -> None:
        if ct.get_action_cooldown() != 0:
            return

        ti, _ = ct.get_global_resources()
        builder_cost, _ = ct.get_builder_bot_cost()

        alive_builders = ct.get_unit_count() - 1  # exclude core
        if alive_builders >= BUILDER_CAP:
            return

        # Emergency: enemy units nearby — spawn immediately if affordable
        my_team = ct.get_team()
        emergency = False
        for uid in ct.get_nearby_units():
            if ct.get_team(uid) != my_team:
                emergency = True
                break
        if emergency and ti >= builder_cost:
            self._try_spawn(ct, ti, builder_cost, reserve=0)
            return

        # Reserve logic: first 3 spawns are free, then hold back for econ
        if self.spawned < 3:
            reserve = 0
        else:
            harvester_cost, _ = ct.get_harvester_cost()
            conveyor_cost, _ = ct.get_conveyor_cost()
            reserve = harvester_cost + conveyor_cost * 3

        if ti >= builder_cost + reserve:
            self._try_spawn(ct, ti, builder_cost, reserve)

    def _try_spawn(
        self,
        ct: Controller,
        ti: int,
        builder_cost: int,
        reserve: int,
    ) -> None:
        if ti < builder_cost + reserve:
            return

        spawn_pos = _best_spawn_pos(ct, self.core_pos)
        if spawn_pos is None:
            return

        ct.spawn_builder(spawn_pos)

        # Determine role from schedule
        idx = min(self.spawned, len(ROLE_SCHEDULE) - 1)
        role = ROLE_SCHEDULE[idx]
        # Spawns beyond the schedule default to RUSH
        if self.spawned >= len(ROLE_SCHEDULE):
            role = Role.RUSH

        marker = MarkerRole(
            role=role.value,
            birthday=ct.get_current_round() % 2048,
            turn=ct.get_current_round(),
        )

        # Place marker on a core tile that is NOT the spawn tile
        _place_role_marker(ct, self.core_pos, spawn_pos, marker)

        self.spawned += 1


def _best_spawn_pos(ct: Controller, core_pos: Position) -> Position | None:
    """Pick the best spawnable tile around the core.

    Tries all 8 directions, preferring the first available.
    """
    for d in DIR8:
        sp = core_pos.add(d)
        if ct.can_spawn(sp):
            return sp
    return None


def _place_role_marker(
    ct: Controller,
    core_pos: Position,
    spawn_pos: Position,
    marker: MarkerRole,
) -> None:
    """Place a role-assignment marker on a core tile (not the spawn tile).

    The newly spawned builder will read this marker on its first turn
    to learn its assigned role.
    """
    encoded = marker.encode()

    # Try core_pos itself first
    if core_pos != spawn_pos and ct.can_place_marker(core_pos):
        ct.place_marker(core_pos, encoded)
        return

    # Try tiles within core action radius, avoiding the spawn tile
    for t in ct.get_nearby_tiles(GameConstants.CORE_ACTION_RADIUS_SQ):
        if t == spawn_pos:
            continue
        if ct.can_place_marker(t):
            ct.place_marker(t, encoded)
            return
