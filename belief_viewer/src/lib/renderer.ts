import { Env, EType, Dir, TeamId, Overlay, type BeliefFrame } from "./types";
import type { GroundTruth, IndicatorLine } from "./loader";

const TILE_SIZE = 48;

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

const MIRROR_MAP: Record<string, [string, boolean]> = {};
for (const team of ["gold", "silver"]) {
  MIRROR_MAP[`gunner_e_${team}`] = [`gunner_w_${team}`, true];
  MIRROR_MAP[`sentinel_w_${team}`] = [`sentinel_e_${team}`, true];
  MIRROR_MAP[`breach_w_${team}`] = [`breach_e_${team}`, true];
}

export interface RenderOptions {
  showEnv: boolean;
  showEntities: boolean;
  overlays: Set<Overlay>;
  ground: GroundTruth;
  indicators: IndicatorLine[];
}

export function render(
  ctx: CanvasRenderingContext2D,
  frame: BeliefFrame,
  opts: RenderOptions,
  sprites: Map<string, HTMLImageElement>,
) {
  const { w, h } = frame;
  ctx.canvas.width = w * TILE_SIZE;
  ctx.canvas.height = h * TILE_SIZE;
  ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);

  ctx.fillStyle = "#0d0d1a";
  ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x;
      const px = x * TILE_SIZE;
      const py = y * TILE_SIZE;
      const env = frame.env[i];

      if (opts.showEnv) {
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

      if (opts.showEntities) {
        renderEntity(ctx, frame, i, px, py, sprites);
      }

      for (const ov of opts.overlays) {
        renderOverlay(ctx, frame, ov, i, px, py);
      }

      renderFlowDots(ctx, frame, i, px, py);
    }
  }

  if (opts.showEntities) {
    renderCore(ctx, frame, sprites);
    renderBridges(ctx, frame, sprites);
    renderUnits(ctx, frame, sprites);
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
      drawn = drawSprite(ctx, sprites, `road_${teamSuffix}`, px, py);
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

function renderOverlay(
  ctx: CanvasRenderingContext2D,
  frame: BeliefFrame,
  overlay: Overlay,
  i: number,
  px: number,
  py: number,
) {
  switch (overlay) {
    case Overlay.FLOW_TI: {
      const v = frame.flow_ti[i];
      if (v > 0.001) {
        ctx.fillStyle = `rgba(64, 128, 255, ${Math.min(0.85, v * 1.5 + 0.2)})`;
        ctx.fillRect(px, py, TILE_SIZE, TILE_SIZE);
        drawFlowValue(ctx, v, px, py, "#6af");
      }
      break;
    }
    case Overlay.FLOW_AX: {
      const v = frame.flow_ax[i];
      if (v > 0.001) {
        ctx.fillStyle = `rgba(255, 160, 32, ${Math.min(0.85, v * 1.5 + 0.2)})`;
        ctx.fillRect(px, py, TILE_SIZE, TILE_SIZE);
        drawFlowValue(ctx, v, px, py, "#fa4");
      }
      break;
    }
    case Overlay.FLOW_RAX: {
      const v = frame.flow_rax[i];
      if (v > 0.001) {
        ctx.fillStyle = `rgba(180, 64, 255, ${Math.min(0.85, v * 1.5 + 0.2)})`;
        ctx.fillRect(px, py, TILE_SIZE, TILE_SIZE);
        drawFlowValue(ctx, v, px, py, "#c6f");
      }
      break;
    }
    case Overlay.BLOCKED:
      if (frame.blocked[i]) {
        ctx.fillStyle = "rgba(255, 0, 0, 0.35)";
        ctx.fillRect(px, py, TILE_SIZE, TILE_SIZE);
      }
      break;
  }
}

function drawFlowValue(
  ctx: CanvasRenderingContext2D,
  value: number,
  px: number,
  py: number,
  color: string,
) {
  ctx.fillStyle = color;
  ctx.font = "bold 10px monospace";
  ctx.textAlign = "center";
  ctx.fillText(value.toFixed(2), px + TILE_SIZE / 2, py + TILE_SIZE - 3);
}

function renderFlowDots(
  ctx: CanvasRenderingContext2D,
  frame: BeliefFrame,
  i: number,
  px: number,
  py: number,
) {
  const ti = frame.flow_ti[i];
  const ax = frame.flow_ax[i];
  const rax = frame.flow_rax[i];
  if (ti <= 0.001 && ax <= 0.001 && rax <= 0.001) return;

  let dotX = px + TILE_SIZE - 5;
  let dotY = py + 5;
  const r = 3;

  if (ti > 0.001) {
    ctx.fillStyle = "#4080ff";
    ctx.beginPath();
    ctx.arc(dotX, dotY, r, 0, Math.PI * 2);
    ctx.fill();
    dotY += r * 2 + 2;
  }
  if (ax > 0.001) {
    ctx.fillStyle = "#ffa020";
    ctx.beginPath();
    ctx.arc(dotX, dotY, r, 0, Math.PI * 2);
    ctx.fill();
    dotY += r * 2 + 2;
  }
  if (rax > 0.001) {
    ctx.fillStyle = "#b440ff";
    ctx.beginPath();
    ctx.arc(dotX, dotY, r, 0, Math.PI * 2);
    ctx.fill();
  }
}

function renderRadii(
  ctx: CanvasRenderingContext2D,
  frame: BeliefFrame,
) {
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
    ctx.moveTo(il.ax * TILE_SIZE + TILE_SIZE / 2, il.ay * TILE_SIZE + TILE_SIZE / 2);
    ctx.lineTo(il.bx * TILE_SIZE + TILE_SIZE / 2, il.by * TILE_SIZE + TILE_SIZE / 2);
    ctx.stroke();
  }
}

function renderCore(
  ctx: CanvasRenderingContext2D,
  frame: BeliefFrame,
  sprites: Map<string, HTMLImageElement>,
) {
  const [cx, cy] = frame.my_core;
  const sprite = sprites.get("base_gold");
  if (sprite) {
    ctx.drawImage(
      sprite,
      (cx - 1) * TILE_SIZE,
      (cy - 1) * TILE_SIZE,
      TILE_SIZE * 3,
      TILE_SIZE * 3,
    );
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
    ctx.translate(sx, sy);
    ctx.rotate(angle);
    const bridgeHeight = TILE_SIZE * 0.7;
    ctx.drawImage(sprite, 0, -bridgeHeight / 2, dist, bridgeHeight);
    ctx.restore();
  }
}

function renderUnits(
  ctx: CanvasRenderingContext2D,
  frame: BeliefFrame,
  sprites: Map<string, HTMLImageElement>,
) {
  const selfTile = frame.pos[1] * frame.w + frame.pos[0];
  const selfPx = frame.pos[0] * TILE_SIZE;
  const selfPy = frame.pos[1] * TILE_SIZE;
  drawSprite(ctx, sprites, "builderbot_front_gold", selfPx, selfPy);
  ctx.strokeStyle = "#ff0";
  ctx.lineWidth = 2;
  ctx.strokeRect(selfPx + 1, selfPy + 1, TILE_SIZE - 2, TILE_SIZE - 2);

  for (const i of frame.unit_tiles) {
    if (i === selfTile) continue;
    const px = (i % frame.w) * TILE_SIZE;
    const py = Math.floor(i / frame.w) * TILE_SIZE;
    drawSprite(ctx, sprites, "builderbot_front_gold", px, py);
  }
}
