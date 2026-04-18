"""Cost estimation for a blueprint.

Scale contributions per entity type are **not** exposed in
`cambc.GameConstants`, so the percentages below are transcribed from
CLAUDE.md / the game spec. Base (unscaled) costs come from the actual
game constants.
"""

from __future__ import annotations

from cambc import GameConstants as _G

from blueprint import BlueprintEntry, Entity

__all__ = [
    "BASE_COST",
    "BUILDER_SCALE_PCT",
    "SCALE_PCT",
    "blueprint_cost_range",
    "cumulative_cost",
    "initial_scale",
]


BASE_COST: dict[Entity, tuple[int, int]] = {
    Entity.CONVEYOR: _G.CONVEYOR_BASE_COST,
    Entity.SPLITTER: _G.SPLITTER_BASE_COST,
    Entity.ARMOURED_CONVEYOR: _G.ARMOURED_CONVEYOR_BASE_COST,
    Entity.BRIDGE: _G.BRIDGE_BASE_COST,
    Entity.HARVESTER: _G.HARVESTER_BASE_COST,
    Entity.FOUNDRY: _G.FOUNDRY_BASE_COST,
    Entity.GUNNER: _G.GUNNER_BASE_COST,
    Entity.SENTINEL: _G.SENTINEL_BASE_COST,
    Entity.BREACH: _G.BREACH_BASE_COST,
    Entity.LAUNCHER: _G.LAUNCHER_BASE_COST,
    Entity.BARRIER: _G.BARRIER_BASE_COST,
    Entity.ROAD: _G.ROAD_BASE_COST,
}


# Scale contribution per entity (percentage points added to team scale
# after placement). Sourced from the game spec in CLAUDE.md; not in
# cambc.GameConstants.
SCALE_PCT: dict[Entity, float] = {
    Entity.ROAD: 0.5,
    Entity.CONVEYOR: 1.0,
    Entity.SPLITTER: 1.0,
    Entity.ARMOURED_CONVEYOR: 1.0,
    Entity.BARRIER: 1.0,
    Entity.HARVESTER: 5.0,
    Entity.BRIDGE: 10.0,
    Entity.GUNNER: 10.0,
    Entity.LAUNCHER: 10.0,
    Entity.BREACH: 10.0,
    Entity.SENTINEL: 20.0,
    Entity.FOUNDRY: 50.0,
}

BUILDER_SCALE_PCT: float = 20.0
"""Scale contribution of each builder bot already on the team."""


def initial_scale(n_builders: int) -> float:
    """Team scale (1.0 = base) accounting for an initial squad of `n_builders`."""
    return 1.0 + n_builders * BUILDER_SCALE_PCT / 100.0


def _scaled_cost(
    entry: BlueprintEntry,
    scale: float,
) -> tuple[int, int]:
    ti_base, ax_base = BASE_COST[entry.kind]
    return (int(scale * ti_base), int(scale * ax_base))


def cumulative_cost(
    entries: list[BlueprintEntry],
    n_builders: int,
) -> tuple[int, int]:
    """Total (Ti, Ax) cost of placing `entries` in the given order starting
    from a team that already has `n_builders` builder bots."""
    scale = initial_scale(n_builders)
    total_ti = 0
    total_ax = 0
    for entry in entries:
        ti, ax = _scaled_cost(entry, scale)
        total_ti += ti
        total_ax += ax
        scale += SCALE_PCT.get(entry.kind, 0.0) / 100.0
    return (total_ti, total_ax)


def final_scale(entries: list[BlueprintEntry], n_builders: int) -> float:
    """Team scale after the whole blueprint is placed."""
    return initial_scale(n_builders) + sum(
        SCALE_PCT.get(e.kind, 0.0) for e in entries
    ) / 100.0


def blueprint_cost_range(
    entries: list[BlueprintEntry],
    n_builders: int,
) -> tuple[tuple[int, int], tuple[int, int]]:
    """Return ((min_ti, min_ax), (max_ti, max_ax)) over two placement orders:
    ascending scale contribution (cheap first) and descending (expensive
    first). Gives the achievable range.
    """
    by_pct = sorted(entries, key=lambda e: SCALE_PCT.get(e.kind, 0.0))
    asc = cumulative_cost(by_pct, n_builders)
    desc = cumulative_cost(list(reversed(by_pct)), n_builders)
    return asc, desc
