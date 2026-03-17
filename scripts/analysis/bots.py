import math
from collections import defaultdict

from .snapshot import GameState


def pairwise_separation(state: GameState, team: int) -> dict:
    bots = state.team_entities(team, "builder_bot")
    if len(bots) < 2:
        return {"avg": 0, "min": 0, "max": 0, "count": len(bots)}

    dists = []
    for i in range(len(bots)):
        for j in range(i + 1, len(bots)):
            dx = bots[i].pos[0] - bots[j].pos[0]
            dy = bots[i].pos[1] - bots[j].pos[1]
            dists.append(math.sqrt(dx * dx + dy * dy))

    return {
        "avg": sum(dists) / len(dists),
        "min": min(dists),
        "max": max(dists),
        "count": len(bots),
    }


def bot_clustering(states: list[GameState], team: int) -> list[dict]:
    results = []
    for state in states:
        sep = pairwise_separation(state, team)
        bots = state.team_entities(team, "builder_bot")

        core = state.core_pos.get(team)
        if core and bots:
            core_dists = [math.sqrt((b.pos[0] - core[0])**2 + (b.pos[1] - core[1])**2) for b in bots]
            avg_core_dist = sum(core_dists) / len(core_dists)
            max_core_dist = max(core_dists)
        else:
            avg_core_dist = 0
            max_core_dist = 0

        results.append({
            "turn": state.turn,
            "bot_count": sep["count"],
            "avg_separation": sep["avg"],
            "min_separation": sep["min"],
            "max_separation": sep["max"],
            "avg_core_dist": avg_core_dist,
            "max_core_dist": max_core_dist,
        })
    return results


def patrol_analysis(states: list[GameState], team: int) -> dict:
    bot_positions: dict[int, list[tuple[int, tuple[int, int]]]] = defaultdict(list)

    for state in states:
        for e in state.team_entities(team, "builder_bot"):
            bot_positions[e.id].append((state.turn, e.pos))

    patrol_bots = 0
    idle_bots = 0
    unique_tiles_per_bot = []

    for bot_id, history in bot_positions.items():
        if len(history) < 5:
            continue

        positions = [p for _, p in history]
        unique = set(positions)
        unique_tiles_per_bot.append(len(unique))

        if len(unique) <= 2 and len(history) >= 10:
            idle_bots += 1
        elif len(unique) >= 5:
            patrol_bots += 1

    return {
        "total_bots_tracked": len(bot_positions),
        "patrol_bots": patrol_bots,
        "stuck_bots": idle_bots,
        "avg_unique_tiles": sum(unique_tiles_per_bot) / len(unique_tiles_per_bot) if unique_tiles_per_bot else 0,
    }


def analyze_bots(states: list[GameState], team: int) -> dict:
    clustering = bot_clustering(states, team)
    patrol = patrol_analysis(states, team)
    return {
        "clustering_timeline": clustering,
        "patrol": patrol,
    }
