from blueprint import BlueprintEntry, Direction, Entity

BLUEPRINT: tuple[BlueprintEntry, ...] = (
    BlueprintEntry((26, 41), Entity.HARVESTER),
    BlueprintEntry((28, 41), Entity.HARVESTER),
    BlueprintEntry((27, 40), Entity.HARVESTER),
    BlueprintEntry((26, 39), Entity.HARVESTER),
    BlueprintEntry((28, 39), Entity.HARVESTER),
    BlueprintEntry((26, 40), Entity.BRIDGE, bridge_target=(26, 43)),
    BlueprintEntry((28, 40), Entity.BRIDGE, bridge_target=(28, 43)),
    BlueprintEntry((28, 43), Entity.CONVEYOR, direction=Direction.SOUTH),
    BlueprintEntry((25, 43), Entity.ROAD),
    BlueprintEntry((24, 42), Entity.ROAD),
    BlueprintEntry((25, 41), Entity.ROAD),
    BlueprintEntry((29, 41), Entity.ROAD),
    BlueprintEntry((30, 42), Entity.ROAD),
    BlueprintEntry((29, 43), Entity.ROAD),
    BlueprintEntry((26, 43), Entity.FOUNDRY),
    BlueprintEntry((23, 43), Entity.BRIDGE, bridge_target=(26, 43)),
    BlueprintEntry((23, 44), Entity.HARVESTER),
    BlueprintEntry((22, 43), Entity.CONVEYOR, direction=Direction.EAST),
    BlueprintEntry((21, 43), Entity.HARVESTER),
)
