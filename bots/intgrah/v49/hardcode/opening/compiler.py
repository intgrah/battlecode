__all__ = ["CompiledActionMove", "CompiledMoveAction", "CompiledTurn", "dsl_compile"]

from dataclasses import dataclass

from builder.build import (
    Action,
    Fire,
    Heal,
    PlaceArmouredConveyor,
    PlaceBarrier,
    PlaceBridge,
    PlaceConveyor,
    PlaceFoundry,
    PlaceGunner,
    PlaceHarvester,
    PlaceLauncher,
    PlaceRoad,
    PlaceSentinel,
    PlaceSplitter,
    SelfDestruct,
)
from cambc import Direction, Position

from .dsl import (
    DslAction,
    DslActionMove,
    DslFire,
    DslHeal,
    DslMoveAction,
    DslPlaceArmouredConveyor,
    DslPlaceBarrier,
    DslPlaceBridge,
    DslPlaceConveyor,
    DslPlaceFoundry,
    DslPlaceGunner,
    DslPlaceHarvester,
    DslPlaceLauncher,
    DslPlaceRoad,
    DslPlaceSentinel,
    DslPlaceSplitter,
    DslSelfDestruct,
    DslTurn,
)


@dataclass(frozen=True, slots=True)
class CompiledActionMove:
    action: Action | None
    move: Direction | None


@dataclass(frozen=True, slots=True)
class CompiledMoveAction:
    move: Direction | None
    action: Action | None


type CompiledTurn = CompiledMoveAction | CompiledActionMove


def _compile_action(dsl: DslAction, pos: Position) -> Action:
    match dsl:
        case DslPlaceRoad(direction):
            return PlaceRoad(pos.add(direction))
        case DslPlaceHarvester(direction):
            return PlaceHarvester(pos.add(direction))
        case DslPlaceConveyor(direction, building_direction):
            return PlaceConveyor(pos.add(direction), building_direction)
        case DslPlaceArmouredConveyor(direction, building_direction):
            return PlaceArmouredConveyor(pos.add(direction), building_direction)
        case DslPlaceBridge(direction, target_vector):
            build_pos = pos.add(direction)
            target = Position(
                build_pos.x + target_vector[0],
                build_pos.y + target_vector[1],
            )
            return PlaceBridge(build_pos, target)
        case DslPlaceFoundry(direction):
            return PlaceFoundry(pos.add(direction))
        case DslPlaceSplitter(direction, building_direction):
            return PlaceSplitter(pos.add(direction), building_direction)
        case DslPlaceBarrier(direction):
            return PlaceBarrier(pos.add(direction))
        case DslPlaceSentinel(direction, building_direction):
            return PlaceSentinel(pos.add(direction), building_direction)
        case DslPlaceLauncher(direction):
            return PlaceLauncher(pos.add(direction))
        case DslPlaceGunner(direction, building_direction):
            return PlaceGunner(pos.add(direction), building_direction)
        case DslHeal(direction):
            return Heal(pos.add(direction))
        case DslSelfDestruct():
            return SelfDestruct()
        case DslFire():
            return Fire()


def _advance_pos(pos: Position, direction: Direction | None) -> Position:
    if direction is None:
        return pos
    return pos.add(direction)


def dsl_compile(start: Position, script: list[DslTurn]) -> list[CompiledTurn]:
    result: list[CompiledTurn] = []
    pos = start

    for turn in script:
        match turn:
            case DslActionMove(action, move):
                compiled_action = (
                    _compile_action(action, pos) if action is not None else None
                )
                result.append(CompiledActionMove(compiled_action, move))
                pos = _advance_pos(pos, move)
            case DslMoveAction(move, action):
                pos = _advance_pos(pos, move)
                compiled_action = (
                    _compile_action(action, pos) if action is not None else None
                )
                result.append(CompiledMoveAction(move, compiled_action))

    return result
