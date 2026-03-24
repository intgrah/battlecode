import { Env, EType, Dir, TeamId, Overlay, type BeliefFrame } from "./types";
import type { GroundTruth, IndicatorLine } from "./loader";
import type { TurnState, GameEntity } from "./gamestate";

const TILE_SIZE = 64;

const ENV_COLORS: Record<string, string> = {
  [Env.EMPTY]: "#3d3d3d",
  [Env.WALL]: "#1a1a1a",
  [Env.ORE_TITANIUM]: "#2a5080",
  [Env.ORE_AXIONITE]: "#806020",
};

const DIR_ROTATION: Record<string, number> = {
  [Dir.NORTH]: -Math.PI / 2,
  [Dir.NORTHEAST]: -Math.PI / 4,
  [Dir.EAST]: 0,
  [Dir.SOUTHEAST]: Math.PI / 4,
  [Dir.SOUTH]: Math.PI / 2,
  [Dir.SOUTHWEST]: (3 * Math.PI) / 4,
  [Dir.WEST]: Math.PI,
  [Dir.NORTHWEST]: (-3 * Math.PI) / 4,
};

const DIR_SHORT: Record<string, string> = {
  [Dir.NORTH]: "n",
  [Dir.NORTHEAST]: "ne",
  [Dir.EAST]: "e",
  [Dir.SOUTHEAST]: "se",
  [Dir.SOUTH]: "s",
  [Dir.SOUTHWEST]: "sw",
  [Dir.WEST]: "w",
  [Dir.NORTHWEST]: "nw",
};

const DIR_ROTATION_NUM: Record<number, number> = {
  1: -Math.PI / 2,
  2: -Math.PI / 4,
  3: 0,
  4: Math.PI / 4,
  5: Math.PI / 2,
  6: (3 * Math.PI) / 4,
  7: Math.PI,
  8: (-3 * Math.PI) / 4,
};

const DIR_SHORT_NUM: Record<number, string> = {
  1: "n",
  2: "ne",
  3: "e",
  4: "se",
  5: "s",
  6: "sw",
  7: "w",
  8: "nw",
};

const MIRROR_MAP: Record<string, [string, boolean]> = {};
for (const team of ["gold", "silver"]) {
  MIRROR_MAP[`gunner_e_${team}`] = [`gunner_w_${team}`, true];
  MIRROR_MAP[`sentinel_w_${team}`] = [`sentinel_e_${team}`, true];
  MIRROR_MAP[`breach_w_${team}`] = [`breach_e_${team}`, true];
}

export interface RenderOptions {
  useBeliefEntities: boolean;
  overlays: Set<Overlay>;
  ground: GroundTruth;
  indicators: IndicatorLine[];
  turnState: TurnState | undefined;
  selectedBot: number;
}

export function render(
  ctx: CanvasRenderingContext2D,
  frame: BeliefFrame,
  opts: RenderOptions,
  sprites: Map<string, HTMLImageElement>,
) {
  const { w, h } = frame;
  ctx.fillStyle = "#0d0d1a";
  ctx.fillRect(0, 0, w * TILE_SIZE, h * TILE_SIZE);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x;
      const px = x * TILE_SIZE;
      const py = y * TILE_SIZE;
      const env = frame.env[i];

      {
        const groundEnv = opts.ground.env[i];
        ctx.fillStyle = "#352927";
        ctx.fillRect(px, py, TILE_SIZE, TILE_SIZE);
        if (groundEnv === 1) {
          drawSprite(ctx, sprites, "natural_wall", px, py);
          ctx.save();
          ctx.globalCompositeOperation = "multiply";
          ctx.fillStyle = "#482418";
          ctx.fillRect(px, py, TILE_SIZE, TILE_SIZE);
          ctx.restore();
        } else if (groundEnv === 2) {
          drawSprite(ctx, sprites, "titanium_ore", px, py);
        } else if (groundEnv === 3) {
          drawSprite(ctx, sprites, "axionite_ore", px, py);
        }
        if (env === null) {
          ctx.fillStyle = "rgba(0, 0, 0, 0.6)";
          ctx.fillRect(px, py, TILE_SIZE, TILE_SIZE);
        }
      }

      {
        const seen = env !== null;
        if (seen && opts.useBeliefEntities) {
          renderEntity(ctx, frame, i, px, py, sprites);
        } else if (opts.turnState) {
          renderGroundEntity(
            ctx,
            frame,
            opts.turnState,
            i,
            px,
            py,
            sprites,
            !seen,
          );
        }
      }

      renderFlowOverlay(ctx, frame, opts.overlays, i, px, py);
    }
  }

  renderCore(ctx, frame, sprites, opts.turnState);
  renderBridges(ctx, frame, sprites);
  if (opts.turnState) {
    renderAllBuilders(ctx, frame, opts.turnState, opts.selectedBot, sprites);
  }

  renderRadii(ctx, frame);
  renderIndicatorLines(ctx, opts.indicators);
}

function drawSprite(
  ctx: CanvasRenderingContext2D,
  sprites: Map<string, HTMLImageElement>,
  name: string,
  px: number,
  py: number,
  rotation?: number,
): boolean {
  let sprite = sprites.get(name);
  let flipH = false;

  if (!sprite) {
    const mirror = MIRROR_MAP[name];
    if (mirror) {
      sprite = sprites.get(mirror[0]);
      flipH = mirror[1];
    }
  }
  if (!sprite) return false;

  ctx.save();
  ctx.translate(px + TILE_SIZE / 2, py + TILE_SIZE / 2);
  if (flipH) ctx.scale(-1, 1);
  if (rotation) ctx.rotate(rotation);
  ctx.drawImage(sprite, -TILE_SIZE / 2, -TILE_SIZE / 2, TILE_SIZE, TILE_SIZE);
  ctx.restore();
  return true;
}

function renderEntity(
  ctx: CanvasRenderingContext2D,
  frame: BeliefFrame,
  i: number,
  px: number,
  py: number,
  sprites: Map<string, HTMLImageElement>,
) {
  const ent = frame.entity[i];
  if (ent === null) return;

  const [etype, team] = ent;
  const teamSuffix = team === TeamId.A ? "gold" : "silver";
  const dir = frame.direction[i];
  const rotation = dir !== null ? DIR_ROTATION[dir] : undefined;
  const dirShort = dir !== null ? DIR_SHORT[dir] : null;

  let drawn = false;
  switch (etype) {
    case EType.CONVEYOR:
      drawn = drawSprite(
        ctx,
        sprites,
        `conveyor_${teamSuffix}`,
        px,
        py,
        rotation,
      );
      break;
    case EType.ARMOURED_CONVEYOR:
      drawn = drawSprite(
        ctx,
        sprites,
        `armoured_conveyor_${teamSuffix}`,
        px,
        py,
        rotation,
      );
      break;
    case EType.SPLITTER:
      if (dirShort)
        drawn = drawSprite(
          ctx,
          sprites,
          `splitter_${dirShort}_${teamSuffix}`,
          px,
          py,
        );
      break;
    case EType.BRIDGE:
      drawn = drawSprite(ctx, sprites, `bridge_stand_${teamSuffix}`, px, py);
      break;
    case EType.ROAD:
      ctx.globalAlpha = 0.6;
      drawn = drawSprite(ctx, sprites, `road_${teamSuffix}`, px, py);
      ctx.globalAlpha = 1;
      break;
    case EType.BARRIER:
      drawn = drawSprite(ctx, sprites, `barrier_${teamSuffix}`, px, py);
      break;
    case EType.HARVESTER:
      drawn = drawSprite(ctx, sprites, `harvester_${teamSuffix}`, px, py);
      break;
    case EType.FOUNDRY:
      drawn = drawSprite(ctx, sprites, `foundry_${teamSuffix}`, px, py);
      break;
    case EType.MARKER:
      drawn = drawSprite(ctx, sprites, `marker_${teamSuffix}`, px, py);
      break;
    case EType.CORE:
      drawn = true;
      break;
    case EType.GUNNER:
      if (dirShort)
        drawn = drawSprite(
          ctx,
          sprites,
          `gunner_${dirShort}_${teamSuffix}`,
          px,
          py,
        );
      break;
    case EType.SENTINEL:
      if (dirShort)
        drawn = drawSprite(
          ctx,
          sprites,
          `sentinel_${dirShort}_${teamSuffix}`,
          px,
          py,
        );
      break;
    case EType.BREACH:
      if (dirShort)
        drawn = drawSprite(
          ctx,
          sprites,
          `breach_${dirShort}_${teamSuffix}`,
          px,
          py,
        );
      break;
    case EType.LAUNCHER:
      drawn = drawSprite(ctx, sprites, `launcher_${teamSuffix}`, px, py);
      break;
    case EType.BUILDER_BOT:
      drawn = drawSprite(
        ctx,
        sprites,
        `builderbot_front_${teamSuffix}`,
        px,
        py,
      );
      break;
  }

  if (!drawn) {
    const teamColor = team === TeamId.A ? "#d4a017" : "#8a9aaa";
    ctx.fillStyle = teamColor + "66";
    ctx.fillRect(px + 2, py + 2, TILE_SIZE - 4, TILE_SIZE - 4);
  }
}

function renderFlowOverlay(
  ctx: CanvasRenderingContext2D,
  frame: BeliefFrame,
  overlays: Set<Overlay>,
  i: number,
  px: number,
  py: number,
) {
  const ti = overlays.has(Overlay.FLOW_TI) ? frame.flow_ti[i] : 0;
  const ax = overlays.has(Overlay.FLOW_AX) ? frame.flow_ax[i] : 0;
  const rax = overlays.has(Overlay.FLOW_RAX) ? frame.flow_rax[i] : 0;
  const total = ti + ax + rax;

  if (total > 0.001) {
    const alpha = Math.min(0.75, total * 1.2 + 0.15);
    const r = Math.round((ti * 64 + ax * 255 + rax * 180) / total);
    const g = Math.round((ti * 128 + ax * 160 + rax * 64) / total);
    const b = Math.round((ti * 255 + ax * 32 + rax * 255) / total);
    ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${alpha})`;
    ctx.fillRect(px, py, TILE_SIZE, TILE_SIZE);

    ctx.font = "bold 12px monospace";
    ctx.textAlign = "left";
    let textY = py + 14;
    if (ti > 0.001) {
      ctx.fillStyle = "#8ac4ff";
      ctx.fillText(`Ti ${ti.toFixed(2)}`, px + 2, textY);
      textY += 14;
    }
    if (ax > 0.001) {
      ctx.fillStyle = "#ffcc66";
      ctx.fillText(`Ax ${ax.toFixed(2)}`, px + 2, textY);
      textY += 14;
    }
    if (rax > 0.001) {
      ctx.fillStyle = "#d89aff";
      ctx.fillText(`RAx${rax.toFixed(2)}`, px + 2, textY);
    }
  }

  if (overlays.has(Overlay.EXCESS)) {
    const eti = frame.excess_ti[i];
    const eax = frame.excess_ax[i];
    const erax = frame.excess_rax[i];
    const etotal = eti + eax + erax;
    if (etotal > 0.001) {
      ctx.fillStyle = `rgba(255, 255, 0, ${Math.min(0.7, etotal * 1.5 + 0.2)})`;
      ctx.fillRect(px, py, TILE_SIZE, TILE_SIZE);
      ctx.font = "bold 11px monospace";
      ctx.textAlign = "center";
      ctx.fillStyle = "#ff0";
      ctx.fillText(`E ${etotal.toFixed(2)}`, px + TILE_SIZE / 2, py + TILE_SIZE / 2 + 4);
    }
  }

  if (overlays.has(Overlay.BLOCKED) && frame.blocked[i]) {
    ctx.fillStyle = "rgba(255, 0, 0, 0.35)";
    ctx.fillRect(px, py, TILE_SIZE, TILE_SIZE);
  }

  if (overlays.has(Overlay.LEAKAGE) && frame.leakage[i] > 0) {
    const leak = frame.leakage[i];
    const dotSize = 6;
    const margin = 4;
    let dotX = px + TILE_SIZE - margin - dotSize;
    let dotY = py + margin;
    if (leak & 1) {
      ctx.fillStyle = "rgba(100, 160, 255, 0.8)";
      ctx.beginPath();
      ctx.arc(dotX, dotY, dotSize / 2, 0, Math.PI * 2);
      ctx.fill();
      dotY += dotSize + 2;
    }
    if (leak & 2) {
      ctx.fillStyle = "rgba(255, 180, 50, 0.8)";
      ctx.beginPath();
      ctx.arc(dotX, dotY, dotSize / 2, 0, Math.PI * 2);
      ctx.fill();
      dotY += dotSize + 2;
    }
    if (leak & 4) {
      ctx.fillStyle = "rgba(200, 130, 255, 0.8)";
      ctx.beginPath();
      ctx.arc(dotX, dotY, dotSize / 2, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}

function renderRadii(ctx: CanvasRenderingContext2D, frame: BeliefFrame) {
  drawTileRadius(ctx, frame, 20, "rgba(80, 140, 255, 0.5)");
  drawTileRadius(ctx, frame, 2, "rgba(255, 80, 80, 0.5)");
}

function drawTileRadius(
  ctx: CanvasRenderingContext2D,
  frame: BeliefFrame,
  rSq: number,
  color: string,
) {
  const [px, py] = frame.pos;
  const r = Math.ceil(Math.sqrt(rSq));

  const inRange = (dx: number, dy: number) => dx * dx + dy * dy <= rSq;

  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.beginPath();

  for (let dy = -r; dy <= r; dy++) {
    for (let dx = -r; dx <= r; dx++) {
      if (!inRange(dx, dy)) continue;
      const tx = (px + dx) * TILE_SIZE;
      const ty = (py + dy) * TILE_SIZE;

      if (!inRange(dx, dy - 1)) {
        ctx.moveTo(tx, ty);
        ctx.lineTo(tx + TILE_SIZE, ty);
      }
      if (!inRange(dx, dy + 1)) {
        ctx.moveTo(tx, ty + TILE_SIZE);
        ctx.lineTo(tx + TILE_SIZE, ty + TILE_SIZE);
      }
      if (!inRange(dx - 1, dy)) {
        ctx.moveTo(tx, ty);
        ctx.lineTo(tx, ty + TILE_SIZE);
      }
      if (!inRange(dx + 1, dy)) {
        ctx.moveTo(tx + TILE_SIZE, ty);
        ctx.lineTo(tx + TILE_SIZE, ty + TILE_SIZE);
      }
    }
  }

  ctx.stroke();
}

function renderIndicatorLines(
  ctx: CanvasRenderingContext2D,
  indicators: IndicatorLine[],
) {
  for (const il of indicators) {
    ctx.strokeStyle = `rgb(${il.r}, ${il.g}, ${il.b})`;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(
      il.ax * TILE_SIZE + TILE_SIZE / 2,
      il.ay * TILE_SIZE + TILE_SIZE / 2,
    );
    ctx.lineTo(
      il.bx * TILE_SIZE + TILE_SIZE / 2,
      il.by * TILE_SIZE + TILE_SIZE / 2,
    );
    ctx.stroke();
  }
}

function renderCore(
  ctx: CanvasRenderingContext2D,
  frame: BeliefFrame,
  sprites: Map<string, HTMLImageElement>,
  turnState: TurnState | undefined,
) {
  const [cx, cy] = frame.my_core;
  const mySprite = sprites.get("base_gold");
  if (mySprite) {
    ctx.drawImage(
      mySprite,
      (cx - 1) * TILE_SIZE,
      (cy - 1) * TILE_SIZE,
      TILE_SIZE * 3,
      TILE_SIZE * 3,
    );
  }

  if (turnState) {
    for (const ent of turnState.entities.values()) {
      if (ent.kind === "core" && (ent.x !== cx || ent.y !== cy)) {
        const teamSuffix = ent.team === 0 ? "gold" : "silver";
        const sprite = sprites.get(`base_${teamSuffix}`);
        if (sprite) {
          ctx.drawImage(
            sprite,
            (ent.x - 1) * TILE_SIZE,
            (ent.y - 1) * TILE_SIZE,
            TILE_SIZE * 3,
            TILE_SIZE * 3,
          );
        }
      }
    }
  }
}

function renderBridges(
  ctx: CanvasRenderingContext2D,
  frame: BeliefFrame,
  sprites: Map<string, HTMLImageElement>,
) {
  for (const [tileStr, target] of Object.entries(frame.bridge_target)) {
    const i = parseInt(tileStr);
    const ent = frame.entity[i];
    if (ent === null || ent[0] !== EType.BRIDGE) continue;

    const team = ent[1];
    const teamSuffix = team === TeamId.A ? "gold" : "silver";
    const sprite = sprites.get(`bridge_${teamSuffix}`);
    if (!sprite) continue;

    const sx = (i % frame.w) * TILE_SIZE + TILE_SIZE / 2;
    const sy = Math.floor(i / frame.w) * TILE_SIZE + TILE_SIZE / 2;
    const tx = target[0] * TILE_SIZE + TILE_SIZE / 2;
    const ty = target[1] * TILE_SIZE + TILE_SIZE / 2;

    const dx = tx - sx;
    const dy = ty - sy;
    const dist = Math.sqrt(dx * dx + dy * dy);
    const angle = Math.atan2(dy, dx);

    ctx.save();
    ctx.globalAlpha = 0.6;
    ctx.translate(sx, sy);
    ctx.rotate(angle);
    const bridgeHeight = TILE_SIZE * 0.7;
    ctx.drawImage(sprite, 0, -bridgeHeight / 2, dist, bridgeHeight);
    ctx.restore();
  }
}

function renderGroundEntity(
  ctx: CanvasRenderingContext2D,
  frame: BeliefFrame,
  turnState: TurnState,
  i: number,
  px: number,
  py: number,
  sprites: Map<string, HTMLImageElement>,
  dimmed: boolean,
) {
  const x = i % frame.w;
  const y = Math.floor(i / frame.w);
  for (const ent of turnState.entities.values()) {
    if (ent.x !== x || ent.y !== y) continue;
    if (ent.kind === "builder_bot" || ent.kind === "core") continue;
    const teamSuffix = ent.team === 0 ? "gold" : "silver";
    const dir = ent.direction;
    const dirShort = dir !== undefined ? DIR_SHORT_NUM[dir] : null;
    const rotation = dir !== undefined ? DIR_ROTATION_NUM[dir] : undefined;

    let spriteName: string | null = null;
    switch (ent.kind) {
      case "conveyor":
        spriteName = `conveyor_${teamSuffix}`;
        break;
      case "armoured_conveyor":
        spriteName = `armoured_conveyor_${teamSuffix}`;
        break;
      case "splitter":
        if (dirShort) spriteName = `splitter_${dirShort}_${teamSuffix}`;
        break;
      case "bridge":
        spriteName = `bridge_stand_${teamSuffix}`;
        break;
      case "road":
        spriteName = `road_${teamSuffix}`;
        break;
      case "barrier":
        spriteName = `barrier_${teamSuffix}`;
        break;
      case "harvester":
        spriteName = `harvester_${teamSuffix}`;
        break;
      case "foundry":
        spriteName = `foundry_${teamSuffix}`;
        break;
      case "marker":
        spriteName = `marker_${teamSuffix}`;
        break;
      case "gunner":
        if (dirShort) spriteName = `gunner_${dirShort}_${teamSuffix}`;
        break;
      case "sentinel":
        if (dirShort) spriteName = `sentinel_${dirShort}_${teamSuffix}`;
        break;
      case "breach":
        if (dirShort) spriteName = `breach_${dirShort}_${teamSuffix}`;
        break;
      case "launcher":
        spriteName = `launcher_${teamSuffix}`;
        break;
    }

    if (spriteName) {
      if (dimmed) ctx.globalAlpha = 0.35;
      if (ent.kind === "conveyor" || ent.kind === "armoured_conveyor") {
        drawSprite(ctx, sprites, spriteName, px, py, rotation);
      } else {
        drawSprite(ctx, sprites, spriteName, px, py);
      }
      if (dimmed) ctx.globalAlpha = 1;
    }
  }
}

function renderAllBuilders(
  ctx: CanvasRenderingContext2D,
  frame: BeliefFrame,
  turnState: TurnState,
  selectedBot: number,
  sprites: Map<string, HTMLImageElement>,
) {
  const visionSq = 20;

  for (const ent of turnState.entities.values()) {
    if (ent.kind !== "builder_bot") continue;
    const px = ent.x * TILE_SIZE;
    const py = ent.y * TILE_SIZE;
    const teamSuffix = ent.team === 0 ? "gold" : "silver";
    const isSelected = ent.id === selectedBot;
    const dx = ent.x - frame.pos[0];
    const dy = ent.y - frame.pos[1];
    const inVision = dx * dx + dy * dy <= visionSq;

    if (!isSelected && !inVision) ctx.globalAlpha = 0.35;
    drawSprite(ctx, sprites, `builderbot_front_${teamSuffix}`, px, py);
    ctx.globalAlpha = 1;

    if (isSelected) {
      ctx.strokeStyle = "#ff0";
      ctx.lineWidth = 2;
      ctx.strokeRect(px + 1, py + 1, TILE_SIZE - 2, TILE_SIZE - 2);
    }
  }
}
