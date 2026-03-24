import type { Entity, Replay, Turn } from "./proto/cambc_pb";

export interface GameEntity {
  id: number;
  team: number;
  x: number;
  y: number;
  kind: string;
  direction?: number;
  bridgeTarget?: { x: number; y: number };
}

export interface TurnState {
  entities: Map<number, GameEntity>;
}

function entityKind(entity: Entity): string {
  switch (entity.kind.case) {
    case "builderBot":
      return "builder_bot";
    case "conveyor":
      return "conveyor";
    case "splitter":
      return "splitter";
    case "armouredConveyor":
      return "armoured_conveyor";
    case "bridge":
      return "bridge";
    case "harvester":
      return "harvester";
    case "foundry":
      return "foundry";
    case "road":
      return "road";
    case "barrier":
      return "barrier";
    case "marker":
      return "marker";
    case "core":
      return "core";
    case "gunner":
      return "gunner";
    case "sentinel":
      return "sentinel";
    case "breach":
      return "breach";
    case "launcher":
      return "launcher";
    default:
      return "unknown";
  }
}

function entityDirection(entity: Entity): number | undefined {
  const k = entity.kind;
  switch (k.case) {
    case "conveyor":
      return k.value.direction;
    case "splitter":
      return k.value.direction;
    case "armouredConveyor":
      return k.value.direction;
    case "gunner":
      return k.value.direction;
    case "sentinel":
      return k.value.direction;
    case "breach":
      return k.value.direction;
    default:
      return undefined;
  }
}

function entityBridgeTarget(
  entity: Entity,
): { x: number; y: number } | undefined {
  if (entity.kind.case === "bridge" && entity.kind.value.target) {
    return { x: entity.kind.value.target.x, y: entity.kind.value.target.y };
  }
  return undefined;
}

function cloneEntities(
  entities: Map<number, GameEntity>,
): Map<number, GameEntity> {
  const clone = new Map<number, GameEntity>();
  for (const [id, ent] of entities) {
    clone.set(id, {
      ...ent,
      bridgeTarget: ent.bridgeTarget ? { ...ent.bridgeTarget } : undefined,
    });
  }
  return clone;
}

export function reconstructStates(replay: Replay): Map<number, TurnState> {
  const states = new Map<number, TurnState>();
  const entities = new Map<number, GameEntity>();

  for (const core of replay.map?.cores ?? []) {
    entities.set(core.id, {
      id: core.id,
      team: core.team,
      x: core.position!.x,
      y: core.position!.y,
      kind: "core",
    });
  }

  states.set(0, { entities: cloneEntities(entities) });

  for (let turnIdx = 0; turnIdx < replay.turns.length; turnIdx++) {
    const turn = replay.turns[turnIdx];
    for (const update of turn.updates) {
      switch (update.kind.case) {
        case "placeEntity": {
          const e = update.kind.value.entity!;
          entities.set(e.id, {
            id: e.id,
            team: e.team,
            x: e.position!.x,
            y: e.position!.y,
            kind: entityKind(e),
            direction: entityDirection(e),
            bridgeTarget: entityBridgeTarget(e),
          });
          break;
        }
        case "removeEntity": {
          entities.delete(update.kind.value.id);
          break;
        }
        case "moveBuilderBot": {
          const mv = update.kind.value;
          const ent = entities.get(mv.id);
          if (ent) {
            ent.x = mv.to!.x;
            ent.y = mv.to!.y;
          }
          break;
        }
      }
    }
    states.set(turnIdx + 1, { entities: cloneEntities(entities) });
  }

  return states;
}
