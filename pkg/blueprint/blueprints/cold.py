from blueprint import BlueprintEntry, Direction, Entity

BLUEPRINT: tuple[BlueprintEntry, ...] = (
    BlueprintEntry((10, 15), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((10, 16), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((10, 17), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((10, 18), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((10, 19), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((10, 20), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((10, 21), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((10, 22), Entity.HARVESTER),
    BlueprintEntry((9, 22), Entity.HARVESTER),
    BlueprintEntry((11, 22), Entity.HARVESTER),
    BlueprintEntry((9, 21), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((11, 21), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((12, 21), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((12, 22), Entity.HARVESTER),
)
