"""Declarative state visualisation for the replay viewer.

Usage in builder code:

    from visualiser import Grid, Scalar, Tiles, emit

    # Show flow belief
    emit(
        flow_ti=Grid(state.flow.ti, palette="green"),
        flow_excess=Grid(state.flow.excess, palette="red_green"),
    )

    # Show explored vs unseen
    emit(
        seen=Grid([1 if e is not None else 0 for e in state.env], palette="grey"),
    )

    # Track a scalar in the sidebar
    emit(scale=Scalar(state.scale_percent))

    # Highlight specific tiles
    emit(goals=Tiles([(3, 5), (7, 2)]))

The replay viewer parses lines prefixed with ##VIS## from bot stdout.
Each call to emit() replaces the previous vis state for that bot on that turn.

Palettes:
    "viridis"   - perceptual sequential (blue-green-yellow)
    "green"     - transparent to green
    "red"       - transparent to red
    "blue"      - transparent to blue
    "grey"      - transparent to white
    "black"     - transparent to dark (fog of war)
    "red_green" - red (negative) to transparent (zero) to green (positive)

Null handling: values equal to `null` (default None) are rendered transparent.
    Common: null=None (python None), null=-1, null=0
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

VIS_PREFIX = "##VIS## "


@dataclass(frozen=True, slots=True)
class Grid:
    data: Sequence[float | int | bool | None]
    palette: str = "viridis"
    null: float | int | None = None


@dataclass(frozen=True, slots=True)
class Scalar:
    data: float | int | str


@dataclass(frozen=True, slots=True)
class Tiles:
    data: Iterable[tuple[int, int]]


def _serialize_field(v: Grid | Scalar | Tiles) -> dict:
    match v:
        case Grid(data=d, palette=p, null=n):
            return {"type": "grid", "data": d, "palette": p, "null": n}
        case Scalar(data=d):
            return {"type": "scalar", "data": d}
        case Tiles(data=d):
            return {"type": "tiles", "data": [list(t) for t in d]}


def emit(**fields: Grid | Scalar | Tiles) -> None:
    obj = {name: _serialize_field(v) for name, v in fields.items()}
    print(f"{VIS_PREFIX}{json.dumps(obj, separators=(',', ':'))}")
