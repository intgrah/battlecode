"""Extract critical events from a replay + DEBUG_DUMP-enabled bot stdout.

Usage:
    uv run python pkg/hitl/scripts/extract.py path/to/replay.replay26 [stdout.log]

Writes events into the hitl SQLite DB via `hitl.db.Store`. This script lives
outside the `hitl` runtime package because it depends on `proto` to parse
replays; proto is dev-machine-only. The server deploys only the `hitl`
package and never needs proto.

Replay is a protobuf (proto.cambc_pb2.Replay). Bot stdout lines we parse:
    ##VIS## {<json>}                     # belief dump per unit per turn
    task=<us>us [<task_name>]            # selected task name
    total=<us>us                         # total turn time
    post_init=<us>us                     # post_init time on first turn
"""

import argparse
import contextlib
import json
import secrets
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from hitl.config import blobs_dir, db_path, pngs_dir
from hitl.db import Store
from hitl.schema import (
    BeliefState,
    Event,
    EventTrigger,
    Game,
    GameState,
    OutcomeAuto,
)
from PIL import Image, ImageDraw
from proto.cambc_pb2 import Entity, Map, Replay


@dataclass
class UnitTurn:
    """What the bot believed and what happened on one (turn, unit) slot."""

    turn: int
    unit_id: int
    unit_type: str
    team: str
    my_pos: tuple[int, int]
    hp: int
    max_hp: int
    belief: dict = field(default_factory=dict)
    tled: bool = False
    stdout: str = ""
    actions: list[str] = field(default_factory=list)


def parse_stdout(text: str) -> dict:
    """Extract the latest ##VIS## JSON + task/total from a bot's stdout."""
    out: dict = {"vis": None, "task": None, "total_us": None, "role": None}
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("##VIS##"):
            with contextlib.suppress(json.JSONDecodeError):
                out["vis"] = json.loads(line[len("##VIS##") :].strip())
        elif line.startswith("task="):
            with contextlib.suppress(IndexError):
                out["task"] = line.split("[", 1)[1].rstrip("]")
        elif line.startswith("total="):
            with contextlib.suppress(ValueError):
                out["total_us"] = int(line.split("=", 1)[1].rstrip("us"))
    vis = out["vis"]
    if isinstance(vis, dict):
        role = vis.get("role")
        out["role"] = role.get("data") if isinstance(role, dict) else role
    return out


_KIND_TO_TYPE: dict[str, str] = {
    "builder_bot": "BuilderBot",
    "conveyor": "Conveyor",
    "splitter": "Splitter",
    "armoured_conveyor": "ArmouredConveyor",
    "bridge": "Bridge",
    "harvester": "Harvester",
    "foundry": "Foundry",
    "road": "Road",
    "barrier": "Barrier",
    "marker": "Marker",
    "core": "Core",
    "gunner": "Gunner",
    "sentinel": "Sentinel",
    "breach": "Breach",
    "launcher": "Launcher",
}


def _etype(entity: Entity) -> str:
    kind = entity.WhichOneof("kind")
    return _KIND_TO_TYPE.get(kind or "", "Unknown")


def _team(t: int) -> str:
    return "A" if t == 0 else "B"


def unit_turns(replay: Replay) -> Iterator[UnitTurn]:
    """Yield one UnitTurn per (turn, unit) that produced bot output."""
    alive: dict[int, tuple[str, str, int, int, int, int]] = {}
    for t_idx, turn in enumerate(replay.turns):
        pending: dict[int, UnitTurn] = {}
        for update in turn.updates:
            which = update.WhichOneof("kind")
            if which == "place_entity":
                e = update.place_entity.entity
                alive[e.id] = (
                    _etype(e),
                    _team(e.team),
                    e.position.x,
                    e.position.y,
                    e.hp,
                    e.max_hp,
                )
            elif which == "bot_output":
                bo = update.bot_output
                meta = alive.get(bo.id)
                if meta is None:
                    continue
                ut_type, team, x, y, hp, mhp = meta
                pending[bo.id] = UnitTurn(
                    turn=t_idx,
                    unit_id=bo.id,
                    unit_type=ut_type,
                    team=team,
                    my_pos=(x, y),
                    hp=hp,
                    max_hp=mhp,
                    belief=parse_stdout(bo.stdout),
                    tled=bool(bo.tled),
                    stdout=bo.stdout,
                )
            elif which == "move_builder_bot":
                m = update.move_builder_bot
                if m.id in pending:
                    prev = pending[m.id]
                    dx = m.to.x - prev.my_pos[0]
                    dy = m.to.y - prev.my_pos[1]
                    prev.actions.append(f"move dx={dx} dy={dy}")
                    # Keep `alive` position in sync so next turn starts from
                    # the new tile.
                    ut_type, team, _, _, hp, mhp = alive[m.id]
                    alive[m.id] = (ut_type, team, m.to.x, m.to.y, hp, mhp)
            elif which == "builder_attack":
                a = update.builder_attack
                if a.id in pending:
                    pending[a.id].actions.append("fire self-tile")
            elif which == "update_hp":
                uh = update.update_hp
                if uh.id in alive:
                    ut_type, team, x, y, hp, mhp = alive[uh.id]
                    alive[uh.id] = (ut_type, team, x, y, hp + uh.delta, mhp)
            elif which == "remove_entity":
                alive.pop(update.remove_entity.id, None)
        yield from pending.values()


@dataclass
class _UnitHistory:
    """Per-unit state carried across turns to fire cross-turn triggers."""

    prev_role: str | None = None
    prev_hp: int | None = None
    idle_turns: int = 0
    last_trigger_turn: dict[EventTrigger, int] = field(default_factory=dict)


class TriggerDetector:
    """Stateful detector. Feed it UnitTurns in round order; it emits
    (trigger, reason_str) pairs per turn."""

    HP_DROP_THRESHOLD = 8
    IDLE_STREAK = 6
    MIN_GAP_BETWEEN_SAME_TRIGGER = 20

    def __init__(self) -> None:
        self.hist: dict[int, _UnitHistory] = {}

    def detect(self, ut: UnitTurn) -> Iterable[EventTrigger]:
        h = self.hist.setdefault(ut.unit_id, _UnitHistory())
        fired: list[EventTrigger] = []

        if ut.tled:
            self._fire(h, ut.turn, EventTrigger.ASTAR_FAILED, fired)

        role = ut.belief.get("role")
        if h.prev_role is not None and role is not None and role != h.prev_role:
            self._fire(h, ut.turn, EventTrigger.ROLE_CHANGED, fired)

        if h.prev_hp is not None and ut.hp <= h.prev_hp - self.HP_DROP_THRESHOLD:
            self._fire(h, ut.turn, EventTrigger.HP_DROP, fired)

        if not ut.actions:
            h.idle_turns += 1
            if h.idle_turns == self.IDLE_STREAK:
                self._fire(h, ut.turn, EventTrigger.IDLE_WITH_TI, fired)
        else:
            h.idle_turns = 0

        h.prev_role = role if role is not None else h.prev_role
        h.prev_hp = ut.hp
        return fired

    def _fire(
        self,
        h: _UnitHistory,
        turn: int,
        trig: EventTrigger,
        out: list[EventTrigger],
    ) -> None:
        last = h.last_trigger_turn.get(trig, -10_000)
        if turn - last < self.MIN_GAP_BETWEEN_SAME_TRIGGER:
            return
        h.last_trigger_turn[trig] = turn
        out.append(trig)


_TILE_COLOUR: dict[int, tuple[int, int, int]] = {
    0: (40, 40, 48),
    1: (8, 8, 10),
    2: (202, 169, 74),
    3: (74, 200, 196),
}
_TEAM_COLOUR: dict[str, tuple[int, int, int]] = {
    "A": (79, 144, 255),
    "B": (255, 123, 91),
}


def render_png(ut: UnitTurn, replay_map: Map, event_id: str) -> Path:
    """Render base terrain + fog + bot position overlay."""
    w, h = replay_map.width, replay_map.height
    scale = max(6, min(24, 480 // max(w, h)))
    img_w, img_h = w * scale, h * scale + 18
    img = Image.new("RGBA", (img_w, img_h), (18, 20, 25, 255))
    d = ImageDraw.Draw(img)

    # Base terrain
    for y in range(h):
        row = replay_map.rows[y].tiles
        for x in range(w):
            c = _TILE_COLOUR.get(row[x], (40, 40, 48))
            d.rectangle(
                (x * scale, y * scale, x * scale + scale - 1, y * scale + scale - 1),
                fill=c,
            )

    # Fog overlay from the bot's belief state
    vis = ut.belief.get("vis") or {}
    unseen = ((vis or {}).get("unseen") or {}).get("data") or []
    if len(unseen) == w * h:
        fog = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
        fd = ImageDraw.Draw(fog)
        for i, u in enumerate(unseen):
            if u:
                yy, xx = divmod(i, w)
                fd.rectangle(
                    (
                        xx * scale,
                        yy * scale,
                        xx * scale + scale - 1,
                        yy * scale + scale - 1,
                    ),
                    fill=(0, 0, 0, 170),
                )
        img = Image.alpha_composite(img, fog)
        d = ImageDraw.Draw(img)

    # The bot itself
    px, py = ut.my_pos[0] * scale, ut.my_pos[1] * scale
    d.rectangle(
        (px + 1, py + 1, px + scale - 2, py + scale - 2),
        fill=_TEAM_COLOUR.get(ut.team, (200, 200, 200)),
        outline=(255, 255, 255, 255),
    )

    # Caption strip along the bottom
    d.rectangle((0, img_h - 18, img_w, img_h), fill=(30, 34, 44, 255))
    d.text(
        (6, img_h - 14),
        f"t{ut.turn}  {ut.unit_type}#{ut.unit_id}  team {ut.team}  hp {ut.hp}/{ut.max_hp}",
        fill=(230, 230, 230, 255),
    )

    path = pngs_dir() / f"{event_id}.png"
    img.convert("RGB").save(path, "PNG")
    return path


def infer_auto_tags(replay: Replay) -> list[OutcomeAuto]:
    """Derive auto-tags from the replay end-state (not yet implemented)."""
    _ = replay
    return []


def extract_replay(replay_path: Path, stdout_log: Path | None = None) -> int:
    _ = stdout_log  # reserved for when stdout lives outside the replay
    replay = Replay()
    replay.ParseFromString(replay_path.read_bytes())
    game_id = replay_path.stem
    end_turn = len(replay.turns) - 1

    store = Store(db_path())
    store.upsert_game(
        Game(
            replay_id=game_id,
            our_side="A",
            opponent="unknown",
            map_name=getattr(replay.map, "name", "") or "unknown",
            winner=None,
            end_turn=end_turn,
            outcome_auto=infer_auto_tags(replay),
        )
    )

    detector = TriggerDetector()
    n = 0
    for ut in unit_turns(replay):
        for trig in detector.detect(ut):
            event_id = f"{game_id}-t{ut.turn}-u{ut.unit_id}-{secrets.token_hex(3)}"
            belief = BeliefState(
                role=ut.belief.get("role"),
                ore_target=None,
                dangling_output=None,
                scout_target=None,
                symmetry=None,
                ti=0,
                ax=0,
                scale=1.0,
            )
            gstate = GameState(
                my_pos=ut.my_pos,
                hp=ut.hp,
                max_hp=ut.max_hp,
                action_cooldown=0,
                move_cooldown=0,
                nearby_enemies=[],
                nearby_allies=[],
            )
            evt = Event(
                event_id=event_id,
                replay_id=game_id,
                turn=ut.turn,
                unit_id=ut.unit_id,
                unit_type=ut.unit_type,
                team=ut.team,  # type: ignore[arg-type]
                trigger=trig,
                belief=belief,
                game=gstate,
                bot_action="; ".join(ut.actions) or "none",
            )
            blob = blobs_dir() / f"{event_id}.json"
            blob.write_text(evt.model_dump_json())
            png = render_png(ut, replay.map, event_id)
            store.insert_event(evt, blob_path=blob, png_path=png)
            n += 1
    return n


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("replay", type=Path)
    parser.add_argument("stdout_log", type=Path, nargs="?", default=None)
    args = parser.parse_args()
    n = extract_replay(args.replay, args.stdout_log)
    print(f"extracted {n} events from {args.replay.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
