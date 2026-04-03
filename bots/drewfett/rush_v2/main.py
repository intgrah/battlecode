"""Entry point — dispatches to unit-specific logic."""

from __future__ import annotations

import sys
import traceback
from typing import TYPE_CHECKING

from cambc import Controller, EntityType, GameError

if TYPE_CHECKING:
    from unit import Unit


class Player:
    def __init__(self) -> None:
        self._unit: Unit | None = None

    def run(self, ct: Controller) -> None:
        if self._unit is None:
            match ct.get_entity_type():
                case EntityType.CORE:
                    from core import Core

                    self._unit = Core(ct)
                case EntityType.BUILDER_BOT:
                    from builder import Builder

                    self._unit = Builder(ct)
                case EntityType.GUNNER:
                    from gunner import Gunner

                    self._unit = Gunner(ct)
                case EntityType.SENTINEL:
                    from sentinel import Sentinel

                    self._unit = Sentinel(ct)
                case EntityType.LAUNCHER:
                    from launcher import Launcher

                    self._unit = Launcher(ct)
                case _:
                    return
        try:
            self._unit.run(ct)
        except GameError as e:
            print(traceback.format_exc())
            print(f"GAME_ERROR: {e}", file=sys.stderr)
        except Exception as e:
            print(traceback.format_exc())
            print(f"EXCEPTION: {e}", file=sys.stderr)
