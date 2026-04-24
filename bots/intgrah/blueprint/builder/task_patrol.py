from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Controller, Direction, Position

from builder.helpers import make_move

if TYPE_CHECKING:
    from builder import Builder


def trace_upstream(self: Builder, position: Position) -> list[Position]:
    path: list[Position] = []
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


def core_feeders(self: Builder) -> list[Position]:
    return [
        pos
        for d in Direction
        for pos in self.get_conveyors_to_here(self.my_core.add(d))
    ]


def run_patrol(self: Builder, ct: Controller) -> bool:
    if self.patrol_head:
        if self.my_pos.distance_squared(self.patrol_head) > PATROL_RANGE:
            make_move(self, ct, self.patrol_head)
            return True
        conveyors = self.get_conveyors_to_here(self.patrol_head)
        if len(conveyors) == 0:
            self.patrol_head = None
            self.patrol_trail = []
            make_move(self, ct, self.my_core)
            return True
        while (
            len(conveyors) > 0
            and self.my_pos.distance_squared(self.patrol_head) <= PATROL_RANGE
        ):
            self.rng.shuffle(conveyors)
            self.patrol_head = conveyors[0]
            conveyors = self.get_conveyors_to_here(self.patrol_head)
            if self.patrol_head in self.patrol_trail:
                self.patrol_head = None
                self.patrol_trail = []
                make_move(self, ct, self.my_core)
                return True
            self.patrol_trail.append(self.patrol_head)
        make_move(self, ct, self.patrol_head)
        return True
    if self.my_pos == self.my_core or (
        self.my_pos.distance_squared(self.my_core) <= 8
        and not ct.can_move(self.my_pos.direction_to(self.my_core))
    ):
        conveyors = core_feeders(self)
        if len(conveyors) > 0:
            self.rng.shuffle(conveyors)
            self.patrol_head = conveyors[0]
            self.patrol_trail = []
            make_move(self, ct, self.patrol_head)
            return True
        return False
    make_move(self, ct, self.my_core)
    return True
