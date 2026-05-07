from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Controller, EntityType

from .helpers import make_move, make_multi_move

from util import DIR8

if TYPE_CHECKING:
    from builder import Builder, PosInt


def trace_upstream(self: Builder, position: PosInt) -> list[PosInt]:
    path: list[PosInt] = []
    conveyors = [position]
    while len(conveyors) > 0:
        self.rng.shuffle(conveyors)
        position = conveyors[0]
        conveyors = self.get_conveyors_to_here(position)
        if position in path:
            break
        path.append(position)
    return path


PATROL_RANGE = 4


def core_feeders(self: Builder) -> list[PosInt]:
    return self.get_conveyors_to_here(self.my_core) + [
        pos for d in DIR8 for pos in self.get_conveyors_to_here(self.my_core + d)
    ]


def run_patrol(self: Builder, ct: Controller) -> bool:
    my_team = self.my_team
    c_rnd = self.rnd

    if self.patrol_head >= 0 and ct.is_in_vision(self.pos(self.patrol_head)):
        for unit in ct.get_nearby_units():
            if (
                ct.get_entity_type(unit) != EntityType.BUILDER_BOT
                or ct.get_team(unit) != my_team
            ):
                continue
            if (
                self.sq_dist(self._idx(ct.get_position(unit)), self.patrol_head)
                <= PATROL_RANGE
            ):
                self.patrol_head = -1
                break

    if self.patrol_head < 0 and self.patrol_queue:
        self.patrol_head = max(self.patrol_queue, key=lambda v: (c_rnd - v[1]) * v[2])[
            0
        ]

    if self.patrol_head >= 0:
        make_move(self, ct, self.patrol_head)

    return bool(self.patrol_queue)
