from __future__ import annotations

from dataclasses import dataclass, field

from bench_nav.common import BUILDER_VISION_R2
from bench_nav.types import SensorReading


@dataclass
class Sensor:
    """Ground-truth sensor emitting SensorReadings for online algos.

    Vision radius is the builder's constant (BUILDER_VISION_R2). Internally
    tracks which tile indices the algo has already been told about so deltas
    are monotonic: each newly_visible index appears exactly once per run.
    """

    w: int
    h: int
    n: int
    cost: list[int]
    seen: bytearray = field(default_factory=bytearray)

    def __post_init__(self) -> None:
        if len(self.seen) == 0:
            self.seen = bytearray(self.n)

    def reveal(self, center: int) -> SensorReading:
        cx, cy = center % self.w, center // self.w
        r = int(BUILDER_VISION_R2**0.5) + 1
        new: list[int] = []
        costs: dict[int, int] = {}
        for dy in range(-r, r + 1):
            ny = cy + dy
            if ny < 0 or ny >= self.h:
                continue
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy > BUILDER_VISION_R2:
                    continue
                nx = cx + dx
                if nx < 0 or nx >= self.w:
                    continue
                i = ny * self.w + nx
                if not self.seen[i]:
                    self.seen[i] = 1
                    new.append(i)
                    costs[i] = self.cost[i]
        return SensorReading(newly_visible=tuple(new), cost=costs)
