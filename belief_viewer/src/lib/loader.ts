import { ReplaySchema } from "./proto/cambc_pb";
import { fromBinary } from "@bufbuild/protobuf";
import type { BeliefFrame } from "./types";

const BELIEF_PREFIX = "BELIEF:";

export interface GroundTruth {
  w: number;
  h: number;
  env: number[];
}

export interface IndicatorLine {
  eid: number;
  ax: number;
  ay: number;
  bx: number;
  by: number;
  r: number;
  g: number;
  b: number;
}

export interface ReplayData {
  bots: Map<number, Map<number, BeliefFrame>>;
  botIds: number[];
  ground: GroundTruth;
  indicators: Map<number, IndicatorLine[]>;
}

export async function loadReplayFromUrl(url: string): Promise<ReplayData> {
  const resp = await fetch(url);
  const buf = await resp.arrayBuffer();
  return parseReplay(buf);
}

export async function loadReplay(file: File): Promise<ReplayData> {
  const buf = await file.arrayBuffer();
  return parseReplay(buf);
}

function parseReplay(buf: ArrayBuffer): ReplayData {
  const replay = fromBinary(ReplaySchema, new Uint8Array(buf));

  const map = replay.map!;
  const w = map.width;
  const h = map.height;
  const env: number[] = [];
  for (const row of map.rows) {
    for (const tile of row.tiles) {
      env.push(tile);
    }
  }
  const ground: GroundTruth = { w, h, env };

  const bots = new Map<number, Map<number, BeliefFrame>>();
  const indicators = new Map<number, IndicatorLine[]>();

  for (let turnIdx = 0; turnIdx < replay.turns.length; turnIdx++) {
    const turn = replay.turns[turnIdx];
    const turnLines: IndicatorLine[] = [];
    for (const update of turn.updates) {
      if (update.kind.case === "botOutput") {
        const output = update.kind.value;
        const lines = output.stdout.split("\n");
        for (const line of lines) {
          if (!line.startsWith(BELIEF_PREFIX)) continue;
          const json = line.slice(BELIEF_PREFIX.length);
          const raw = JSON.parse(json);
          raw.ore_ti = new Set(raw.ore_ti);
          raw.ore_ax = new Set(raw.ore_ax);
          const frame = raw as BeliefFrame;

          if (!bots.has(frame.eid)) {
            bots.set(frame.eid, new Map());
          }
          bots.get(frame.eid)!.set(frame.round, frame);
        }
      } else if (update.kind.case === "indicatorLine") {
        const il = update.kind.value;
        turnLines.push({
          eid: il.id,
          ax: il.posA!.x,
          ay: il.posA!.y,
          bx: il.posB!.x,
          by: il.posB!.y,
          r: il.r,
          g: il.g,
          b: il.b,
        });
      }
    }
    if (turnLines.length > 0) {
      indicators.set(turnIdx + 1, turnLines);
    }
  }

  const botIds = [...bots.keys()].sort((a, b) => a - b);
  return { bots, botIds, ground, indicators };
}

export async function loadSprites(): Promise<Map<string, HTMLImageElement>> {
  const sprites = new Map<string, HTMLImageElement>();
  const teams = ["gold", "silver"];

  const names = [
    "conveyor_gold",
    "conveyor_silver",
    "armoured_conveyor_gold",
    "armoured_conveyor_silver",
    "bridge_gold",
    "bridge_silver",
    "bridge_stand_gold",
    "bridge_stand_silver",
    "road_gold",
    "road_silver",
    "barrier_gold",
    "barrier_silver",
    "harvester_gold",
    "harvester_silver",
    "foundry_gold",
    "foundry_silver",
    "marker_gold",
    "marker_silver",
    "base_gold",
    "base_silver",
    "launcher_gold",
    "launcher_silver",
    "splitter_n_gold",
    "splitter_n_silver",
    "splitter_s_gold",
    "splitter_s_silver",
    "splitter_e_gold",
    "splitter_e_silver",
    "splitter_w_gold",
    "splitter_w_silver",
    "titanium_ore",
    "axionite_ore",
    "bg",
    "titanium",
    "axionite_raw",
    "axionite_processed",
    "builderbot_front_gold",
    "builderbot_front_silver",
    "builderbot_back_gold",
    "builderbot_back_silver",
    "builderbot_side_gold",
    "builderbot_side_silver",
  ];

  const gunnerDirs = ["n", "ne", "se", "s", "sw", "w", "nw"];
  for (const team of teams) {
    for (const dir of gunnerDirs) {
      names.push(`gunner_${dir}_${team}`);
    }
  }

  const dirEntities = ["sentinel", "breach"];
  const dirs = ["n", "ne", "e", "se", "s", "sw", "nw"];
  for (const ent of dirEntities) {
    for (const dir of dirs) {
      for (const team of teams) {
        names.push(`${ent}_${dir}_${team}`);
      }
    }
  }

  const jpgNames = ["natural_wall"];

  const allEntries: [string, string][] = [
    ...names.map((n): [string, string] => [n, `/sprites/${n}.png`]),
    ...jpgNames.map((n): [string, string] => [n, `/sprites/${n}.jpg`]),
  ];

  let loaded = 0;
  let failed = 0;
  await Promise.all(
    allEntries.map(
      ([name, src]) =>
        new Promise<void>((resolve) => {
          const img = new Image();
          img.onload = () => {
            sprites.set(name, img);
            loaded++;
            resolve();
          };
          img.onerror = () => {
            failed++;
            resolve();
          };
          img.src = src;
        }),
    ),
  );
  console.log(
    `Sprites: ${loaded} loaded, ${failed} failed, ${allEntries.length} total`,
  );

  return sprites;
}
