from __future__ import annotations

import sys
import time
import traceback
from typing import TYPE_CHECKING

from breach import Breach
from builder import Builder
from cambc import Controller, EntityType
from config import DEBUG_RESIGN
from core import Core
from gunner import Gunner
from launcher import Launcher
from sentinel import Sentinel

if TYPE_CHECKING:
    from unit import Unit


class Player:
    def __init__(self) -> None:
        self.unit: Unit | None = None

    def run(self, ct: Controller) -> None:
        if self.unit is None:
            t0 = time.perf_counter_ns()
            match ct.get_entity_type():
                case EntityType.BUILDER_BOT:
                    self.unit = Builder(ct)
                    t1 = time.perf_counter_ns()
                    print(f"init={t1 - t0}ns ({(t1 - t0) // 1000}us)")
                case EntityType.CORE:
                    self.unit = Core(ct)
                case EntityType.SENTINEL:
                    self.unit = Sentinel(ct)
                case EntityType.GUNNER:
                    self.unit = Gunner(ct)
                case EntityType.LAUNCHER:
                    self.unit = Launcher(ct)
                case EntityType.BREACH:
                    self.unit = Breach(ct)
                case _:
                    # No other entity types are controllable
                    raise ValueError
        try:
            self.unit.run(ct)
        except Exception as e:  # noqa: BLE001
            exc = traceback.format_exc()
            print(exc, file=sys.stdout)
            print(exc, file=sys.stderr)
            if DEBUG_RESIGN:
                # Do not print the full exception as this leaks code publicly
                ct.resign(str(e))
