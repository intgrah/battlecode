"""Event-driven replay debugger for LLM-readable output.

Scans a replay file, detects interesting events (combat, breaks, state
changes, economy shifts), and produces a compact narrative that an LLM
or human can reason about.

Usage:
    python scripts/replay_debug.py [replay] [options]

Options:
    --team A|B          Filter to one team
    --entity ID         Filter to one entity
    --turns 100-200     Only show events in turn range
    --area x1,y1,x2,y2 Only show events in bounding box
    --event TYPE        Filter event type (combat,break,economy,spawn,
                        death,idle,tle,turret,marker,state)
    --context N         Map-snippet radius around events (default 5)
    --no-map            Skip map snippets
    --verbose           Show all turns, not just events
    --json              Output as JSON (for piping to tools)
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analysis.parse import parse as parse_replay

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEAM_LABEL = {0: "A", 1: "B"}
ENV_CHARS = {0: ".", 1: "#", 2: "T", 3: "X"}
DIR_DELTA = {
    0: (0, 0),
    1: (0, -1),
    2: (1, -1),
    3: (1, 0),
    4: (1, 1),
    5: (0, 1),
    6: (-1, 1),
    7: (-1, 0),
    8: (-1, -1),
}
DIR_ARROWS = {0: "o", 1: "^", 2: "/", 3: ">", 4: "\\", 5: "v", 6: "\\", 7: "<", 8: "/"}
CONVEYOR_KINDS = frozenset({"conveyor", "armoured_conveyor", "splitter", "bridge"})
TURRET_KINDS = frozenset({"gunner", "sentinel", "breach", "launcher"})
MOBILE_KINDS = frozenset({"builder_bot"})

ENTITY_CHARS = {
    "core": "@",
    "builder_bot": "b",
    "conveyor": ">",
    "splitter": "Y",
    "bridge": "=",
    "harvester": "H",
    "foundry": "F",
    "road": "-",
    "barrier": "B",
    "marker": ",",
    "gunner": "g",
    "sentinel": "s",
    "breach": "x",
    "launcher": "L",
    "armoured_conveyor": ">",
}

# Marker decoding (matches bots/v32/marker.py)
CIPHER = 0x2120B7E8
_TAG_SHIFT = 28
_CLAIM_STATES = {0: "CLAIMED", 1: "BUILDING", 2: "CONNECTED", 3: "ABANDONED"}
_URGENCY = {0: "LOW", 1: "MEDIUM", 2: "HIGH", 3: "CRITICAL"}


def _decode_marker(encrypted: int) -> dict | None:
    """Decode a marker value into a readable dict. Returns None if invalid."""
    raw = encrypted ^ CIPHER
    tag = (raw >> _TAG_SHIFT) & 0xF
    payload = raw & 0x0FFFFFFF
    if tag == 0:
        return {
            "type": "OreClaim",
            "ore_x": (payload >> 22) & 0x3F,
            "ore_y": (payload >> 16) & 0x3F,
            "state": _CLAIM_STATES.get((payload >> 14) & 0x3, "?"),
            "freshness": (payload >> 2) & 0x3F,
        }
    if tag == 1:
        return {
            "type": "Threat",
            "enemy_x": (payload >> 22) & 0x3F,
            "enemy_y": (payload >> 16) & 0x3F,
            "enemy_count": (payload >> 8) & 0xF,
            "urgency": _URGENCY.get(payload & 0x3, "?"),
            "freshness": (payload >> 2) & 0x3F,
        }
    if tag == 2:
        return {
            "type": "Pressure",
            "pos_x": (payload >> 22) & 0x3F,
            "pos_y": (payload >> 16) & 0x3F,
            "level": (payload >> 12) & 0xF,
            "upstream_harvesters": (payload >> 8) & 0xF,
            "freshness": (payload >> 2) & 0x3F,
        }
    if tag == 3:
        return {
            "type": "BreakAlert",
            "break_x": (payload >> 22) & 0x3F,
            "break_y": (payload >> 16) & 0x3F,
            "importance": (payload >> 10) & 0x7,
            "freshness": (payload >> 4) & 0x3F,
        }
    return None


# ---------------------------------------------------------------------------
# Entity / game state tracking
# ---------------------------------------------------------------------------


def _entity_kind(e: object) -> str:
    return e.WhichOneof("kind") or "unknown"


@dataclass
class EntityInfo:
    id: int
    team: int
    kind: str
    pos: tuple[int, int]
    hp: int
    max_hp: int
    direction: int = 0
    bridge_target: tuple[int, int] | None = None
    marker_value: int | None = None
    spawn_turn: int = 0


@dataclass
class BotDebugInfo:
    """Parsed structured debug JSON from BotOutput.stdout."""

    raw: str = ""
    parsed: dict | None = None


@dataclass
class Event:
    turn: int
    kind: str  # combat, break, economy, spawn, death, idle, tle, turret, marker, state
    team: int | None = None
    entity_id: int | None = None
    pos: tuple[int, int] | None = None
    description: str = ""
    details: dict = field(default_factory=dict)
    priority: int = 0  # higher = more important


@dataclass
class TurnState:
    """Snapshot of resources at a turn."""

    ti: dict[int, int] = field(default_factory=lambda: {0: 1000, 1: 1000})
    ax: dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0})
    ti_collected: dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0})
    ax_collected: dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0})


# ---------------------------------------------------------------------------
# Core replay scanner with event detection
# ---------------------------------------------------------------------------


class ReplayDebugger:
    def __init__(self, replay: object) -> None:
        self.replay = replay
        self.w = replay.map.width
        self.h = replay.map.height
        self.env_grid = [list(row.tiles) for row in replay.map.rows]

        self.core_pos: dict[int, tuple[int, int]] = {}
        for c in replay.map.cores:
            self.core_pos[c.team] = (c.position.x, c.position.y)

        self.entities: dict[int, EntityInfo] = {}
        self.building_at: dict[tuple[int, int], int] = {}
        self.events: list[Event] = []
        self.resources = TurnState()
        self.resources_at_turn: dict[int, TurnState] = {}  # snapshots at event turns
        self.bot_output: dict[int, dict[int, BotDebugInfo]] = defaultdict(
            dict,
        )  # turn -> eid -> info

        # Tracking for event detection
        self._prev_income: dict[int, float] = {0: 0.0, 1: 0.0}
        self._income_window: dict[int, list[tuple[int, int]]] = {
            0: [],
            1: [],
        }  # (turn, collected)
        self._entity_counts: dict[int, Counter] = {0: Counter(), 1: Counter()}
        self._conveyor_chains: dict[int, set[tuple[int, int]]] = {0: set(), 1: set()}
        self._idle_streak: dict[int, int] = defaultdict(int)
        self._acted: set[int] = set()
        self._damaged: set[int] = set()
        self._fire_events: list[tuple[int, tuple[int, int], tuple[int, int]]] = []

    def scan(self) -> list[Event]:
        """Single-pass scan of the replay, detecting events."""
        for turn_idx, turn in enumerate(self.replay.turns):
            self._acted.clear()
            self._damaged.clear()
            self._fire_events.clear()

            for u in turn.updates:
                kind = u.WhichOneof("kind")
                if kind == "place_entity":
                    self._handle_place(turn_idx, u.place_entity.entity)
                elif kind == "move_builder_bot":
                    self._handle_move(turn_idx, u.move_builder_bot)
                elif kind == "remove_entity":
                    self._handle_remove(turn_idx, u.remove_entity)
                elif kind == "update_hp":
                    self._handle_hp(turn_idx, u.update_hp)
                elif kind == "update_players":
                    self._handle_resources(turn_idx, u.update_players.players)
                elif kind == "fire_turret":
                    self._handle_fire(turn_idx, u.fire_turret)
                elif kind == "bot_output":
                    self._handle_bot_output(turn_idx, u.bot_output)

            # Post-turn: snapshot resources and detect idle builders
            self._snapshot_resources(turn_idx)
            self._detect_idle(turn_idx)

        self.events.sort(key=lambda e: (e.turn, -e.priority))
        return self.events

    # --- Update handlers ---

    def _handle_place(self, turn: int, entity: object) -> None:
        e = entity
        ek = _entity_kind(e)
        pos = (e.position.x, e.position.y)
        direction = 0
        bridge_target = None
        marker_value = None

        if ek in ("conveyor", "armoured_conveyor", "splitter"):
            direction = getattr(e, ek).direction
        elif ek == "bridge":
            bridge_target = (e.bridge.target.x, e.bridge.target.y)
        elif ek in TURRET_KINDS and ek != "launcher":
            direction = getattr(e, ek).direction
        elif ek == "marker":
            marker_value = e.marker.value

        info = EntityInfo(
            id=e.id,
            team=e.team,
            kind=ek,
            pos=pos,
            hp=e.hp,
            max_hp=e.max_hp,
            direction=direction,
            bridge_target=bridge_target,
            marker_value=marker_value,
            spawn_turn=turn,
        )
        self.entities[e.id] = info
        if ek not in MOBILE_KINDS and ek != "marker":
            self.building_at[pos] = e.id
        self._acted.add(e.id)
        self._entity_counts[e.team][ek] += 1

        # Event: entity spawned (only interesting ones)
        if ek == "builder_bot":
            self.events.append(
                Event(
                    turn=turn,
                    kind="spawn",
                    team=e.team,
                    entity_id=e.id,
                    pos=pos,
                    description=f"Builder #{e.id} spawned at {pos}",
                    priority=20,
                ),
            )
        elif ek == "harvester":
            self.events.append(
                Event(
                    turn=turn,
                    kind="spawn",
                    team=e.team,
                    entity_id=e.id,
                    pos=pos,
                    description=f"Harvester #{e.id} built at {pos} (team {TEAM_LABEL[e.team]} now has {self._entity_counts[e.team]['harvester']})",
                    priority=40,
                ),
            )
        elif ek in TURRET_KINDS:
            self.events.append(
                Event(
                    turn=turn,
                    kind="spawn",
                    team=e.team,
                    entity_id=e.id,
                    pos=pos,
                    description=f"{ek.title()} #{e.id} built at {pos} facing dir={direction}",
                    priority=50,
                ),
            )
        elif ek == "marker":
            decoded = _decode_marker(marker_value) if marker_value else None
            if decoded and decoded["type"] in ("Threat", "BreakAlert"):
                self.events.append(
                    Event(
                        turn=turn,
                        kind="marker",
                        team=e.team,
                        pos=pos,
                        description=f"Marker placed at {pos}: {decoded}",
                        details={"marker": decoded},
                        priority=60 if decoded["type"] == "Threat" else 50,
                    ),
                )

        if ek in CONVEYOR_KINDS:
            self._conveyor_chains[e.team].add(pos)

    def _handle_move(self, _turn: int, mb: object) -> None:
        eid = mb.id
        new_pos = (mb.to.x, mb.to.y)
        if eid in self.entities:
            self.entities[eid].pos = new_pos
        self._acted.add(eid)
        self._idle_streak[eid] = 0

    def _handle_remove(self, turn: int, rm: object) -> None:
        eid = rm.id
        info = self.entities.pop(eid, None)
        if info is None:
            return

        self._entity_counts[info.team][info.kind] -= 1
        if info.pos in self.building_at and self.building_at[info.pos] == eid:
            del self.building_at[info.pos]

        if info.kind in CONVEYOR_KINDS:
            self._conveyor_chains[info.team].discard(info.pos)

        if info.kind == "builder_bot":
            was_damaged = eid in self._damaged
            cause = "killed" if was_damaged else "self-destruct"
            self.events.append(
                Event(
                    turn=turn,
                    kind="death",
                    team=info.team,
                    entity_id=eid,
                    pos=info.pos,
                    description=f"Builder #{eid} {cause} at {info.pos} (lived {turn - info.spawn_turn} turns)",
                    details={"cause": cause, "lifetime": turn - info.spawn_turn},
                    priority=60 if was_damaged else 30,
                ),
            )
        elif info.kind in ("harvester", "foundry") or info.kind in TURRET_KINDS:
            was_damaged = eid in self._damaged
            self.events.append(
                Event(
                    turn=turn,
                    kind="death",
                    team=info.team,
                    entity_id=eid,
                    pos=info.pos,
                    description=f"{info.kind.title()} #{eid} destroyed at {info.pos} (team {TEAM_LABEL[info.team]})",
                    priority=70,
                ),
            )
        elif info.kind in CONVEYOR_KINDS and eid in self._damaged:
            # Conveyor destroyed = potential chain break
            self.events.append(
                Event(
                    turn=turn,
                    kind="break",
                    team=info.team,
                    entity_id=eid,
                    pos=info.pos,
                    description=f"Conveyor break: {info.kind} #{eid} destroyed at {info.pos}",
                    priority=80,
                ),
            )
        elif info.kind == "core":
            self.events.append(
                Event(
                    turn=turn,
                    kind="death",
                    team=info.team,
                    entity_id=eid,
                    pos=info.pos,
                    description=f"CORE DESTROYED - Team {TEAM_LABEL[info.team]} loses!",
                    priority=100,
                ),
            )

    def _handle_hp(self, turn: int, hp_update: object) -> None:
        eid = hp_update.id
        delta = hp_update.delta
        info = self.entities.get(eid)
        if info is None:
            return

        info.hp += delta

        if delta < 0:
            self._damaged.add(eid)
            if info.kind == "core":
                self.events.append(
                    Event(
                        turn=turn,
                        kind="combat",
                        team=1 - info.team,
                        pos=info.pos,
                        description=f"Core hit! Team {TEAM_LABEL[info.team]} core: {info.hp}/{info.max_hp} HP (took {abs(delta)} dmg)",
                        priority=90,
                    ),
                )
            elif info.kind in TURRET_KINDS or info.kind == "harvester":
                self.events.append(
                    Event(
                        turn=turn,
                        kind="combat",
                        team=1 - info.team,
                        entity_id=eid,
                        pos=info.pos,
                        description=f"{info.kind.title()} #{eid} at {info.pos} took {abs(delta)} dmg ({info.hp}/{info.max_hp})",
                        priority=40,
                    ),
                )

    def _snapshot_resources(self, turn: int) -> None:
        self.resources_at_turn[turn] = TurnState(
            ti=dict(self.resources.ti),
            ax=dict(self.resources.ax),
            ti_collected=dict(self.resources.ti_collected),
            ax_collected=dict(self.resources.ax_collected),
        )

    def _handle_resources(self, turn: int, players: object) -> None:
        for t, p in ((0, players.a), (1, players.b)):
            new_collected = p.titanium_collected + p.axionite_collected

            self.resources.ti[t] = p.titanium
            self.resources.ax[t] = p.axionite
            self.resources.ti_collected[t] = p.titanium_collected
            self.resources.ax_collected[t] = p.axionite_collected

            # Track income rate
            self._income_window[t].append((turn, new_collected))
            # Keep last 100 turns
            while self._income_window[t] and self._income_window[t][0][0] < turn - 100:
                self._income_window[t].pop(0)

            if len(self._income_window[t]) >= 2:
                w = self._income_window[t]
                dt = w[-1][0] - w[0][0]
                if dt > 0:
                    rate = (w[-1][1] - w[0][1]) / dt
                    old_rate = self._prev_income[t]

                    # Detect significant income changes
                    if old_rate > 0.1 and rate < old_rate * 0.5:
                        self.events.append(
                            Event(
                                turn=turn,
                                kind="economy",
                                team=t,
                                description=f"Team {TEAM_LABEL[t]} income dropped: {old_rate:.2f} -> {rate:.2f}/turn",
                                details={"old_rate": old_rate, "new_rate": rate},
                                priority=70,
                            ),
                        )
                    elif rate > 0.1 and old_rate < 0.05:
                        self.events.append(
                            Event(
                                turn=turn,
                                kind="economy",
                                team=t,
                                description=f"Team {TEAM_LABEL[t]} first income: {rate:.2f}/turn",
                                details={"rate": rate},
                                priority=50,
                            ),
                        )

                    self._prev_income[t] = rate

    def _handle_fire(self, turn: int, fire: object) -> None:
        f_from = getattr(fire, "from")
        from_pos = (f_from.x, f_from.y)
        to_pos = (fire.to.x, fire.to.y)

        firer_id = self.building_at.get(from_pos)
        firer = self.entities.get(firer_id) if firer_id else None
        target_id = None
        target_kind = "?"
        for eid, info in self.entities.items():
            if info.pos == to_pos and info.kind in MOBILE_KINDS | {"core"}:
                target_id = eid
                target_kind = info.kind
                break

        firer_kind = firer.kind if firer else "turret"
        self.events.append(
            Event(
                turn=turn,
                kind="turret",
                team=firer.team if firer else None,
                pos=from_pos,
                description=f"{firer_kind} at {from_pos} fires at {to_pos} (target: {target_kind})",
                details={"from": from_pos, "to": to_pos, "target_id": target_id},
                priority=35,
            ),
        )

    def _handle_bot_output(self, turn: int, bo: object) -> None:
        info = BotDebugInfo(raw=bo.stdout)

        # Try to parse structured debug JSON from stdout
        for raw_line in bo.stdout.strip().split("\n"):
            line = raw_line.strip()
            if line.startswith("{") and '"_dbg"' in line:
                with contextlib.suppress(json.JSONDecodeError):
                    info.parsed = json.loads(line)

        self.bot_output[turn][bo.id] = info

        if bo.tled:
            ent = self.entities.get(bo.id)
            self.events.append(
                Event(
                    turn=turn,
                    kind="tle",
                    team=ent.team if ent else None,
                    entity_id=bo.id,
                    pos=ent.pos if ent else None,
                    description=f"TLE: entity #{bo.id} ({ent.kind if ent else '?'}) timed out ({bo.exec_time_us}us)",
                    priority=75,
                ),
            )

        if info.parsed and bo.id in self.entities:
            ent = self.entities[bo.id]
            dbg = info.parsed
            # Detect state transitions in structured debug
            state = dbg.get("state")
            prev_state = dbg.get("prev_state")
            if prev_state and state and prev_state != state:
                self.events.append(
                    Event(
                        turn=turn,
                        kind="state",
                        team=ent.team,
                        entity_id=bo.id,
                        pos=ent.pos,
                        description=f"Builder #{bo.id} state: {prev_state} -> {state}",
                        details={"debug": dbg},
                        priority=45,
                    ),
                )

    def _detect_idle(self, turn: int) -> None:
        for eid, info in self.entities.items():
            if info.kind != "builder_bot":
                continue
            if eid in self._acted:
                self._idle_streak[eid] = 0
            else:
                self._idle_streak[eid] += 1
                streak = self._idle_streak[eid]
                # Only report at specific thresholds to avoid spam
                if streak in (10, 30, 60):
                    self.events.append(
                        Event(
                            turn=turn,
                            kind="idle",
                            team=info.team,
                            entity_id=eid,
                            pos=info.pos,
                            description=f"Builder #{eid} idle for {streak} turns at {info.pos}",
                            priority=25 + (15 if streak >= 30 else 0),
                        ),
                    )

    # --- Map rendering ---

    def render_map_snippet(
        self,
        center: tuple[int, int],
        radius: int,
    ) -> str:
        """Render a small map area around a position."""
        cx, cy = center
        x1, y1 = max(0, cx - radius), max(0, cy - radius)
        x2, y2 = min(self.w - 1, cx + radius), min(self.h - 1, cy + radius)

        lines = []
        # Header with x coordinates
        header = "    " + "".join(f"{x % 10}" for x in range(x1, x2 + 1))
        lines.append(header)

        # Build entity lookup for current state
        pos_to_ent: dict[tuple[int, int], EntityInfo] = {}
        for info in self.entities.values():
            pos_to_ent[info.pos] = info

        for y in range(y1, y2 + 1):
            row = f"{y:3d} "
            for x in range(x1, x2 + 1):
                if (x, y) == center:
                    row += "*"  # Mark the center
                elif (x, y) in pos_to_ent:
                    info = pos_to_ent[(x, y)]
                    ch = ENTITY_CHARS.get(info.kind, "?")
                    if (
                        info.kind in ("conveyor", "armoured_conveyor")
                        and info.direction
                    ):
                        ch = DIR_ARROWS.get(info.direction, ">")
                    if info.team == 1:
                        ch = ch.upper()
                    row += ch
                else:
                    row += ENV_CHARS.get(self.env_grid[y][x], "?")
            lines.append(row)

        return "\n".join(lines)

    def render_full_map(self) -> str:
        """Render the full map at current state."""
        return self.render_map_snippet(
            (self.w // 2, self.h // 2),
            max(self.w, self.h),
        )

    # --- Entity summary ---

    def entity_summary(self, team: int) -> str:
        counts: Counter = Counter()
        for info in self.entities.values():
            if info.team == team:
                counts[info.kind] += 1
        parts = [f"{count} {kind}" for kind, count in sorted(counts.items())]
        return ", ".join(parts) if parts else "none"


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def format_narrative(
    debugger: ReplayDebugger,
    events: list[Event],
    *,
    team_filter: int | None = None,
    entity_filter: int | None = None,
    turn_range: tuple[int, int] | None = None,
    area: tuple[int, int, int, int] | None = None,
    event_types: set[str] | None = None,
    map_radius: int = 5,
    show_map: bool = True,
    verbose: bool = False,
) -> str:
    """Format events into an LLM-readable narrative."""
    total_turns = len(debugger.replay.turns)
    winner_raw = debugger.replay.winner if debugger.replay.HasField("winner") else None
    winner = TEAM_LABEL.get(winner_raw, "draw") if winner_raw is not None else "draw"

    # Filter events
    filtered = []
    for ev in events:
        if team_filter is not None and ev.team is not None and ev.team != team_filter:
            continue
        if entity_filter is not None and ev.entity_id != entity_filter:
            continue
        if turn_range and not (turn_range[0] <= ev.turn <= turn_range[1]):
            continue
        if area and ev.pos:
            x, y = ev.pos
            if not (area[0] <= x <= area[2] and area[1] <= y <= area[3]):
                continue
        if event_types and ev.kind not in event_types:
            continue
        filtered.append(ev)

    if not verbose:
        # Deduplicate: collapse runs of similar events
        filtered = _collapse_events(filtered)

    lines: list[str] = []

    # Header
    lines.append(f"=== Replay Debug: {total_turns} turns, winner: {winner} ===")
    lines.append(f"Map: {debugger.w}x{debugger.h}")
    for t in (0, 1):
        cp = debugger.core_pos.get(t)
        lines.append(f"Team {TEAM_LABEL[t]} core: {cp}")
    lines.append(f"Events found: {len(filtered)}")
    lines.append("")

    # Group events by phase
    phases = _identify_phases(filtered, total_turns)
    for phase_name, phase_events in phases:
        if not phase_events:
            continue

        lines.append(f"--- {phase_name} ---")

        prev_turn = -1
        for ev in phase_events:
            # Turn header if changed
            if ev.turn != prev_turn:
                # Show resources at this turn
                res = debugger.resources_at_turn.get(ev.turn, debugger.resources)
                res_str = (
                    f"  [A: {res.ti[0]}Ti {res.ax[0]}Ax | "
                    f"B: {res.ti[1]}Ti {res.ax[1]}Ax]"
                )
                lines.append(f"\nTurn {ev.turn}{res_str}")
                prev_turn = ev.turn

            # Event line
            team_tag = f"[{TEAM_LABEL[ev.team]}] " if ev.team is not None else ""
            lines.append(f"  {team_tag}{ev.description}")

            # Bot debug info if available
            if ev.entity_id and ev.turn in debugger.bot_output:
                dbg = debugger.bot_output[ev.turn].get(ev.entity_id)
                if dbg and dbg.parsed:
                    # Format structured debug compactly
                    d = {k: v for k, v in dbg.parsed.items() if k != "_dbg"}
                    lines.append(f"    beliefs: {json.dumps(d, separators=(',', ':'))}")
                elif dbg and dbg.raw.strip():
                    # Show raw stdout (truncated)
                    raw = dbg.raw.strip().replace("\n", " | ")
                    if len(raw) > 120:
                        raw = raw[:117] + "..."
                    lines.append(f"    stdout: {raw}")

            # Map snippet
            if show_map and ev.pos and ev.priority >= 50:
                snippet = debugger.render_map_snippet(ev.pos, map_radius)
                lines.extend(f"    {sl}" for sl in snippet.split("\n"))

        lines.append("")

    # Summary
    lines.append("=== Summary ===")
    lines.extend(f"Team {TEAM_LABEL[t]}: {debugger.entity_summary(t)}" for t in (0, 1))
    lines.append(f"Total events: {len(events)} ({len(filtered)} after filters)")

    return "\n".join(lines)


def format_json(
    debugger: ReplayDebugger,
    events: list[Event],
) -> str:
    """Format events as JSON for tool consumption."""
    total_turns = len(debugger.replay.turns)
    winner_raw = debugger.replay.winner if debugger.replay.HasField("winner") else None
    winner = TEAM_LABEL.get(winner_raw, "draw") if winner_raw is not None else "draw"

    result = {
        "total_turns": total_turns,
        "winner": winner,
        "map_size": [debugger.w, debugger.h],
        "core_positions": {
            TEAM_LABEL[t]: list(p) for t, p in debugger.core_pos.items()
        },
        "events": [
            {
                "turn": ev.turn,
                "kind": ev.kind,
                "team": TEAM_LABEL[ev.team] if ev.team is not None else None,
                "entity_id": ev.entity_id,
                "pos": list(ev.pos) if ev.pos else None,
                "description": ev.description,
                "details": ev.details,
                "priority": ev.priority,
            }
            for ev in events
        ],
        "final_state": {
            TEAM_LABEL[t]: {
                "resources": {
                    "titanium": debugger.resources.ti[t],
                    "axionite": debugger.resources.ax[t],
                },
                "entities": debugger.entity_summary(t),
            }
            for t in (0, 1)
        },
    }
    return json.dumps(result, indent=2)


def _collapse_events(events: list[Event]) -> list[Event]:
    """Collapse sequences of similar low-priority events."""
    if not events:
        return []

    result: list[Event] = []
    skip_turret_until = -1

    i = 0
    while i < len(events):
        ev = events[i]

        # Collapse turret fire sequences
        if ev.kind == "turret" and ev.turn > skip_turret_until:
            count = 1
            j = i + 1
            while (
                j < len(events)
                and events[j].kind == "turret"
                and events[j].turn - ev.turn <= 5
            ):
                count += 1
                j += 1
            if count > 3:
                result.append(
                    Event(
                        turn=ev.turn,
                        kind="turret",
                        team=ev.team,
                        pos=ev.pos,
                        description=f"{count} turret shots over turns {ev.turn}-{events[j - 1].turn}",
                        priority=35,
                    ),
                )
                skip_turret_until = events[j - 1].turn
                i = j
                continue

        if ev.kind == "turret" and ev.turn <= skip_turret_until:
            i += 1
            continue

        result.append(ev)
        i += 1

    return result


def _identify_phases(
    events: list[Event],
    total_turns: int,
) -> list[tuple[str, list[Event]]]:
    """Group events into game phases."""
    if not events:
        return []

    # Simple phase boundaries
    early_end = min(100, total_turns // 4)
    mid_end = min(500, total_turns * 2 // 3)

    phases = []
    early = [e for e in events if e.turn <= early_end]
    mid = [e for e in events if early_end < e.turn <= mid_end]
    late = [e for e in events if e.turn > mid_end]

    if early:
        phases.append((f"Early Game (turns 0-{early_end})", early))
    if mid:
        phases.append((f"Mid Game (turns {early_end + 1}-{mid_end})", mid))
    if late:
        phases.append((f"Late Game (turns {mid_end + 1}-{total_turns})", late))

    return phases


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Event-driven replay debugger")
    parser.add_argument(
        "replay",
        nargs="?",
        default="replay.replay26",
        help="Replay file path",
    )
    parser.add_argument("--team", choices=["A", "B"], help="Filter to team")
    parser.add_argument("--entity", type=int, help="Filter to entity ID")
    parser.add_argument("--turns", help="Turn range (e.g. 100-200)")
    parser.add_argument("--area", help="Bounding box (x1,y1,x2,y2)")
    parser.add_argument("--event", help="Event types (comma-separated)")
    parser.add_argument("--context", type=int, default=5, help="Map snippet radius")
    parser.add_argument("--no-map", action="store_true", help="Skip map snippets")
    parser.add_argument("--verbose", action="store_true", help="Show all events")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument(
        "--min-priority",
        type=int,
        default=0,
        help="Minimum event priority (0-100)",
    )

    args = parser.parse_args()

    replay = parse_replay(args.replay)
    debugger = ReplayDebugger(replay)
    events = debugger.scan()

    # Apply priority filter
    events = [e for e in events if e.priority >= args.min_priority]

    team_filter = {"A": 0, "B": 1}.get(args.team) if args.team else None
    turn_range = None
    if args.turns:
        parts = args.turns.split("-")
        turn_range = (int(parts[0]), int(parts[1]))
    area_filter = None
    if args.area:
        area_filter = tuple(int(x) for x in args.area.split(","))
    event_types = set(args.event.split(",")) if args.event else None

    if args.json:
        output = format_json(debugger, events)
    else:
        output = format_narrative(
            debugger,
            events,
            team_filter=team_filter,
            entity_filter=args.entity,
            turn_range=turn_range,
            area=area_filter,
            event_types=event_types,
            map_radius=args.context,
            show_map=not args.no_map,
            verbose=args.verbose,
        )

    print(output)


if __name__ == "__main__":
    main()
