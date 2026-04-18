from blueprint import BlueprintEntry, Direction, Entity

BLUEPRINT: tuple[BlueprintEntry, ...] = (
    BlueprintEntry((33, 38), Entity.HARVESTER),
    BlueprintEntry((35, 38), Entity.HARVESTER),
    BlueprintEntry((34, 38), Entity.FOUNDRY),
    BlueprintEntry((33, 37), Entity.HARVESTER),
    BlueprintEntry((33, 36), Entity.HARVESTER),
    BlueprintEntry((34, 37), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((34, 36), Entity.CONVEYOR, direction=Direction.NORTH),
    BlueprintEntry((34, 35), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((35, 35), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((36, 35), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((37, 35), Entity.CONVEYOR, direction=Direction.EAST),
)
