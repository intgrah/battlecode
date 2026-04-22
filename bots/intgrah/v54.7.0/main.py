from __future__ import annotations

import sys
import traceback
from typing import TYPE_CHECKING, Final

from breach import Breach
from builder import Builder
from cambc import Controller, EntityType
from config import DEBUG_RESIGN
from core import Core
from gunner import Gunner
from launcher import Launcher
from sentinel import Sentinel
from util.debug import Scope

if TYPE_CHECKING:
    from unit import Unit

TIME_INIT: Final[bool] = False


class Player:
    def __init__(self) -> None:
        self.unit: Unit | None = None
        with Scope("init", time=TIME_INIT):
            with Scope("builder", time=TIME_INIT):
                self.builder = Builder()
            with Scope("core", time=TIME_INIT):
                self.core = Core()
            with Scope("sentinel", time=TIME_INIT):
                self.sentinel = Sentinel()
            with Scope("gunner", time=TIME_INIT):
                self.gunner = Gunner()
            with Scope("launcher", time=TIME_INIT):
                self.launcher = Launcher()
            with Scope("breach", time=TIME_INIT):
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
            with Scope("post_init", time=True):
                self.unit.post_init(ct)
        try:
            with Scope("run", time=True):
                self.unit.run(ct)
        except Exception:  # noqa: BLE001
            exc = traceback.format_exc()
            print(exc, file=sys.stdout)
            print(exc, file=sys.stderr)
            if DEBUG_RESIGN:
                ct.resign(str(exc))
