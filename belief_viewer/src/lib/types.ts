export interface BeliefFrame {
  w: number;
  h: number;
  round: number;
  eid: number;
  pos: [number, number];
  env: (string | null)[];
  entity: ([string, string] | null)[];
  direction: (string | null)[];
  bridge_target: Record<string, [number, number]>;
  my_core: [number, number];
  ore_ti: Set<number>;
  ore_ax: Set<number>;
  my_harvesters: number[];
  my_transport: number[];
  my_foundries: number[];
  flow_ti: number[];
  flow_ax: number[];
  flow_rax: number[];
  blocked: boolean[];
  unit_tiles: number[];
  symmetry: string | null;
}

export const Env = {
  UNSEEN: null,
  EMPTY: "empty",
  WALL: "wall",
  ORE_TITANIUM: "ore_titanium",
  ORE_AXIONITE: "ore_axionite",
} as const;

export const EType = {
  CORE: "core",
  BUILDER_BOT: "builder_bot",
  GUNNER: "gunner",
  SENTINEL: "sentinel",
  BREACH: "breach",
  LAUNCHER: "launcher",
  CONVEYOR: "conveyor",
  SPLITTER: "splitter",
  ARMOURED_CONVEYOR: "armoured_conveyor",
  BRIDGE: "bridge",
  HARVESTER: "harvester",
  FOUNDRY: "foundry",
  ROAD: "road",
  BARRIER: "barrier",
  MARKER: "marker",
} as const;

export const Dir = {
  NORTH: "north",
  NORTHEAST: "northeast",
  EAST: "east",
  SOUTHEAST: "southeast",
  SOUTH: "south",
  SOUTHWEST: "southwest",
  WEST: "west",
  NORTHWEST: "northwest",
  CENTRE: "centre",
} as const;

export const TeamId = {
  A: "a",
  B: "b",
} as const;

export enum Overlay {
  FLOW_TI = "flow_ti",
  FLOW_AX = "flow_ax",
  FLOW_RAX = "flow_rax",
  BLOCKED = "blocked",
}
