from blueprint import BlueprintEntry, Direction, Entity

BLUEPRINT: tuple[BlueprintEntry, ...] = (
    BlueprintEntry((2, 3), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((2, 4), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((2, 5), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((3, 6), Entity.HARVESTER),
    BlueprintEntry((3, 5), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((4, 5), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((6, 6), Entity.HARVESTER),
    BlueprintEntry((7, 8), Entity.HARVESTER),
    BlueprintEntry((5, 8), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((6, 8), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((2, 6), Entity.BARRIER),
    BlueprintEntry((4, 6), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((6, 5), Entity.BARRIER),
    BlueprintEntry((5, 7), Entity.FOUNDRY),
    BlueprintEntry((4, 7), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((5, 6), Entity.BARRIER),
    BlueprintEntry((6, 7), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((7, 6), Entity.SENTINEL, direction=Direction.SOUTHWEST),
    BlueprintEntry((3, 7), Entity.BARRIER),
    BlueprintEntry((9, 6), Entity.BARRIER),
)
