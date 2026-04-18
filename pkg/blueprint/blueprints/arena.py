from blueprint import BlueprintEntry, Direction, Entity

BLUEPRINT: tuple[BlueprintEntry, ...] = (
    BlueprintEntry((7, 13), Entity.FOUNDRY),
    BlueprintEntry((7, 8), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((7, 12), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((8, 13), Entity.HARVESTER),
    BlueprintEntry((6, 13), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((7, 14), Entity.SPLITTER, direction=Direction.SOUTH),
    BlueprintEntry((7, 7), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((6, 8), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((5, 13), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((7, 6), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((5, 8), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((5, 14), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((7, 5), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((4, 8), Entity.HARVESTER),
    BlueprintEntry((5, 15), Entity.HARVESTER),
    BlueprintEntry((7, 4), Entity.HARVESTER),
    BlueprintEntry((8, 14), Entity.GUNNER, direction=Direction.EAST),
    BlueprintEntry((6, 14), Entity.SENTINEL, direction=Direction.NORTH),
    BlueprintEntry((7, 15), Entity.SENTINEL, direction=Direction.SOUTH),
)
