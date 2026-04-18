from blueprint import BlueprintEntry, Direction, Entity

BLUEPRINT: tuple[BlueprintEntry, ...] = (
    BlueprintEntry((3, 1), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((4, 1), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((5, 1), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((2, 3), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((2, 4), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((2, 5), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((3, 6), Entity.HARVESTER),
    BlueprintEntry((6, 1), Entity.HARVESTER),
    BlueprintEntry((3, 5), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((4, 5), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((5, 5), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((6, 5), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((6, 6), Entity.HARVESTER),
    BlueprintEntry((7, 8), Entity.HARVESTER),
    BlueprintEntry((7, 7), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((8, 6), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((7, 5), Entity.SPLITTER, direction=Direction.NORTH),
    BlueprintEntry((7, 6), Entity.FOUNDRY),
    BlueprintEntry((9, 6), Entity.HARVESTER),
    BlueprintEntry((8, 5), Entity.BREACH, direction=Direction.SOUTHEAST),
)
