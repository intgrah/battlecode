import math

from .snapshot import VISION_SQ, GameState


def _tiles_in_vision(cx: int, cy: int, rsq: int, w: int, h: int) -> set[tuple[int, int]]:
    r = int(math.isqrt(rsq)) + 1
    tiles = set()
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            if dx * dx + dy * dy <= rsq:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h:
                    tiles.add((nx, ny))
    return tiles


def vision_coverage(state: GameState, team: int) -> dict:
    w, h = state.width, state.height
    visible = set()
    for e in state.team_entities(team):
        rsq = VISION_SQ.get(e.kind)
        if rsq is None:
            continue
        visible |= _tiles_in_vision(e.pos[0], e.pos[1], rsq, w, h)

    passable = sum(1 for y in range(h) for x in range(w) if state.tiles[y][x] != 1)
    return {
        "visible_tiles": len(visible),
        "passable_tiles": passable,
        "coverage_pct": 100 * len(visible) / passable if passable > 0 else 0,
        "visible_set": visible,
    }


def cumulative_vision(states: list[GameState], team: int) -> list[dict]:
    ever_seen: set[tuple[int, int]] = set()
    results = []
    for state in states:
        vc = vision_coverage(state, team)
        ever_seen |= vc["visible_set"]
        passable = vc["passable_tiles"]
        results.append({
            "turn": state.turn,
            "current_coverage_pct": vc["coverage_pct"],
            "cumulative_coverage_pct": 100 * len(ever_seen) / passable if passable > 0 else 0,
            "cumulative_tiles": len(ever_seen),
        })
    return results


def ore_discovery(states: list[GameState], team: int) -> list[dict]:
    all_ores = set()
    if states:
        for x, y, _ in states[0].ore_tiles():
            all_ores.add((x, y))
    total_ore = len(all_ores)

    discovered: set[tuple[int, int]] = set()
    harvested: set[tuple[int, int]] = set()
    results = []

    for state in states:
        vc = vision_coverage(state, team)
        newly_seen = vc["visible_set"] & all_ores
        discovered |= newly_seen

        for e in state.team_entities(team, "harvester"):
            if e.pos in all_ores:
                harvested.add(e.pos)

        undiscovered = all_ores - discovered
        results.append({
            "turn": state.turn,
            "total_ore": total_ore,
            "discovered": len(discovered),
            "undiscovered": len(undiscovered),
            "undiscovered_positions": sorted(undiscovered)[:20],
            "discovery_pct": 100 * len(discovered) / total_ore if total_ore > 0 else 0,
            "harvested": len(harvested),
            "harvest_pct": 100 * len(harvested) / total_ore if total_ore > 0 else 0,
        })
    return results


def map_control(state: GameState) -> dict:
    w, h = state.width, state.height
    team_vis = {0: set(), 1: set()}
    for t in (0, 1):
        for e in state.team_entities(t):
            rsq = VISION_SQ.get(e.kind)
            if rsq is None:
                continue
            team_vis[t] |= _tiles_in_vision(e.pos[0], e.pos[1], rsq, w, h)

    exclusive_a = team_vis[0] - team_vis[1]
    exclusive_b = team_vis[1] - team_vis[0]
    contested = team_vis[0] & team_vis[1]
    dark = set()
    for y in range(h):
        for x in range(w):
            if state.tiles[y][x] != 1 and (x, y) not in team_vis[0] and (x, y) not in team_vis[1]:
                dark.add((x, y))

    passable = sum(1 for y in range(h) for x in range(w) if state.tiles[y][x] != 1)
    return {
        "team_a_exclusive": len(exclusive_a),
        "team_b_exclusive": len(exclusive_b),
        "contested": len(contested),
        "dark": len(dark),
        "passable": passable,
    }


def analyze_spatial(states: list[GameState], team: int) -> dict:
    cum = cumulative_vision(states, team)
    ore = ore_discovery(states, team)
    control = map_control(states[-1]) if states else {}

    return {
        "vision_timeline": cum,
        "ore_timeline": ore,
        "map_control": control,
    }
