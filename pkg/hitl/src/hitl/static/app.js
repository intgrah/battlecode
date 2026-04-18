"use strict";

const state = {
  direction: null,
  action: null,
  buildType: null,
  reasons: new Set(),
  lastAnnotationId: null,
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const BUILD_REQUIRED = new Set(["build"]);
const DIR_REQUIRED = new Set(["move", "attack", "heal", "destroy", "build"]);

function togglePick(btn, key, val, multi = false) {
  if (multi) {
    const s = state[key];
    if (s.has(val)) { s.delete(val); btn.classList.remove("selected"); }
    else { s.add(val); btn.classList.add("selected"); }
  } else {
    $$("[data-" + key + "]").forEach((b) => b.classList.remove("selected"));
    btn.classList.add("selected");
    state[key] = val;
  }
  refresh();
}

function refresh() {
  const needsBuild = BUILD_REQUIRED.has(state.action);
  $(".build-row").classList.toggle("hidden", !needsBuild);
  const ok =
    state.action &&
    (!DIR_REQUIRED.has(state.action) || state.direction !== null) &&
    (!needsBuild || state.buildType !== null);
  $("#submit").disabled = !ok;
}

function attach() {
  $$(".dir").forEach((b) => b.addEventListener("click", () => togglePick(b, "direction", b.dataset.dir)));
  $$(".act").forEach((b) => b.addEventListener("click", () => togglePick(b, "action", b.dataset.act)));
  $$(".build").forEach((b) => b.addEventListener("click", () => togglePick(b, "buildType", b.dataset.build)));
  $$(".reason").forEach((b) => b.addEventListener("click", () => {
    const s = state.reasons;
    const v = b.dataset.reason;
    if (s.has(v)) { s.delete(v); b.classList.remove("selected"); }
    else { s.add(v); b.classList.add("selected"); }
  }));

  $("#submit").addEventListener("click", submit);
  $("#skip").addEventListener("click", () => (location.href = "/"));
  $("#right-yes")?.addEventListener("click", () => reveal(true));
  $("#right-no")?.addEventListener("click", () => reveal(false));
}

async function submit() {
  const app = $("#app");
  if (!app) return;
  const body = new FormData();
  body.set("event_id", app.dataset.eventId);
  body.set("direction", state.direction || "none");
  body.set("action", state.action);
  if (state.buildType) body.set("build_type", state.buildType);
  body.set("reasons", JSON.stringify([...state.reasons]));
  body.set("free_text", $("#free-text")?.value || "");

  const r = await fetch("/annotate", { method: "POST", body });
  if (!r.ok) { alert("submit failed: " + r.status); return; }
  const d = await r.json();
  state.lastAnnotationId = d.annotation_id;
  $("#bot-action").textContent = d.bot_action || "(unknown)";
  $("#reveal").classList.remove("hidden");
  $("#reveal").scrollIntoView({ behavior: "smooth", block: "end" });
}

async function reveal(right) {
  if (!state.lastAnnotationId) return;
  const body = new FormData();
  body.set("right", right ? "1" : "0");
  await fetch("/reveal/" + state.lastAnnotationId, { method: "POST", body });
  location.href = "/";
}

window.addEventListener("DOMContentLoaded", attach);
