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

  let canvas = $state<HTMLCanvasElement>();
  let sprites = $state<Map<string, HTMLImageElement>>(new Map());

  let replayData = $state<ReplayData | null>(null);
  let botIds = $state<number[]>([]);
  let rounds = $state<number[]>([]);
  let selectedBot = $state(0);
  let selectedRound = $state(0);
  let frame = $state<BeliefFrame | null>(null);
  let loading = $state(false);

  let showEnv = $state(true);
  let showEntities = $state(true);
  let showFlowTi = $state(false);
  let showFlowAx = $state(false);
  let showFlowRax = $state(false);
  let showBlocked = $state(false);

  let overlays = $derived(
    new Set([
      ...(showFlowTi ? [Overlay.FLOW_TI] : []),
      ...(showFlowAx ? [Overlay.FLOW_AX] : []),
      ...(showFlowRax ? [Overlay.FLOW_RAX] : []),
      ...(showBlocked ? [Overlay.BLOCKED] : []),
    ]),
  );

  onMount(async () => {
    sprites = await loadSprites();
    await loadFromUrl("/replay.replay26");
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
      selectedRound = rounds[0];
      loadFrame();
    }
  }

  function loadFrame() {
    frame = replayData?.bots.get(selectedBot)?.get(selectedRound) ?? null;
  }

  $effect(() => {
    if (!frame || !canvas || !replayData) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const turnIndicators = replayData.indicators.get(frame.round) ?? [];
    const botIndicators = turnIndicators.filter((il) => il.eid === selectedBot);
    render(
      ctx,
      frame,
      {
        showEnv,
        showEntities,
        overlays,
        ground: replayData.ground,
        indicators: botIndicators,
      },
      sprites,
    );
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
          />
          <button onclick={nextRound}>&gt;</button>
        </div>
      </div>

      <div class="control-group checkboxes">
        <label><input type="checkbox" bind:checked={showEnv} /> Env</label>
        <label
          ><input type="checkbox" bind:checked={showEntities} /> Entities</label
        >
        <label><input type="checkbox" bind:checked={showFlowTi} /> Ti</label>
        <label><input type="checkbox" bind:checked={showFlowAx} /> Ax</label>
        <label><input type="checkbox" bind:checked={showFlowRax} /> RAx</label>
        <label
          ><input type="checkbox" bind:checked={showBlocked} /> Blocked</label
        >
      </div>
    {/if}

    {#if loading}
      <span class="loading">Loading...</span>
    {/if}

    {#if frame}
      <span class="info">{frame.w}x{frame.h} | {frame.symmetry ?? "?"}</span>
    {/if}
  </div>

  {#if !replayData}
    <div class="drop-zone">
      Drop a .replay26 file or use the file picker above
    </div>
  {:else}
    <div class="canvas-wrapper">
      <canvas bind:this={canvas}></canvas>
    </div>
  {/if}
</div>

<style>
  .container {
    font-family: "Berkeley Mono", "Fira Code", monospace;
    background: #0a0a0a;
    color: #ccc;
    min-height: 100vh;
    padding: 12px;
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
    border: 2px dashed #333;
    padding: 60px;
    text-align: center;
    color: #555;
    font-size: 14px;
  }

  .canvas-wrapper {
    overflow: auto;
    border: 1px solid #222;
  }

  canvas {
    display: block;
  }
</style>
