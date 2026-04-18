from blueprint import BlueprintEntry, Direction, Entity

BLUEPRINT: tuple[BlueprintEntry, ...] = (
    BlueprintEntry((9, 17), Entity.HARVESTER),
    BlueprintEntry((10, 16), Entity.HARVESTER),
    BlueprintEntry((11, 17), Entity.HARVESTER),
    BlueprintEntry((10, 18), Entity.HARVESTER),
    BlueprintEntry((10, 17), Entity.BRIDGE, bridge_target=(12, 19)),
    BlueprintEntry((12, 19), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((12, 20), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((12, 21), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((12, 22), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((11, 18), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((12, 18), Entity.CONVEYOR, direction=Direction.SOUTH),
)
