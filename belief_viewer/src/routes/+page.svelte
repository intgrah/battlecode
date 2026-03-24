<script lang="ts">
  import { onMount } from "svelte";
  import { render } from "$lib/renderer";
  import {
    loadReplay,
    loadReplayFromUrl,
    loadSprites,
    type ReplayData,
  } from "$lib/loader";
  import { Overlay, type BeliefFrame } from "$lib/types";
  import { computeScaleAndCosts } from "$lib/gamestate";

  let canvas = $state<HTMLCanvasElement>();
  let sprites = $state<Map<string, HTMLImageElement>>(new Map());

  let replayData = $state<ReplayData | null>(null);
  let botIds = $state<number[]>([]);
  let rounds = $state<number[]>([]);
  let selectedBot = $state(0);
  let selectedRound = $state(0);
  let frame = $state<BeliefFrame | null>(null);
  let loading = $state(false);

  let useBeliefEntities = $state(true);

  let camX = $state(0);
  let camY = $state(0);
  let zoom = $state(1);
  let dragging = $state(false);
  let dragStartX = 0;
  let dragStartY = 0;
  let camStartX = 0;
  let camStartY = 0;
  let showFlow = $state(true);
  let showExcess = $state(false);
  let showBlocked = $state(false);
  let showLeakage = $state(false);

  let overlays = $derived(
    new Set([
      ...(showFlow
        ? [Overlay.FLOW_TI, Overlay.FLOW_AX, Overlay.FLOW_RAX]
        : []),
      ...(showExcess ? [Overlay.EXCESS] : []),
      ...(showLeakage ? [Overlay.LEAKAGE] : []),
      ...(showBlocked ? [Overlay.BLOCKED] : []),
    ]),
  );

  let needsCenter = $state(false);

  onMount(async () => {
    sprites = await loadSprites();
    await loadFromUrl("/api/replay");
    needsCenter = true;
  });

  async function loadFromUrl(url: string) {
    loading = true;
    try {
      replayData = await loadReplayFromUrl(url);
      botIds = replayData.botIds;
      if (botIds.length > 0) {
        selectBot(botIds[0]);
      }
    } catch (e) {
      console.error("Failed to load replay:", e);
    }
    loading = false;
  }

  async function onFileSelect(e: Event) {
    const input = e.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;

    loading = true;
    replayData = await loadReplay(file);
    botIds = replayData.botIds;
    loading = false;

    if (botIds.length > 0) {
      selectBot(botIds[0]);
    }
  }

  function selectBot(eid: number) {
    selectedBot = eid;
    const botFrames = replayData?.bots.get(eid);
    if (!botFrames) return;
    rounds = [...botFrames.keys()].sort((a, b) => a - b);
    if (rounds.length > 0) {
      if (!rounds.includes(selectedRound)) {
        const closest = rounds.reduce((prev, curr) =>
          Math.abs(curr - selectedRound) < Math.abs(prev - selectedRound)
            ? curr
            : prev,
        );
        selectedRound = closest;
      }
      loadFrame();
    }
  }

  function loadFrame() {
    frame = replayData?.bots.get(selectedBot)?.get(selectedRound) ?? null;
  }

  let offscreen: OffscreenCanvas | null = null;
  let rafId = 0;

  function draw() {
    if (!frame || !canvas || !replayData) return;
    const cw = canvas.clientWidth;
    const ch = canvas.clientHeight;
    if (cw === 0 || ch === 0) {
      rafId = requestAnimationFrame(draw);
      return;
    }

    canvas.width = cw;
    canvas.height = ch;

    const g = replayData.ground;
    const mapW = g.w * 64;
    const mapH = g.h * 64;

    if (needsCenter) {
      zoom = Math.min(cw / mapW, ch / mapH, 1);
      camX = (cw - mapW * zoom) / 2;
      camY = (ch - mapH * zoom) / 2;
      needsCenter = false;
    }

    if (!offscreen || offscreen.width !== mapW || offscreen.height !== mapH) {
      offscreen = new OffscreenCanvas(mapW, mapH);
    }
    const offCtx = offscreen.getContext("2d");
    if (!offCtx) return;

    const turnIndicators = replayData.indicators.get(frame.round) ?? [];
    const botIndicators = turnIndicators.filter((il) => il.eid === selectedBot);
    render(
      offCtx as unknown as CanvasRenderingContext2D,
      frame,
      {
        useBeliefEntities,
        overlays,
        ground: replayData.ground,
        indicators: botIndicators,
        turnState: replayData.turnStates.get(frame.round),
        selectedBot,
      },
      sprites,
    );

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, cw, ch);
    ctx.drawImage(
      offscreen,
      Math.round(camX),
      Math.round(camY),
      Math.round(mapW * zoom),
      Math.round(mapH * zoom),
    );
  }

  $effect(() => {
    void frame;
    void canvas;
    void replayData;
    void camX;
    void camY;
    void zoom;
    void useBeliefEntities;
    void overlays;
    void selectedBot;
    void sprites;
    void needsCenter;
    cancelAnimationFrame(rafId);
    rafId = requestAnimationFrame(draw);
  });

  function prevRound() {
    const idx = rounds.indexOf(selectedRound);
    if (idx > 0) {
      selectedRound = rounds[idx - 1];
      loadFrame();
    }
  }

  function nextRound() {
    const idx = rounds.indexOf(selectedRound);
    if (idx < rounds.length - 1) {
      selectedRound = rounds[idx + 1];
      loadFrame();
    }
  }

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === "ArrowLeft") prevRound();
    else if (e.key === "ArrowRight") nextRound();
  }

  function canvasToTile(clientX: number, clientY: number): [number, number] {
    if (!canvas) return [0, 0];
    const rect = canvas.getBoundingClientRect();
    const pixelX = (clientX - rect.left) * (canvas.width / rect.width);
    const pixelY = (clientY - rect.top) * (canvas.height / rect.height);
    const worldX = (pixelX - camX) / zoom;
    const worldY = (pixelY - camY) / zoom;
    return [Math.floor(worldX / 64), Math.floor(worldY / 64)];
  }

  function onCanvasClick(e: MouseEvent) {
    if (!canvas || !replayData || !frame || dragging) return;
    const [tileX, tileY] = canvasToTile(e.clientX, e.clientY);
    const turnState = replayData.turnStates.get(frame.round);
    if (!turnState) return;
    for (const ent of turnState.entities.values()) {
      if (ent.kind === "builder_bot" && ent.x === tileX && ent.y === tileY) {
        if (replayData.bots.has(ent.id)) {
          selectBot(ent.id);
          return;
        }
      }
    }
  }

  function onCanvasMouseDown(e: MouseEvent) {
    if (e.button !== 0) return;
    dragging = true;
    dragStartX = e.clientX;
    dragStartY = e.clientY;
    camStartX = camX;
    camStartY = camY;
  }

  function onCanvasMouseMove(e: MouseEvent) {
    if (!dragging) return;
    camX = camStartX + (e.clientX - dragStartX);
    camY = camStartY + (e.clientY - dragStartY);
  }

  function onCanvasMouseUp() {
    dragging = false;
  }

  function onCanvasWheel(e: WheelEvent) {
    e.preventDefault();
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mouseX = (e.clientX - rect.left) * (canvas.width / rect.width);
    const mouseY = (e.clientY - rect.top) * (canvas.height / rect.height);

    const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    const newZoom = Math.max(0.2, Math.min(5, zoom * factor));

    camX = mouseX - ((mouseX - camX) / zoom) * newZoom;
    camY = mouseY - ((mouseY - camY) / zoom) * newZoom;
    zoom = newZoom;
  }
</script>

<svelte:window onkeydown={onKeyDown} />

<svelte:head>
  <title>Belief Viewer</title>
</svelte:head>

<div class="container">
  <div class="controls">
    <div class="control-group">
      <label>
        Replay
        <input type="file" accept=".replay26" onchange={onFileSelect} />
      </label>
    </div>

    {#if botIds.length > 0}
      <div class="control-group">
        <label>
          Bot
          <select onchange={(e) => selectBot(Number(e.currentTarget.value))}>
            {#each botIds as bot}
              <option value={bot} selected={bot === selectedBot}
                >Bot {bot}</option
              >
            {/each}
          </select>
        </label>
      </div>

      <div class="control-group">
        <span>Round {selectedRound} / {rounds[rounds.length - 1] ?? 0}</span>
        <div class="round-controls">
          <button onclick={prevRound}>&lt;</button>
          <input
            type="range"
            min={rounds[0] ?? 0}
            max={rounds[rounds.length - 1] ?? 0}
            value={selectedRound}
            oninput={(e) => {
              const val = Number(e.currentTarget.value);
              const closest = rounds.reduce((prev, curr) =>
                Math.abs(curr - val) < Math.abs(prev - val) ? curr : prev,
              );
              selectedRound = closest;
              loadFrame();
            }}
            onwheel={(e) => {
              e.preventDefault();
              if (e.deltaY < 0) nextRound();
              else prevRound();
            }}
          />
          <button onclick={nextRound}>&gt;</button>
        </div>
      </div>

      <div class="control-group checkboxes">
        <label><input type="checkbox" bind:checked={useBeliefEntities} /> Belief</label>
        <label><input type="checkbox" bind:checked={showFlow} /> Flow</label>
        <label><input type="checkbox" bind:checked={showExcess} /> Excess</label>
        <label><input type="checkbox" bind:checked={showBlocked} /> Blocked</label>
        <label><input type="checkbox" bind:checked={showLeakage} /> Leakage</label>
      </div>
    {/if}

    {#if loading}
      <span class="loading">Loading...</span>
    {/if}

    {#if frame && replayData}
      {@const ts = replayData.turnStates.get(frame.round)}
      <span class="info">
        {frame.w}x{frame.h} | {frame.symmetry ?? "?"}
        {#if ts}
          {@const sc = computeScaleAndCosts(ts, 0)}
          | Ti: {ts.players[0].titanium} ({ts.players[0].titaniumCollected} mined)
          | RAx: {ts.players[0].axionite} ({ts.players[0].axioniteCollected} mined)
          | Scale: {sc.scale.toFixed(2)}x | Builder: {sc.costs.builder_bot} Harv:
          {sc.costs.harvester} Foundry: {sc.costs.foundry} Conv: {sc.costs
            .conveyor} Bridge: {sc.costs.bridge}
        {/if}
      </span>
    {/if}
  </div>

  {#if !replayData}
    <div class="drop-zone">
      Drop a .replay26 file or use the file picker above
    </div>
  {:else}
    <div class="canvas-wrapper">
      <canvas
        bind:this={canvas}
        onclick={onCanvasClick}
        onmousedown={onCanvasMouseDown}
        onmousemove={onCanvasMouseMove}
        onmouseup={onCanvasMouseUp}
        onmouseleave={onCanvasMouseUp}
        onwheel={onCanvasWheel}
      ></canvas>
    </div>
  {/if}
</div>

<style>
  .container {
    font-family: "Berkeley Mono", "Fira Code", monospace;
    background: #0a0a0a;
    color: #ccc;
    height: 100vh;
    padding: 12px;
    display: flex;
    flex-direction: column;
    box-sizing: border-box;
  }

  .controls {
    display: flex;
    gap: 20px;
    align-items: center;
    flex-wrap: wrap;
    margin-bottom: 12px;
  }

  .control-group {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 12px;
  }

  .checkboxes {
    flex-direction: row;
    gap: 12px;
  }

  .checkboxes label {
    flex-direction: row;
    gap: 4px;
    cursor: pointer;
    user-select: none;
  }

  label {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 12px;
  }

  select,
  button {
    background: #1a1a1a;
    color: #ccc;
    border: 1px solid #333;
    padding: 4px 8px;
    font-size: 12px;
    cursor: pointer;
  }

  input[type="file"] {
    font-size: 11px;
    color: #888;
  }

  .round-controls {
    display: flex;
    gap: 4px;
    align-items: center;
  }

  input[type="range"] {
    width: 400px;
  }

  input[type="checkbox"] {
    accent-color: #4080ff;
  }

  .loading {
    color: #ff0;
    font-size: 12px;
  }

  .info {
    font-size: 11px;
    color: #888;
  }

  .drop-zone {
    flex: 1;
    border: 2px dashed #333;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #555;
    font-size: 14px;
  }

  .canvas-wrapper {
    flex: 1;
    border: 1px solid #222;
    overflow: hidden;
    position: relative;
  }

  canvas {
    display: block;
    width: 100%;
    height: 100%;
    cursor: grab;
  }

  canvas:active {
    cursor: grabbing;
  }
</style>
