from blueprint import BlueprintEntry, Direction, Entity

BLUEPRINT: tuple[BlueprintEntry, ...] = (
    BlueprintEntry((10, 4), Entity.HARVESTER),
    BlueprintEntry((9, 9), Entity.HARVESTER),
    BlueprintEntry((9, 4), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((9, 3), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((10, 3), Entity.BARRIER),
    BlueprintEntry((9, 8), Entity.BRIDGE, bridge_target=(9, 5)),
    BlueprintEntry((9, 5), Entity.FOUNDRY),
    BlueprintEntry((10, 5), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((11, 4), Entity.SENTINEL, direction=Direction.SOUTHWEST),
    BlueprintEntry((8, 3), Entity.ROAD),
    BlueprintEntry((7, 2), Entity.ROAD),
    BlueprintEntry((6, 2), Entity.ROAD),
    BlueprintEntry((5, 2), Entity.ROAD),
    BlueprintEntry((4, 3), Entity.ROAD),
    BlueprintEntry((4, 4), Entity.ROAD),
    BlueprintEntry((5, 5), Entity.ROAD),
    BlueprintEntry((6, 6), Entity.ROAD),
    BlueprintEntry((7, 7), Entity.ROAD),
    BlueprintEntry((8, 7), Entity.ROAD),
)
