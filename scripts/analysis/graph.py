from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from .constants import CONVEYOR_KINDS, Pos
from .snapshot import building_entity_at, conveyor_output, core_tiles, team_entities
from .types import GameState


def build_conveyor_graph(state: GameState, team: int) -> nx.DiGraph:
    g: nx.DiGraph = nx.DiGraph()
    ct = core_tiles(state.core_pos, team)

    for e in team_entities(state, team):
        if e.kind not in CONVEYOR_KINDS:
            continue
        out = conveyor_output(e)
        if out is None:
            continue
        g.add_node(e.pos, kind=e.kind, hp=e.hp)
        te = building_entity_at(state, out)
        if (
            te and te.team == team and (te.kind in CONVEYOR_KINDS or te.kind == "core")
        ) or out in ct:
            g.add_edge(e.pos, out)

    for tile in ct:
        if tile in g:
            g.nodes[tile]["is_core"] = True

    return g


def harvester_entry_points(state: GameState, team: int) -> dict[Pos, list[Pos]]:
    result: dict[Pos, list[Pos]] = {}
    for e in team_entities(state, team, "harvester"):
        entries: list[Pos] = []
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if dx == 0 and dy == 0:
                    continue
                adj: Pos = (e.pos[0] + dx, e.pos[1] + dy)
                te = building_entity_at(state, adj)
                if te and te.team == team and te.kind in CONVEYOR_KINDS:
                    entries.append(adj)
        result[e.pos] = entries
    return result


def reachable_from_core(g: nx.DiGraph, ct: set[Pos]) -> set[Pos]:
    sinks = ct & set(g.nodes)
    reachable: set[Pos] = set()
    for s in sinks:
        reachable |= nx.ancestors(g, s)
        reachable.add(s)
    return reachable


def connected_harvesters(
    state: GameState,
    team: int,
) -> tuple[list[Pos], list[Pos]]:
    g = build_conveyor_graph(state, team)
    ct = core_tiles(state.core_pos, team)
    reachable = reachable_from_core(g, ct)
    entries = harvester_entry_points(state, team)

    connected: list[Pos] = []
    disconnected: list[Pos] = []
    for hpos, eps in entries.items():
        if any(ep in reachable for ep in eps):
            connected.append(hpos)
        else:
            disconnected.append(hpos)
    return connected, disconnected


def dead_conveyor_positions(state: GameState, team: int) -> list[Pos]:
    g = build_conveyor_graph(state, team)
    ct = core_tiles(state.core_pos, team)
    reachable = reachable_from_core(g, ct)
    entries = harvester_entry_points(state, team)

    harvester_adj: set[Pos] = set()
    for eps in entries.values():
        harvester_adj.update(eps)

    useful: set[Pos] = set()
    for src in harvester_adj & reachable:
        for sink in ct & set(g.nodes):
            if nx.has_path(g, src, sink):
                useful |= set(nx.shortest_path(g, src, sink))

    all_conv = {e.pos for e in team_entities(state, team) if e.kind in CONVEYOR_KINDS}
    return sorted(all_conv - useful)


def betweenness_centrality(state: GameState, team: int) -> list[tuple[Pos, float]]:
    g = build_conveyor_graph(state, team)
    if len(g) < 2:
        return []

    bc: dict[Pos, float] = nx.betweenness_centrality(g, normalized=True)
    return sorted(bc.items(), key=lambda x: -x[1])[:5]


@dataclass
class MaxFlowResult:
    max_flow: float
    theoretical_max: float
    utilization: float


def max_flow_capacity(state: GameState, team: int) -> MaxFlowResult:
    g = build_conveyor_graph(state, team)
    ct = core_tiles(state.core_pos, team)
    entries = harvester_entry_points(state, team)

    fg: nx.DiGraph = nx.DiGraph()
    for u, v in g.edges():
        fg.add_edge(u, v, capacity=1.0)

    super_source: Pos = (-1, -1)
    super_sink: Pos = (-2, -2)
    for eps in entries.values():
        for ep in eps:
            if ep in g:
                fg.add_edge(super_source, ep, capacity=0.25)

    for tile in ct & set(g.nodes):
        fg.add_edge(tile, super_sink, capacity=float("inf"))

    if super_source not in fg or super_sink not in fg:
        return MaxFlowResult(0.0, len(entries) * 0.25, 0.0)

    try:
        flow_value, _ = nx.maximum_flow(fg, super_source, super_sink)
    except nx.NetworkXError:
        flow_value = 0.0

    theoretical = len(entries) * 0.25
    return MaxFlowResult(
        max_flow=flow_value,
        theoretical_max=theoretical,
        utilization=flow_value / theoretical if theoretical > 0 else 0.0,
    )


def articulation_points(state: GameState, team: int) -> list[tuple[Pos, int]]:
    g = build_conveyor_graph(state, team)
    ct = core_tiles(state.core_pos, team)
    entries = harvester_entry_points(state, team)
    reachable = reachable_from_core(g, ct)

    harv_to_entries: dict[Pos, list[Pos]] = {}
    for hpos, eps in entries.items():
        connected_eps = [ep for ep in eps if ep in reachable]
        if connected_eps:
            harv_to_entries[hpos] = connected_eps

    results: list[tuple[Pos, int]] = []
    for node in set(g.nodes) - ct:
        if node not in reachable:
            continue
        g_minus = g.copy()
        g_minus.remove_node(node)
        new_reachable = reachable_from_core(g_minus, ct)

        impact = 0
        for eps in harv_to_entries.values():
            was = any(ep in reachable for ep in eps)
            now = any(ep in new_reachable for ep in eps if ep != node)
            if was and not now:
                impact += 1

        if impact > 0:
            results.append((node, impact))

    return sorted(results, key=lambda x: -x[1])[:5]


def shortest_path_lengths(state: GameState, team: int) -> dict[Pos, int | None]:
    g = build_conveyor_graph(state, team)
    ct = core_tiles(state.core_pos, team)
    entries = harvester_entry_points(state, team)

    result: dict[Pos, int | None] = {}
    for hpos, eps in entries.items():
        best: int | None = None
        for ep in eps:
            if ep not in g:
                continue
            for ct_node in ct & set(g.nodes):
                if nx.has_path(g, ep, ct_node):
                    length: int = nx.shortest_path_length(g, ep, ct_node)
                    if best is None or length < best:
                        best = length
        result[hpos] = best
    return result


def steiner_tree_comparison(
    state: GameState,
    team: int,
) -> tuple[int, int | None, float | None]:
    actual = sum(1 for e in team_entities(state, team) if e.kind in CONVEYOR_KINDS)

    harv_positions = [e.pos for e in team_entities(state, team, "harvester")]
    core_center = state.core_pos.get(team)
    if not core_center or not harv_positions:
        return actual, None, None

    ug: nx.Graph = nx.Graph()
    for y in range(state.height):
        for x in range(state.width):
            if state.tiles[y][x] == 1:
                continue
            for dx, dy in [(1, 0), (0, 1)]:
                nx2, ny = x + dx, y + dy
                if (
                    0 <= nx2 < state.width
                    and 0 <= ny < state.height
                    and state.tiles[ny][nx2] != 1
                ):
                    ug.add_edge((x, y), (nx2, ny), weight=1)

    terminals = [*harv_positions, core_center]
    try:
        st = nx.algorithms.approximation.steiner_tree(ug, terminals, weight="weight")
        steiner_size = st.number_of_edges()
    except (nx.NetworkXError, nx.NodeNotFound):
        return actual, None, None

    waste = actual / steiner_size if steiner_size > 0 else None
    return actual, steiner_size, waste


def network_diameter(state: GameState, team: int) -> int | None:
    g = build_conveyor_graph(state, team)
    ct = core_tiles(state.core_pos, team)
    reachable = reachable_from_core(g, ct)
    sub = g.subgraph(reachable)
    if len(sub) < 2:
        return None
    try:
        return nx.dag_longest_path_length(sub)
    except (nx.NetworkXError, nx.NetworkXUnfeasible):
        try:
            lengths = dict(nx.all_pairs_shortest_path_length(sub))
            return max(max(d.values()) for d in lengths.values())
        except Exception:  # noqa: BLE001
            return None


def dead_end_count(state: GameState, team: int) -> int:
    ct = core_tiles(state.core_pos, team)
    count = 0
    for e in team_entities(state, team):
        if e.kind not in CONVEYOR_KINDS:
            continue
        out = conveyor_output(e)
        if out is None:
            count += 1
            continue
        te = building_entity_at(state, out)
        if out not in ct and (
            te is None
            or te.team != team
            or (te.kind not in CONVEYOR_KINDS and te.kind != "core")
        ):
            count += 1
    return count


def shared_trunk_tiles(state: GameState, team: int) -> int:
    g = build_conveyor_graph(state, team)
    ct = core_tiles(state.core_pos, team)
    entries = harvester_entry_points(state, team)

    tile_use_count: dict[Pos, int] = {}
    for eps in entries.values():
        used: set[Pos] = set()
        for ep in eps:
            if ep not in g:
                continue
            for ct_node in ct & set(g.nodes):
                if nx.has_path(g, ep, ct_node):
                    path: list[Pos] = nx.shortest_path(g, ep, ct_node)
                    used |= set(path)
                    break
        for tile in used:
            tile_use_count[tile] = tile_use_count.get(tile, 0) + 1

    return sum(1 for count in tile_use_count.values() if count > 1)
