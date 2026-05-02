"""
Bot-side debug helpers — structured per-turn JSON tree + cambc indicator
overlays.

Per-turn flow:
- The first `Scope` of the turn starts a fresh root node and stack.
- Nested `Scope`s become child nodes of the current top-of-stack scope.
- Bodies append `msg` and `vis` nodes via `debug()` and `vis()`.
- At end of turn, the bot calls `flush()` which prints the root tree as
  one line of JSON to stdout.

State lives in a `DebugCtx` struct with one process-global instance. Each
cdylib has its own copy of the static, and the engine serialises bot
calls per turn, so no locking is needed in practice — `unsafe` reads from
a `static mut` are fine on this single-threaded path.
"""
from __future__ import annotations

from typing import Final
import time
import json

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

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cambc import Controller, ControllerApi, Position
from config import DEBUG_LOG
from util.visualiser import Dumper
if TYPE_CHECKING:
    from util.visualiser import Dump, DumpBoolGrid, DumpU8Grid, DumpI16Grid, DumpU16Grid, DumpF32Grid, DumpTiles, DumpTile, DumpDot, DumpPath, DumpVectorField, DumpScalar
TYPE_KEY: Final[str] = "$type"
"""Discriminator key for typed JSON nodes (matches Python `_TYPE = "$type"`)."""

class Frame:
    """
    Per-frame entry: the index of this scope's child slot inside its parent's
    `children` array, plus (for timed scopes) the start nanosecond timestamp.
    The frame at index 0 has `parent_child_idx = None` because it is the root.
    """
    parent_child_idx: int | None
    t0_ns: int | None

    def __init__(self, parent_child_idx: int | None, t0_ns: int | None):
        self.parent_child_idx = parent_child_idx
        self.t0_ns = t0_ns

class DebugCtx:
    """
    Process-global debug state. The `Dumper`'s same_cache is keyed by
    `(current_bot_id, name)` so multiple builders running through the
    same static still get per-bot same-elision.
    """
    root: Value | None
    frames: list[Frame]
    dumper: Dumper
    last_flush_us: int
    current_bot_id: int

    def __init__(self):
        self.root = None
        self.frames = []
        self.dumper = Dumper()
        self.last_flush_us = 0
        self.current_bot_id = -1

    def current_scope_mut(self):
        """
        Walk into the current scope node (the deepest open scope), using
        the parent-child indices recorded in `frames`.
        """
        root = self.root
        node: Value = root
        for f in self.frames[1:]:
            idx = f.parent_child_idx
            node = node["children"][idx]
        return node

    def push_scope(self, label, timed):
        node = {"$type": "scope", "name": str(label), "children": []}
        t0_ns = time.perf_counter_ns() if timed else None
        if (self.root is None):
            self.root = node
            self.frames.append(Frame(parent_child_idx=None, t0_ns=t0_ns))
            return
        parent = self.current_scope_mut()
        children = parent["children"]
        idx = len(children)
        children.append(node)
        self.frames.append(Frame(parent_child_idx=idx, t0_ns=t0_ns))

    def pop_scope(self):
        frame = (self.frames.pop() if self.frames else None)
        t0_ns = frame.t0_ns
        if t0_ns is not None:
            us = (time.perf_counter_ns() - t0_ns) // 1000
            if (not self.frames):
                root = self.root
                root["us"] = us
            else:
                idx = frame.parent_child_idx
                parent = self.current_scope_mut()
                parent["children"][idx]["us"] = us
        if (not self.frames):
            self.root = None

    def emit_child(self, node):
        if (not self.frames):
            return
        parent = self.current_scope_mut()
        parent["children"].append(node)

    def debug(self, tmpl, args):
        node = {"$type": "msg", "tmpl": str(tmpl), "args": args}
        self.emit_child(node)

    def vis(self, name, value):
        if (not self.frames):
            return
        root = self.root
        node: Value = root
        for f in self.frames[1:]:
            idx = f.parent_child_idx
            node = node["children"][idx]
        children = node["children"]
        self.dumper.dump(children, self.current_bot_id, name, value)

    def flush(self):
        prev_us = self.last_flush_us
        root = self.root
        root["prev_flush_us"] = prev_us
        t0_ns = time.perf_counter_ns()
        payload = json.dumps(root)
        print(f"{payload}")
        self.last_flush_us = (time.perf_counter_ns() - t0_ns) // 1000

    @staticmethod
    def default():
        return DebugCtx()
CTX: DebugCtx | None = None
"""
Process-global debug context. The `Dumper` inside same-elides per
`(bot_id, name)`, so multiple builders sharing the static still get
per-builder same_cache isolation. `current_bot_id` is set at the top
of `Player::run` via `set_current_bot` and used by `Dumper.dump`.
"""

def ctx():
    global CTX
    if (CTX is None):
        CTX = DebugCtx()
    return CTX

def set_current_bot(id):
    """
    Set the bot id used as the same-elision cache key for subsequent
    `vis()` calls. Call at the top of each `run()` before any scope opens.
    """
    if not DEBUG_LOG:
        return
    ctx().current_bot_id = id

class Scope:

    def __init__(self, label=None):
        self.label = str(label) if label is not None else ""
        if DEBUG_LOG:
            ctx().push_scope(self.label, False)

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        if DEBUG_LOG:
            ctx().pop_scope()

    @staticmethod
    def new(label):
        """Push an untimed scope onto the stack. The returned guard pops on drop."""
        ctx().push_scope(label, False)
        __self = Scope.__new__(Scope)
        __self.label = str(label)
        return __self
    @staticmethod
    def new_timed(label):
        """
        Push a timed scope; on drop, records `us` (microseconds elapsed).
        Mirrors Python `Scope(label, time=True)`.
        """
        ctx().push_scope(label, True)
        __self = Scope.__new__(Scope)
        __self.label = str(label)
        return __self
    def drop(self):
        ctx().pop_scope()

def debug(tmpl, args):
    """
    Append a `msg` node under the current scope. `tmpl` is a Python-style
    format-string fragment using `{name}` slots; `args` provide the values
    referenced by those slots.
    """
    if not DEBUG_LOG:
        return
    ctx().debug(tmpl, args)

def vis(name, value):
    """
    Append a vis node under the current scope, routed through the per-unit
    `Dumper` for same-elision.
    """
    if not DEBUG_LOG:
        return
    ctx().vis(name, value)

def flush():
    """
    Print the root scope as one JSON line to stdout. MUST be called from
    inside the top-level `Scope::new("turn")` block, before that block's
    guard drops.
    """
    if not DEBUG_LOG:
        return
    ctx().flush()

def dot(ct, pos, r, g, b):
    """
    Wrapper over `Controller::draw_indicator_dot`. Engine-side overlay,
    visible to all spectators, on/off globally per replay.
    """
    if not DEBUG_LOG:
        return
    ct.draw_indicator_dot(pos, r, g, b)

def line(ct, pos_a, pos_b, r, g, b):
    """Wrapper over `Controller::draw_indicator_line`."""
    if not DEBUG_LOG:
        return
    ct.draw_indicator_line(pos_a, pos_b, r, g, b)
