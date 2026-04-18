from blueprint import BlueprintEntry, Direction, Entity

BLUEPRINT: tuple[BlueprintEntry, ...] = (
    BlueprintEntry((8, 19), Entity.BRIDGE, bridge_target=(7, 17)),
    BlueprintEntry((7, 17), Entity.BRIDGE, bridge_target=(5, 16)),
    BlueprintEntry((5, 16), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((6, 16), Entity.ROAD),
    BlueprintEntry((8, 17), Entity.HARVESTER),
    BlueprintEntry((9, 19), Entity.HARVESTER),
    BlueprintEntry((7, 18), Entity.ROAD),
    BlueprintEntry((5, 14), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((6, 14), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((7, 14), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((8, 12), Entity.ROAD),
    BlueprintEntry((9, 13), Entity.ROAD),
    BlueprintEntry((10, 13), Entity.BRIDGE, bridge_target=(7, 13)),
    BlueprintEntry((10, 12), Entity.HARVESTER),
    BlueprintEntry((7, 13), Entity.CONVEYOR, direction=Direction.SOUTH),
)
