from blueprint import BlueprintEntry, Direction, Entity

BLUEPRINT: tuple[BlueprintEntry, ...] = (
    BlueprintEntry((2, 17), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((2, 16), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((2, 15), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((2, 14), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((2, 13), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((2, 12), Entity.HARVESTER),
    BlueprintEntry((3, 13), Entity.HARVESTER),
    BlueprintEntry((3, 12), Entity.BRIDGE, bridge_target=(2, 14)),
    BlueprintEntry((4, 12), Entity.HARVESTER),
    BlueprintEntry((3, 11), Entity.HARVESTER),
)
