from blueprint import BlueprintEntry, Direction, Entity

BLUEPRINT: tuple[BlueprintEntry, ...] = (
    BlueprintEntry((8, 27), Entity.HARVESTER),
    BlueprintEntry((11, 24), Entity.HARVESTER),
    BlueprintEntry((11, 23), Entity.HARVESTER),
    BlueprintEntry((9, 27), Entity.HARVESTER),
    BlueprintEntry((8, 26), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((9, 26), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((10, 24), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((10, 23), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((7, 20), Entity.HARVESTER),
    BlueprintEntry((8, 20), Entity.HARVESTER),
    BlueprintEntry((9, 20), Entity.HARVESTER),
    BlueprintEntry((7, 21), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((7, 22), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((8, 21), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((8, 22), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((9, 21), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((9, 22), Entity.CONVEYOR, direction=Direction.SOUTH),
)
