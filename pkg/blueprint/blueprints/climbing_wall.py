from blueprint import BlueprintEntry, Direction, Entity

BLUEPRINT: tuple[BlueprintEntry, ...] = (
    BlueprintEntry((5, 44), Entity.HARVESTER),
    BlueprintEntry((6, 44), Entity.HARVESTER),
    BlueprintEntry((6, 45), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((5, 45), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((4, 45), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((3, 45), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((2, 45), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((1, 46), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((1, 45), Entity.FOUNDRY),
    BlueprintEntry((1, 41), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((1, 42), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((1, 43), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((1, 44), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((1, 40), Entity.HARVESTER),
    BlueprintEntry((2, 41), Entity.HARVESTER),
    BlueprintEntry((2, 46), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((3, 44), Entity.BRIDGE, bridge_target=(2, 46)),
    BlueprintEntry((5, 43), Entity.HARVESTER),
    BlueprintEntry((4, 43), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((3, 43), Entity.CONVEYOR, direction=Direction.SOUTH),
)
