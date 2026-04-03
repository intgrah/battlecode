from action import (
    Action,
    ActionMove,
    ActionOnly,
    Fire,
    Heal,
    MoveAction,
    MoveOnly,
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
    Turn,
)
from cambc import Position

from .dsl import (
    DslAction,
    DslActionMove,
    DslActionOnly,
    DslFire,
    DslHeal,
    DslMoveAction,
    DslMoveOnly,
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
    DslWait,
)

__all__ = ["dsl_compile"]


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


def dsl_compile(start: Position, script: list[DslTurn]) -> list[Turn | None]:
    result: list[Turn | None] = []
    pos = start

    for turn in script:
        match turn:
            case DslWait():
                result.append(None)
            case DslActionOnly(action):
                result.append(ActionOnly(_compile_action(action, pos)))
            case DslMoveOnly(move):
                result.append(MoveOnly(move))
                pos = pos.add(move)
            case DslActionMove(action, move):
                result.append(ActionMove(_compile_action(action, pos), move))
                pos = pos.add(move)
            case DslMoveAction(move, action):
                pos = pos.add(move)
                result.append(MoveAction(move, _compile_action(action, pos)))

    return result
