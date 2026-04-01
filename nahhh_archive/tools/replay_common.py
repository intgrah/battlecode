from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from generated import cambc_pb2


TEAM_A = cambc_pb2.TEAM_A
TEAM_B = cambc_pb2.TEAM_B
TEAM_LABELS = {
    TEAM_A: "TEAM_A",
    TEAM_B: "TEAM_B",
}


WINNER_RE = re.compile(r"Winner:\s+(?P<winner>\S+)\s+\((?P<reason>.+),\s*turn\s+(?P<turn>\d+)\)")


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def team_label(team: int | None) -> str:
    if team is None:
        return "UNKNOWN"
    return TEAM_LABELS.get(team, f"TEAM_{team}")


def team_from_side(side: str) -> int:
    normalized = side.strip().upper()
    if normalized in {"A", "TEAM_A"}:
        return TEAM_A
    if normalized in {"B", "TEAM_B"}:
        return TEAM_B
    raise ValueError(f"Unsupported side {side!r}; expected A or B")


def other_team(team: int) -> int:
    return TEAM_B if team == TEAM_A else TEAM_A


def pos_tuple(pos: Any) -> tuple[int, int]:
    return (pos.x, pos.y)


def pos_text(pos: tuple[int, int] | None) -> str:
    if pos is None:
        return "-"
    return f"({pos[0]},{pos[1]})"


def resource_label(value: int) -> str:
    try:
        return cambc_pb2.ResourceType.Name(value)
    except ValueError:
        return str(value)


def load_replay(path: str | Path) -> cambc_pb2.Replay:
    replay = cambc_pb2.Replay()
    replay.ParseFromString(Path(path).read_bytes())
    return replay


def parse_run_summary(stdout: str) -> dict[str, Any]:
    match = WINNER_RE.search(stdout)
    if not match:
        return {}
    return {
        "winner_name": match.group("winner"),
        "win_reason": match.group("reason"),
        "turn": int(match.group("turn")),
    }


def _core_entity(core: cambc_pb2.CorePosition) -> dict[str, Any]:
    return {
        "id": core.id,
        "team": core.team,
        "kind": "core",
        "pos": pos_tuple(core.position),
        "hp": None,
        "max_hp": None,
        "action_cooldown": 0,
        "move_cooldown": None,
        "direction": None,
        "stored": None,
        "bridge_target": None,
        "marker_value": None,
        "harvester_resource_type": None,
        "ammo_type": None,
        "ammo_amount": None,
    }


def _entity_state(entity: cambc_pb2.Entity) -> dict[str, Any]:
    kind = entity.WhichOneof("kind") or "unknown"
    state = {
        "id": entity.id,
        "team": entity.team,
        "kind": kind,
        "pos": pos_tuple(entity.position),
        "hp": entity.hp,
        "max_hp": entity.max_hp,
        "action_cooldown": None,
        "move_cooldown": None,
        "direction": None,
        "stored": None,
        "bridge_target": None,
        "marker_value": None,
        "harvester_resource_type": None,
        "ammo_type": None,
        "ammo_amount": None,
    }
    payload = getattr(entity, kind, None)
    if payload is None:
        return state
    if kind == "builder_bot":
        state["action_cooldown"] = payload.action_cooldown
        state["move_cooldown"] = payload.move_cooldown
    elif kind == "core":
        state["action_cooldown"] = payload.action_cooldown
    elif kind in {"conveyor", "splitter", "armoured_conveyor", "gunner", "sentinel", "breach"}:
        state["direction"] = payload.direction
    if kind in {"conveyor", "splitter", "armoured_conveyor", "bridge", "foundry"}:
        state["stored"] = payload.stored
    if kind == "bridge":
        state["bridge_target"] = pos_tuple(payload.target)
    if kind == "marker":
        state["marker_value"] = payload.value
    if kind == "harvester":
        state["harvester_resource_type"] = payload.resource_type
    if kind in {"gunner", "sentinel", "breach", "launcher"}:
        state["ammo_type"] = payload.ammo_type
        state["ammo_amount"] = payload.ammo_amount
    return state


def initial_entities(replay: cambc_pb2.Replay) -> dict[int, dict[str, Any]]:
    entities: dict[int, dict[str, Any]] = {}
    for core in replay.map.cores:
        entities[core.id] = _core_entity(core)
    return entities


def _apply_entity_update(entities: dict[int, dict[str, Any]], update: cambc_pb2.Update) -> None:
    kind = update.WhichOneof("kind")
    if kind == "place_entity":
        entity = update.place_entity.entity
        entities[entity.id] = _entity_state(entity)
        return
    if kind == "move_builder_bot":
        state = entities.get(update.move_builder_bot.id)
        if state is not None:
            state["pos"] = pos_tuple(update.move_builder_bot.to)
        return
    if kind == "remove_entity":
        entities.pop(update.remove_entity.id, None)
        return
    if kind == "update_hp":
        state = entities.get(update.update_hp.id)
        if state is not None and state["hp"] is not None:
            state["hp"] += update.update_hp.delta
        return
    if kind == "set_action_cooldown":
        state = entities.get(update.set_action_cooldown.id)
        if state is not None:
            state["action_cooldown"] = update.set_action_cooldown.value
        return
    if kind == "set_move_cooldown":
        state = entities.get(update.set_move_cooldown.id)
        if state is not None:
            state["move_cooldown"] = update.set_move_cooldown.value


def _players_dict(players: cambc_pb2.Players | None) -> dict[str, dict[str, int]] | None:
    if players is None:
        return None
    return {
        "TEAM_A": {
            "titanium": players.a.titanium,
            "axionite": players.a.axionite,
            "resources_collected": players.a.resources_collected,
            "titanium_collected": players.a.titanium_collected,
            "axionite_collected": players.a.axionite_collected,
        },
        "TEAM_B": {
            "titanium": players.b.titanium,
            "axionite": players.b.axionite,
            "resources_collected": players.b.resources_collected,
            "titanium_collected": players.b.titanium_collected,
            "axionite_collected": players.b.axionite_collected,
        },
    }


def summarize_replay(path: str | Path) -> dict[str, Any]:
    replay_path = Path(path)
    replay = load_replay(replay_path)
    entities = initial_entities(replay)
    player_state: cambc_pb2.Players | None = None
    indicator_lines = 0
    indicator_dots = 0
    bot_output_events = 0
    stdout_events = 0
    tles_total = 0
    tles_by_team: Counter[str] = Counter()
    tles_by_turn: list[dict[str, Any]] = []
    bot_stats: dict[int, dict[str, Any]] = defaultdict(
        lambda: {
            "id": None,
            "team": "UNKNOWN",
            "kind": "unknown",
            "bot_output_events": 0,
            "stdout_events": 0,
            "tle_count": 0,
            "max_exec_us": 0,
            "total_exec_us": 0,
        }
    )

    for turn_no, turn in enumerate(replay.turns, start=1):
        tle_ids: list[int] = []
        for update in turn.updates:
            kind = update.WhichOneof("kind")
            if kind == "update_players":
                player_state = update.update_players.players
                continue
            if kind == "bot_output":
                event = update.bot_output
                state = entities.get(event.id)
                stat = bot_stats[event.id]
                stat["id"] = event.id
                if state is not None:
                    stat["team"] = team_label(state["team"])
                    stat["kind"] = state["kind"]
                stat["bot_output_events"] += 1
                stat["max_exec_us"] = max(stat["max_exec_us"], event.exec_time_us)
                stat["total_exec_us"] += event.exec_time_us
                bot_output_events += 1
                if event.stdout:
                    stat["stdout_events"] += 1
                    stdout_events += 1
                if event.tled:
                    stat["tle_count"] += 1
                    tles_total += 1
                    tles_by_team[stat["team"]] += 1
                    tle_ids.append(event.id)
                continue
            if kind == "indicator_line":
                indicator_lines += 1
            elif kind == "indicator_dot":
                indicator_dots += 1
            _apply_entity_update(entities, update)
        if tle_ids:
            tles_by_turn.append({"turn": turn_no, "ids": tle_ids})

    final_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for state in entities.values():
        final_counts[team_label(state["team"])][state["kind"]] += 1

    top_exec = sorted(
        (
            {
                **stat,
                "avg_exec_us": int(stat["total_exec_us"] / stat["bot_output_events"]) if stat["bot_output_events"] else 0,
            }
            for stat in bot_stats.values()
        ),
        key=lambda stat: (stat["tle_count"], stat["max_exec_us"], stat["total_exec_us"]),
        reverse=True,
    )

    map_info = {
        "width": replay.map.width,
        "height": replay.map.height,
        "cores": [
            {
                "id": core.id,
                "team": team_label(core.team),
                "pos": pos_tuple(core.position),
            }
            for core in replay.map.cores
        ],
    }
    has_winner = replay.HasField("winner")
    return {
        "path": str(replay_path),
        "map": map_info,
        "turns": len(replay.turns),
        "winner": team_label(replay.winner) if has_winner else None,
        "players": _players_dict(player_state),
        "final_entities": {
            team: dict(sorted(counter.items()))
            for team, counter in sorted(final_counts.items())
        },
        "bot_outputs": {
            "events": bot_output_events,
            "stdout_events": stdout_events,
            "tles_total": tles_total,
            "tles_by_team": dict(sorted(tles_by_team.items())),
            "first_tle_turn": tles_by_turn[0]["turn"] if tles_by_turn else None,
            "tled_turns": tles_by_turn[:10],
            "top_exec_entities": top_exec[:10],
        },
        "indicators": {
            "lines": indicator_lines,
            "dots": indicator_dots,
        },
    }


def trace_entity(
    path: str | Path,
    entity_id: int,
    turn_from: int = 1,
    turn_to: int | None = None,
    *,
    only_events: bool = False,
) -> dict[str, Any]:
    replay_path = Path(path)
    replay = load_replay(replay_path)
    entities = initial_entities(replay)
    records: list[dict[str, Any]] = []
    if turn_to is None:
        turn_to = len(replay.turns)

    for turn_no, turn in enumerate(replay.turns, start=1):
        current = entities.get(entity_id)
        record = {
            "turn": turn_no,
            "present": current is not None,
            "team": team_label(current["team"]) if current is not None else None,
            "kind": current["kind"] if current is not None else None,
            "pos_before": current["pos"] if current is not None else None,
            "pos_after": current["pos"] if current is not None else None,
            "hp_before": current["hp"] if current is not None else None,
            "hp_after": current["hp"] if current is not None else None,
            "action_cooldown": current["action_cooldown"] if current is not None else None,
            "move_cooldown": current["move_cooldown"] if current is not None else None,
            "spawned": False,
            "removed": False,
            "moved": False,
            "hp_delta": 0,
            "exec_time_us": None,
            "tled": False,
            "stdout": [],
            "indicator_lines": 0,
            "indicator_dots": 0,
            "builder_attack": False,
        }

        for update in turn.updates:
            kind = update.WhichOneof("kind")
            if kind == "place_entity" and update.place_entity.entity.id == entity_id:
                record["spawned"] = True
            elif kind == "move_builder_bot" and update.move_builder_bot.id == entity_id:
                record["moved"] = True
                record["pos_after"] = pos_tuple(update.move_builder_bot.to)
            elif kind == "remove_entity" and update.remove_entity.id == entity_id:
                record["removed"] = True
            elif kind == "update_hp" and update.update_hp.id == entity_id:
                record["hp_delta"] += update.update_hp.delta
            elif kind == "set_action_cooldown" and update.set_action_cooldown.id == entity_id:
                record["action_cooldown"] = update.set_action_cooldown.value
            elif kind == "set_move_cooldown" and update.set_move_cooldown.id == entity_id:
                record["move_cooldown"] = update.set_move_cooldown.value
            elif kind == "bot_output" and update.bot_output.id == entity_id:
                record["exec_time_us"] = update.bot_output.exec_time_us
                record["tled"] = update.bot_output.tled
                if update.bot_output.stdout:
                    record["stdout"].extend(
                        line for line in update.bot_output.stdout.splitlines() if line
                    )
            elif kind == "indicator_line" and update.indicator_line.id == entity_id:
                record["indicator_lines"] += 1
            elif kind == "indicator_dot" and update.indicator_dot.id == entity_id:
                record["indicator_dots"] += 1
            elif kind == "builder_attack" and update.builder_attack.id == entity_id:
                record["builder_attack"] = True
            _apply_entity_update(entities, update)

        current = entities.get(entity_id)
        record["present"] = current is not None
        if current is not None:
            record["team"] = team_label(current["team"])
            record["kind"] = current["kind"]
            record["pos_after"] = current["pos"]
            record["hp_after"] = current["hp"]
            record["action_cooldown"] = current["action_cooldown"]
            record["move_cooldown"] = current["move_cooldown"]
        else:
            record["pos_after"] = None
            record["hp_after"] = None

        if turn_no < turn_from or turn_no > turn_to:
            continue
        if only_events and not (
            record["spawned"]
            or record["removed"]
            or record["moved"]
            or record["hp_delta"]
            or record["tled"]
            or record["stdout"]
            or record["indicator_lines"]
            or record["indicator_dots"]
            or record["builder_attack"]
        ):
            continue
        records.append(record)

    return {
        "path": str(replay_path),
        "entity_id": entity_id,
        "turn_from": turn_from,
        "turn_to": turn_to,
        "records": records,
    }


