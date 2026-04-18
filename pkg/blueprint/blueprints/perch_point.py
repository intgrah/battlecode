from blueprint import BlueprintEntry, Direction, Entity

BLUEPRINT: tuple[BlueprintEntry, ...] = (
    BlueprintEntry((3, 9), Entity.HARVESTER),
    BlueprintEntry((3, 1), Entity.HARVESTER),
    BlueprintEntry((2, 1), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((1, 1), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((1, 2), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((1, 3), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((1, 4), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((1, 5), Entity.FOUNDRY),
    BlueprintEntry((1, 6), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((1, 7), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((1, 8), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((1, 9), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((2, 9), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((3, 12), Entity.BARRIER),
    BlueprintEntry((3, 10), Entity.ROAD),
    BlueprintEntry((3, 11), Entity.ROAD),
)
