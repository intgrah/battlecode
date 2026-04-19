from __future__ import annotations

import sys
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
from util.timer import Timer

if TYPE_CHECKING:
    from unit import Unit


class Player:
    def __init__(self) -> None:
        self.unit: Unit | None = None
        with Timer("init"):
            with Timer("builder"):
                self.builder = Builder()
            with Timer("core"):
                self.core = Core()
            with Timer("sentinel"):
                self.sentinel = Sentinel()
            with Timer("gunner"):
                self.gunner = Gunner()
            with Timer("launcher"):
                self.launcher = Launcher()
            with Timer("breach"):
                self.breach = Breach()

    def run(self, ct: Controller) -> None:
        if self.unit is None:
            match ct.get_entity_type():
                case EntityType.BUILDER_BOT:
                    self.unit = self.builder
                case EntityType.CORE:
                    self.unit = self.core
                case EntityType.SENTINEL:
                    self.unit = self.sentinel
                case EntityType.GUNNER:
                    self.unit = self.gunner
                case EntityType.LAUNCHER:
                    self.unit = self.launcher
                case EntityType.BREACH:
                    self.unit = self.breach
                case _:
                    raise ValueError
            with Timer("post_init"):
                self.unit.post_init(ct)
        try:
            with Timer("run"):
                self.unit.run(ct)
        except Exception:  # noqa: BLE001
            exc = traceback.format_exc()
            print(exc, file=sys.stdout)
            print(exc, file=sys.stderr)
            if DEBUG_RESIGN:
                ct.resign(str(exc))
