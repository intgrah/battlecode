from __future__ import annotations

from dataclasses import dataclass

from blueprint import DIR_DELTA, BlueprintEntry, Entity

__all__ = ["Scored", "sequence", "unrouted"]


_CHAIN = frozenset(
    {
        Entity.CONVEYOR,
        Entity.SPLITTER,
        Entity.ARMOURED_CONVEYOR,
        Entity.BRIDGE,
    },
)

_SINK_KINDS: frozenset[Entity] = frozenset(
    {
        Entity.GUNNER,
        Entity.SENTINEL,
        Entity.BREACH,
        Entity.LAUNCHER,
        Entity.FOUNDRY,
    },
)


@dataclass(frozen=True, slots=True)
class Scored:
    entry: BlueprintEntry
    unrouted: bool


def _successors(entry: BlueprintEntry) -> list[tuple[int, int]]:
    """Positions this chain-kind entry sends resources toward.

    Only defined for chain kinds (conveyor / armoured / splitter / bridge).
    Harvesters and foundries are sources/sinks, not passthroughs — the
    chain-to-sink walk treats them as terminals and uses the direct
    cardinal-neighbour check below for source validation.
    """
    x, y = entry.pos
    match entry.kind:
        case Entity.CONVEYOR | Entity.ARMOURED_CONVEYOR:
            if entry.direction is None:
                return []
            dx, dy = DIR_DELTA[entry.direction]
            return [(x + dx, y + dy)]
        case Entity.SPLITTER:
            if entry.direction is None:
                return []
            bx, by = DIR_DELTA[entry.direction]
            opp = (-bx, -by)
            out: list[tuple[int, int]] = []
            for dx, dy in DIR_DELTA.values():
                if abs(dx) + abs(dy) != 1:
                    continue
                if (dx, dy) == opp:
                    continue
                out.append((x + dx, y + dy))
            return out
        case Entity.BRIDGE:
            if entry.bridge_target is None:
                return []
            return [entry.bridge_target]
        case _:
            return []


def _cardinal_neighbours(pos: tuple[int, int]) -> list[tuple[int, int]]:
    x, y = pos
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


def _core_tiles(core: tuple[int, int]) -> frozenset[tuple[int, int]]:
    cx, cy = core
    return frozenset((cx + dx, cy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1))


def unrouted(
    entries: dict[tuple[int, int], BlueprintEntry],
    core: tuple[int, int],
) -> set[tuple[int, int]]:
    """Set of positions whose successor chain reaches no valid sink.

    Valid sinks: the 3x3 core area, turret tiles (gunner / sentinel /
    launcher), and foundry tiles (foundries consume into their own ax
    processing pipeline, so a chain ending at a foundry is routed).
    """
    core_tiles = _core_tiles(core)
    sink_positions = {
        pos for pos, e in entries.items() if e.kind in _SINK_KINDS
    }
    sinks = core_tiles | sink_positions
    chain_positions = {pos for pos, e in entries.items() if e.kind in _CHAIN}
    reach_sink = set()
    for pos in chain_positions:
        seen: set[tuple[int, int]] = set()
        stack = [pos]
        hit = False
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            if cur in sinks:
                hit = True
                break
            entry = entries.get(cur)
            if entry is None:
                # Non-entry tile — chain terminates here without a sink.
                continue
            stack.extend(_successors(entry))
        if hit:
            reach_sink.add(pos)
    bad = chain_positions - reach_sink

    # Harvester must feed a routed chain via a cardinal neighbour.
    for pos, entry in entries.items():
        if entry.kind != Entity.HARVESTER:
            continue
        feeds_routed = any(
            n in reach_sink or n in sinks for n in _cardinal_neighbours(pos)
        )
        if not feeds_routed:
            bad.add(pos)
    return bad


def sequence(
    entries: dict[tuple[int, int], BlueprintEntry],
    core: tuple[int, int],
) -> list[Scored]:
    """Return entries in the user's placement order. Flags unrouted ones.

    Build order is the order the user placed things; the editor does not
    try to derive it from the conveyor graph.
    """
    bad = unrouted(entries, core)
    return [
        Scored(entry=entry, unrouted=pos in bad)
        for pos, entry in entries.items()
    ]
