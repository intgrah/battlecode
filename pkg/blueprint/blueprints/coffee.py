from blueprint import BlueprintEntry, Direction, Entity

BLUEPRINT: tuple[BlueprintEntry, ...] = (
    BlueprintEntry((21, 5), Entity.HARVESTER),
    BlueprintEntry((21, 7), Entity.HARVESTER),
    BlueprintEntry((20, 7), Entity.CONVEYOR, direction=Direction.WEST),
    BlueprintEntry((20, 5), Entity.CONVEYOR, direction=Direction.WEST),
)
