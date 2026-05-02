"""
Cambridge Battlecode bot — Rust translation of `bots/intgrah/v54.7.9`.

`Player` is the entry point that the engine instantiates once and calls
`run(ct)` on each turn the unit is alive. `cambc_bot!(Player)` exports the
FFI symbols the engine looks for.
"""
from __future__ import annotations

def _pyrust_install_aliases() -> None:
    try:
        import cambc as _c
    except ImportError:
        return
    for _name in ("Team", "ResourceType", "EntityType", "Environment", "Direction"):
        _cls = getattr(_c, _name, None)
        if _cls is None:
            continue
        for _m in list(_cls):
            _p = "".join(_s.capitalize() for _s in _m.name.split("_"))
            if not hasattr(_cls, _p):
                setattr(_cls, _p, _m)
    # Hot-path: cache (dx, dy) per Direction so `pos.add(d)` skips the
    # 9-entry dict construction in `Direction.delta`. ~3.3x speedup.
    _Pos = getattr(_c, "Position", None)
    _Dir = getattr(_c, "Direction", None)
    if _Pos is not None and _Dir is not None:
        _DELTA = {_d: _d.delta() for _d in _Dir}
        def _fast_add(self, d, _DELTA=_DELTA, _Pos=_Pos):
            _dx, _dy = _DELTA[d]
            return _Pos(self.x + _dx, self.y + _dy)
        _Pos.add = _fast_add
        def _fast_delta(self, _DELTA=_DELTA):
            return _DELTA[self]
        _Dir.delta = _fast_delta
    # Hot-path: pre-build all 5000 Position objects so `pos_of(p)`
    # is a tuple __getitem__ instead of a fresh `Position(x, y)` call.
    if _Pos is not None:
        _POS_TABLE = tuple(_Pos(x=_i % 100, y=_i // 100) for _i in range(5000))
        _Pos.lookup = _POS_TABLE.__getitem__
    # Hot-path: precomputed PosInt distance tables. Indexed by
    # `p - q + DIST_OFFSET` where DIST_OFFSET=4949, length 9899.
    if _Pos is not None:
        _STRIDE = 100
        _DIST_OFFSET = 4949
        _DIST_LEN = 9899
        _MAX_D = 49
        _ds = [0] * _DIST_LEN
        _mh = [0] * _DIST_LEN
        _ch = [0] * _DIST_LEN
        for _dy in range(-_MAX_D, _MAX_D + 1):
            for _dx in range(-_MAX_D, _MAX_D + 1):
                _i = _dy * _STRIDE + _dx + _DIST_OFFSET
                _adx = _dx if _dx >= 0 else -_dx
                _ady = _dy if _dy >= 0 else -_dy
                _ds[_i] = _dx * _dx + _dy * _dy
                _mh[_i] = _adx + _ady
                _ch[_i] = _adx if _adx > _ady else _ady
        _Pos.dist_sq_table = tuple(_ds).__getitem__
        _Pos.manhat_table = tuple(_mh).__getitem__
        _Pos.chebyshev_table = tuple(_ch).__getitem__
_pyrust_install_aliases()
del _pyrust_install_aliases

from cambc import EntityType
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cambc import Controller, ControllerApi
from breach import Breach
from builder import Builder
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

    def __init__(self):
        self.unit = None
        self.builder = Builder()
        self.core = Core()
        self.sentinel = Sentinel()
        self.gunner = Gunner()
        self.launcher = Launcher()
        self.breach = Breach()

    def run(self, ct):
        with Scope("turn") as _turn:
            if (self.unit is None):
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
                            (_ for _ in ()).throw(Exception(f"Player::run on unsupported entity type: {et!r}"))
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
