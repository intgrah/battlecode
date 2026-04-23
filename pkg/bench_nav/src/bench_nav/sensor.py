from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from bench_nav.types import SensorReading

VISION_FULL: Final[int] = 1 << 30


@dataclass
class Sensor:
    """Ground-truth sensor that emits SensorReadings for the runner.

    Internally tracks which tile indices the algo has already been told about,
    so deltas are monotonic: each newly_visible index appears exactly once per
    run.
    """

    w: int
    h: int
    n: int
    cost: list[int]
    vision_r2: int
    seen: bytearray = field(default_factory=bytearray)

    def __post_init__(self) -> None:
        if len(self.seen) == 0:
            self.seen = bytearray(self.n)

    def reveal(self, center: int) -> SensorReading:
        if self.vision_r2 >= VISION_FULL:
            return self._reveal_all()
        return self._reveal_disk(center)

    def _reveal_all(self) -> SensorReading:
        new: list[int] = []
        costs: dict[int, int] = {}
        for i in range(self.n):
            if not self.seen[i]:
                self.seen[i] = 1
                new.append(i)
                costs[i] = self.cost[i]
        return SensorReading(newly_visible=tuple(new), cost=costs)

    def _reveal_disk(self, center: int) -> SensorReading:
        cx, cy = center % self.w, center // self.w
        r = int(self.vision_r2**0.5) + 1
        new: list[int] = []
        costs: dict[int, int] = {}
        for dy in range(-r, r + 1):
            ny = cy + dy
            if ny < 0 or ny >= self.h:
                continue
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy > self.vision_r2:
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
