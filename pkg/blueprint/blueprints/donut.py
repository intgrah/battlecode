from blueprint import BlueprintEntry, Direction, Entity

BLUEPRINT: tuple[BlueprintEntry, ...] = (
    BlueprintEntry((12, 14), Entity.ROAD),
    BlueprintEntry((11, 13), Entity.BRIDGE, bridge_target=(12, 15)),
    BlueprintEntry((11, 12), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((10, 13), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((9, 13), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((8, 13), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((7, 13), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((7, 12), Entity.FOUNDRY),
    BlueprintEntry((6, 15), Entity.HARVESTER),
    BlueprintEntry((7, 11), Entity.HARVESTER),
    BlueprintEntry((4, 12), Entity.HARVESTER),
    BlueprintEntry((5, 12), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((6, 12), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((6, 14), Entity.BRIDGE, bridge_target=(7, 12)),
    BlueprintEntry((8, 12), Entity.ROAD),
    BlueprintEntry((8, 10), Entity.BRIDGE, bridge_target=(7, 12)),
    BlueprintEntry((8, 11), Entity.ROAD),
    BlueprintEntry((8, 9), Entity.HARVESTER),
    BlueprintEntry((11, 11), Entity.HARVESTER),
)
