from cambc import Controller, Direction

from .action import Action, SelfDestruct
from .state import State


def self_destruct(
    _state: State,
    _ct: Controller,
) -> tuple[Direction, Action | None] | None:
    return Direction.CENTRE, SelfDestruct()
