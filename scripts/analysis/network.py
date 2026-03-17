from collections import deque

import networkx as nx

from .snapshot import CONVEYOR_KINDS, GameState


def build_conveyor_graph(state: GameState, team: int) -> nx.DiGraph:
    G = nx.DiGraph()
    core_tiles = state.core_tiles(team)

    for e in state.team_entities(team):
        if e.kind not in CONVEYOR_KINDS:
            continue
        out = state.conveyor_output(e)
        if out is None:
            continue
        G.add_node(e.pos, kind=e.kind, hp=e.hp)
        te = state.building_entity_at(out)
        if te and te.team == team and (te.kind in CONVEYOR_KINDS or te.kind == "core"):
            G.add_edge(e.pos, out)
        elif out in core_tiles:
            G.add_edge(e.pos, out)

    for ct in core_tiles:
        if ct in G:
            G.nodes[ct]["is_core"] = True

    return G


def find_core_sinks(state: GameState, team: int) -> set[tuple[int, int]]:
    return state.core_tiles(team)


def harvester_positions(state: GameState, team: int) -> list[tuple[int, int]]:
    return [e.pos for e in state.team_entities(team, "harvester")]


def harvester_entry_points(state: GameState, team: int) -> dict[tuple[int, int], list[tuple[int, int]]]:
    result = {}
    for hpos in harvester_positions(state, team):
        entries = []
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if dx == 0 and dy == 0:
                    continue
                adj = (hpos[0] + dx, hpos[1] + dy)
                e = state.building_entity_at(adj)
                if e and e.team == team and e.kind in CONVEYOR_KINDS:
                        entries.append(adj)
        result[hpos] = entries
    return result


def reachability_to_core(G: nx.DiGraph, core_tiles: set[tuple[int, int]]) -> set[tuple[int, int]]:
    sinks = core_tiles & set(G.nodes)
    reachable = set()
    R = G.reverse()
    for s in sinks:
        reachable |= nx.ancestors(R, s)
        reachable.add(s)
    return reachable


def connected_harvesters(state: GameState, team: int) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    G = build_conveyor_graph(state, team)
    core_tiles = find_core_sinks(state, team)
    reachable = reachability_to_core(G, core_tiles)
    entries = harvester_entry_points(state, team)

    connected = []
    disconnected = []
    for hpos, entry_nodes in entries.items():
        if any(ep in reachable for ep in entry_nodes):
            connected.append(hpos)
        else:
            disconnected.append(hpos)
    return connected, disconnected


def dead_conveyors(state: GameState, team: int) -> list[tuple[int, int]]:
    G = build_conveyor_graph(state, team)
    core_tiles = find_core_sinks(state, team)
    reachable = reachability_to_core(G, core_tiles)
    entries = harvester_entry_points(state, team)
    harvester_adj = set()
    for eps in entries.values():
        harvester_adj.update(eps)

    useful = set()
    for src in harvester_adj & reachable:
        for sink in core_tiles & set(G.nodes):
            if nx.has_path(G, src, sink):
                useful |= set(nx.shortest_path(G, src, sink))

    all_conv = {e.pos for e in state.team_entities(team) if e.kind in CONVEYOR_KINDS}
    return sorted(all_conv - useful)


def betweenness_centrality(state: GameState, team: int) -> dict[tuple[int, int], float]:
    G = build_conveyor_graph(state, team)
    if len(G) < 2:
        return {}

    core_tiles = find_core_sinks(state, team)
    entries = harvester_entry_points(state, team)
    sources = set()
    for eps in entries.values():
        sources |= set(eps) & set(G.nodes)
    sinks = core_tiles & set(G.nodes)

    if not sources or not sinks:
        return {}

    bc: dict[tuple[int, int], float] = {n: 0.0 for n in G.nodes}
    for src in sources:
        for sink in sinks:
            if nx.has_path(G, src, sink):
                path = nx.shortest_path(G, src, sink)
                for node in path[1:-1]:
                    bc[node] += 1.0

    total = len(sources) * len(sinks)
    if total > 0:
        bc = {k: v / total for k, v in bc.items()}
    return bc


def max_flow_capacity(state: GameState, team: int) -> dict:
    G = build_conveyor_graph(state, team)
    core_tiles = find_core_sinks(state, team)
    entries = harvester_entry_points(state, team)

    FG = nx.DiGraph()
    for u, v in G.edges():
        FG.add_edge(u, v, capacity=1.0)

    super_source = (-1, -1)
    super_sink = (-2, -2)
    for hpos, eps in entries.items():
        for ep in eps:
            if ep in G:
                FG.add_edge(super_source, ep, capacity=0.25)

    for ct in core_tiles & set(G.nodes):
        FG.add_edge(ct, super_sink, capacity=float("inf"))

    if super_source not in FG or super_sink not in FG:
        return {"max_flow": 0.0, "theoretical_max": 0.0, "utilization": 0.0}

    try:
        flow_value, flow_dict = nx.maximum_flow(FG, super_source, super_sink)
    except nx.NetworkXError:
        flow_value = 0.0
        flow_dict = {}

    n_harvesters = len(entries)
    theoretical = n_harvesters * 0.25

    return {
        "max_flow": flow_value,
        "theoretical_max": theoretical,
        "utilization": flow_value / theoretical if theoretical > 0 else 0.0,
        "flow_dict": flow_dict,
    }


def articulation_points(state: GameState, team: int) -> list[tuple[tuple[int, int], int]]:
    G = build_conveyor_graph(state, team)
    core_tiles = find_core_sinks(state, team)
    entries = harvester_entry_points(state, team)
    reachable = reachability_to_core(G, core_tiles)

    sources = set()
    harv_to_entries = {}
    for hpos, eps in entries.items():
        connected_eps = [ep for ep in eps if ep in reachable]
        if connected_eps:
            sources.update(connected_eps)
            harv_to_entries[hpos] = connected_eps

    results = []
    for node in set(G.nodes) - core_tiles:
        if node not in reachable:
            continue
        G_minus = G.copy()
        G_minus.remove_node(node)
        new_reachable = reachability_to_core(G_minus, core_tiles)

        impact = 0
        for hpos, eps in harv_to_entries.items():
            was_connected = any(ep in reachable for ep in eps)
            now_connected = any(ep in new_reachable for ep in eps if ep != node)
            if was_connected and not now_connected:
                impact += 1

        if impact > 0:
            results.append((node, impact))

    return sorted(results, key=lambda x: -x[1])


def shortest_path_lengths(state: GameState, team: int) -> dict[tuple[int, int], int | None]:
    G = build_conveyor_graph(state, team)
    core_tiles = find_core_sinks(state, team)
    entries = harvester_entry_points(state, team)

    result = {}
    for hpos, eps in entries.items():
        best = None
        for ep in eps:
            if ep not in G:
                continue
            for ct in core_tiles & set(G.nodes):
                if nx.has_path(G, ep, ct):
                    length = nx.shortest_path_length(G, ep, ct)
                    if best is None or length < best:
                        best = length
        result[hpos] = best
    return result


def steiner_tree_comparison(state: GameState, team: int) -> dict:
    G = build_conveyor_graph(state, team)
    core_tiles = find_core_sinks(state, team)
    entries = harvester_entry_points(state, team)

    actual_conveyors = sum(1 for e in state.team_entities(team) if e.kind in CONVEYOR_KINDS)

    reachable = reachability_to_core(G, core_tiles)
    used_on_paths = set()
    for hpos, eps in entries.items():
        for ep in eps:
            if ep not in G or ep not in reachable:
                continue
            for ct in core_tiles & set(G.nodes):
                if nx.has_path(G, ep, ct):
                    path = nx.shortest_path(G, ep, ct)
                    used_on_paths.update(path)
                    break

    UG = nx.Graph()
    for y in range(state.height):
        for x in range(state.width):
            if state.tiles[y][x] == 1:
                continue
            for dx, dy in [(1, 0), (0, 1)]:
                nx2, ny = x + dx, y + dy
                if 0 <= nx2 < state.width and 0 <= ny < state.height and state.tiles[ny][nx2] != 1:
                    UG.add_edge((x, y), (nx2, ny), weight=1)

    harvs = [h for h in harvester_positions(state, team)]
    core_center = state.core_pos.get(team)
    if not core_center or not harvs:
        return {"actual": actual_conveyors, "on_shortest_paths": len(used_on_paths),
                "steiner_approx": None, "waste_ratio": None}

    terminals = harvs + [core_center]
    try:
        st = nx.algorithms.approximation.steiner_tree(UG, terminals, weight="weight")
        steiner_size = st.number_of_edges()
    except (nx.NetworkXError, nx.NodeNotFound):
        steiner_size = None

    waste = None
    if steiner_size is not None and steiner_size > 0:
        waste = actual_conveyors / steiner_size

    return {
        "actual": actual_conveyors,
        "on_shortest_paths": len(used_on_paths),
        "steiner_approx": steiner_size,
        "waste_ratio": waste,
    }


def network_diameter(state: GameState, team: int) -> int | None:
    G = build_conveyor_graph(state, team)
    core_tiles = find_core_sinks(state, team)
    reachable = reachability_to_core(G, core_tiles)
    sub = G.subgraph(reachable)
    if len(sub) < 2:
        return None
    try:
        return nx.dag_longest_path_length(sub)
    except (nx.NetworkXError, nx.NetworkXUnfeasible):
        try:
            lengths = dict(nx.all_pairs_shortest_path_length(sub))
            return max(max(d.values()) for d in lengths.values())
        except Exception:
            return None


def analyze_network(state: GameState, team: int) -> dict:
    conn, disconn = connected_harvesters(state, team)
    dead = dead_conveyors(state, team)
    bc = betweenness_centrality(state, team)
    mf = max_flow_capacity(state, team)
    ap = articulation_points(state, team)
    sp = shortest_path_lengths(state, team)
    steiner = steiner_tree_comparison(state, team)
    diam = network_diameter(state, team)

    top_bc = sorted(bc.items(), key=lambda x: -x[1])[:5]
    total_conv = sum(1 for e in state.team_entities(team) if e.kind in CONVEYOR_KINDS)

    return {
        "harvesters_connected": len(conn),
        "harvesters_disconnected": len(disconn),
        "disconnected_positions": disconn,
        "total_conveyors": total_conv,
        "dead_conveyors": len(dead),
        "dead_positions": dead[:10],
        "betweenness_top5": top_bc,
        "max_flow": mf["max_flow"],
        "theoretical_max_flow": mf["theoretical_max"],
        "flow_utilization": mf["utilization"],
        "single_points_of_failure": ap[:5],
        "path_lengths": sp,
        "steiner_actual": steiner["actual"],
        "steiner_approx": steiner["steiner_approx"],
        "steiner_waste_ratio": steiner["waste_ratio"],
        "diameter": diam,
    }
