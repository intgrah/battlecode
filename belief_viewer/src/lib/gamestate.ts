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

const SCALING: Record<string, number> = {
  road: 0.005,
  conveyor: 0.01,
  armoured_conveyor: 0.01,
  splitter: 0.01,
  bridge: 0.05,
  barrier: 0.01,
  harvester: 0.1,
  foundry: 1.0,
  builder_bot: 0.2,
  gunner: 0.1,
  sentinel: 0.2,
  breach: 0.1,
  launcher: 0.1,
  marker: 0,
  core: 0,
};

const BASE_COSTS: Record<string, number> = {
  road: 1,
  conveyor: 3,
  armoured_conveyor: 10,
  splitter: 6,
  bridge: 20,
  barrier: 3,
  harvester: 80,
  foundry: 120,
  builder_bot: 50,
  gunner: 10,
  sentinel: 15,
  breach: 30,
  launcher: 20,
};

export function computeScaleAndCosts(
  turnState: TurnState,
  team: number,
): { scale: number; costs: Record<string, number> } {
  let scale = 1.0;
  for (const ent of turnState.entities.values()) {
    if (ent.team === team) {
      scale += SCALING[ent.kind] ?? 0;
    }
  }
  const costs: Record<string, number> = {};
  for (const [kind, base] of Object.entries(BASE_COSTS)) {
    costs[kind] = Math.floor(scale * base);
  }
  return { scale, costs };
}

export interface PlayerResources {
  titanium: number;
  axionite: number;
  titaniumCollected: number;
  axioniteCollected: number;
}

export interface TurnState {
  entities: Map<number, GameEntity>;
  players: [PlayerResources, PlayerResources];
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

const defaultPlayer = (): PlayerResources => ({
  titanium: 1000,
  axionite: 0,
  titaniumCollected: 0,
  axioniteCollected: 0,
});

export function reconstructStates(replay: Replay): Map<number, TurnState> {
  const states = new Map<number, TurnState>();
  const entities = new Map<number, GameEntity>();
  const players: [PlayerResources, PlayerResources] = [
    defaultPlayer(),
    defaultPlayer(),
  ];

  for (const core of replay.map?.cores ?? []) {
    entities.set(core.id, {
      id: core.id,
      team: core.team,
      x: core.position!.x,
      y: core.position!.y,
      kind: "core",
    });
  }

  states.set(0, {
    entities: cloneEntities(entities),
    players: [{ ...players[0] }, { ...players[1] }],
  });

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
        case "updatePlayers": {
          const p = update.kind.value.players;
          if (p?.a) {
            players[0].titanium = p.a.titanium;
            players[0].axionite = p.a.axionite;
            players[0].titaniumCollected = p.a.titaniumCollected;
            players[0].axioniteCollected = p.a.axioniteCollected;
          }
          if (p?.b) {
            players[1].titanium = p.b.titanium;
            players[1].axionite = p.b.axionite;
            players[1].titaniumCollected = p.b.titaniumCollected;
            players[1].axioniteCollected = p.b.axioniteCollected;
          }
          break;
        }
      }
    }
    states.set(turnIdx + 1, {
      entities: cloneEntities(entities),
      players: [{ ...players[0] }, { ...players[1] }],
    });
  }

  return states;
}
