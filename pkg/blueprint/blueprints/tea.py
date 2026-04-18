from blueprint import BlueprintEntry, Direction, Entity

BLUEPRINT: tuple[BlueprintEntry, ...] = (
    BlueprintEntry((4, 3), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((4, 4), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((4, 5), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((4, 6), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((5, 6), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((6, 7), Entity.ROAD),
    BlueprintEntry((7, 8), Entity.BRIDGE, bridge_target=(5, 6)),
    BlueprintEntry((9, 9), Entity.HARVESTER),
    BlueprintEntry((8, 9), Entity.FOUNDRY),
    BlueprintEntry((7, 9), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((8, 13), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((8, 12), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((8, 11), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((8, 10), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((8, 14), Entity.HARVESTER),
)
