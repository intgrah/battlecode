from blueprint import BlueprintEntry, Direction, Entity

BLUEPRINT: tuple[BlueprintEntry, ...] = (
    BlueprintEntry((2, 8), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((3, 8), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((1, 8), Entity.HARVESTER),
    BlueprintEntry((0, 8), Entity.BARRIER),
    BlueprintEntry((1, 9), Entity.BARRIER),
    BlueprintEntry((1, 7), Entity.BARRIER),
    BlueprintEntry((7, 0), Entity.HARVESTER),
    BlueprintEntry((6, 0), Entity.FOUNDRY),
    BlueprintEntry((8, 0), Entity.BARRIER),
    BlueprintEntry((7, 1), Entity.BARRIER),
    BlueprintEntry((6, 1), Entity.BRIDGE, bridge_target=(6, 4)),
    BlueprintEntry((6, 4), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((1, 1), Entity.HARVESTER),
    BlueprintEntry((1, 0), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((2, 0), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((3, 0), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((4, 0), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((5, 0), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((6, 5), Entity.CONVEYOR, direction=Direction.SOUTH),
)
