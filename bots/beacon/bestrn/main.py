"""
Cambridge Battlecode bot — Rust translation of `bots/intgrah/v54.7.9`.

`Player` is the entry point that the engine instantiates once and calls
`run(ct)` on each turn the unit is alive. `cambc_bot!(Player)` exports the
FFI symbols the engine looks for.
"""

from __future__ import annotations

from breach import Breach
from builder import Builder
from cambc import EntityType
from core import Core
from gunner import Gunner
from launcher import Launcher
from sentinel import Sentinel
from util.debug import Scope, flush


class Player:
    """
    The bot. The engine constructs one `Player` per unit (the FFI entry
    point) and calls `Bot::run` each turn. `unit` caches which of the six
    concrete subtypes this instance resolved to so subsequent turns skip
    the dispatch + `post_init`.
    """

    unit: EntityType | None
    builder: Builder
    core: Core
    sentinel: Sentinel
    gunner: Gunner
    launcher: Launcher
    breach: Breach

    def __init__(self) -> None:
        self.unit = None
        self.builder = Builder()
        self.core = Core()
        self.sentinel = Sentinel()
        self.gunner = Gunner()
        self.launcher = Launcher()
        self.breach = Breach()

    def run(self, ct) -> None:
        with Scope("turn") as _turn:
            if self.unit is None:
                kind = ct.get_entity_type(None)
                self.unit = kind
                with Scope.new_timed("post_init") as _scope:
                    match kind:
                        case EntityType.BUILDER_BOT:
                            self.builder.post_init(ct)
                        case EntityType.CORE:
                            self.core.post_init(ct)
                        case EntityType.SENTINEL:
                            self.sentinel.post_init(ct)
                        case EntityType.GUNNER:
                            self.gunner.post_init(ct)
                        case EntityType.LAUNCHER:
                            self.launcher.post_init(ct)
                        case EntityType.BREACH:
                            self.breach.post_init(ct)
                        case et:
                            (_ for _ in ()).throw(
                                Exception(
                                    f"Player::run on unsupported entity type: {et!r}"
                                )
                            )
            with Scope.new_timed("run") as _scope:
                match self.unit:
                    case EntityType.BUILDER_BOT:
                        self.builder.run(ct)
                    case EntityType.CORE:
                        self.core.run(ct)
                    case EntityType.SENTINEL:
                        self.sentinel.run(ct)
                    case EntityType.GUNNER:
                        self.gunner.run(ct)
                    case EntityType.LAUNCHER:
                        self.launcher.run(ct)
                    case EntityType.BREACH:
                        self.breach.run(ct)
                    case _:
                        pass
            flush()
