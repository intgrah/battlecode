"""
Translation of `bots/intgrah/v54.7.9/builder/algorithms/bug2_planner.py`.

Bug2 plan generator that mutates a `path_idx` list in place.

Drains under a budget per turn — yields after each walker step, after
each m-line cell, and after each chosen-path cell. Caller drives the
generator and resumes next turn from where it left off.

Outcome signalling: `step()` returns `Some(true)` on success (path reached
the goal), `Some(false)` if proven unreachable, and `None` while more steps
are needed. The "yielded value" is exposed as `last_yielded` (-1 for a
walker-step heartbeat, otherwise the flat cell index `y * MAX_WIDTH + x`).

Cost model:
- `cost[i] == INF`        : impassable (wall, enemy building, harvester, ore)
- `cost[i] != INF`        : passable (treat as 1 for walkable, 3 for buildable
                            in the user's choice of cost grid; the planner
                            itself only checks `== INF`).
- `path_idx[i]`           : -1 if not on plan, else the index along the path
                            (monotone non-decreasing along the planned route).
                            Caller must initialize with -1s and write
                            `path_idx[start] = 0`.

`stride` is the row stride for cell indices: `cell = y * stride + x`.
For the bot we pass `MAX_WIDTH`. `n_pad` is `stride * stride` (the size
of the flat arrays). `w`, `h` are the actual map dimensions.
"""
from __future__ import annotations

from typing import Final
from dataclasses import dataclass

from util.constants import INF, MAX_WIDTH
DX: Final[list[int]] = [0, 1, 1, 1, 0, -1, -1, -1]
DY: Final[list[int]] = [-1, -1, 0, 1, 1, 1, 0, -1]
IS_CARDINAL: Final[list[bool]] = [True, False, True, False, True, False, True, False]

def build_mline_seq(sx, sy, gx, gy):
    """Build the Bresenham m-line sequence from `(sx, sy)` to `(gx, gy)`."""
    out: list[tuple[int, int]] = []
    dx = abs(gx - sx)
    dy = abs(gy - sy)
    sxi = 1 if sx < gx else -1
    syi = 1 if sy < gy else -1
    err = dx - dy
    cx = sx
    cy = sy
    while True:
        out.append((cx, cy))
        if cx == gx and cy == gy:
            return out
        e2 = err << 1
        if e2 > -dy:
            err -= dy
            cx += sxi
        if e2 < dx:
            err += dx
            cy += syi
    return

"""Outcome of a single `step()` call."""
@dataclass(frozen=True, slots=True)
class StateAdvanceMLine:
    """Main outer loop entry: try to advance along the m-line."""
    pass

@dataclass(frozen=True, slots=True)
class StateWalkerRace:
    """Walker race: alternately step CW and CCW walkers."""
    pass

@dataclass(frozen=True, slots=True)
class StateEmitChosen:
    """Emit each cell of the chosen path one at a time."""
    idx: int

@dataclass(frozen=True, slots=True)
class StateEmitWinner:
    """Emit the winning cell."""
    pass

@dataclass(frozen=True, slots=True)
class StateAdvanceAfterWinner:
    """After winner emission, advance `m_i` past covered cells."""
    pass

@dataclass(frozen=True, slots=True)
class StateDone:
    """Done — return value is in `done_value`."""
    pass

type State = StateAdvanceMLine | StateWalkerRace | StateEmitChosen | StateEmitWinner | StateAdvanceAfterWinner | StateDone

class Bug2Planner:
    """
    Bug2 planner state machine. One step ≈ one Python `yield`.

    `cost` is supplied as a borrow on every `step()` call, mirroring the
    Python generator that closes over the caller's mutable `cost_grid` list.
    """
    w: int
    h: int
    gi: int
    _path_idx: list[int]
    stride: int
    n_pad: int
    sx: int
    sy: int
    gx: int
    gy: int
    mdx: int
    mdy: int
    goal_dot: int
    mline_seq: list[tuple[int, int]]
    pos: int
    path_len: int
    m_i: int
    hit_d: int
    cw_faces: list[int]
    ccw_faces: list[int]
    cw_px: int
    cw_py: int
    cw_dir: int
    cw_path: list[int]
    cw_alive: bool
    cw_cross: int
    cw_wox: int
    cw_woy: int
    ccw_px: int
    ccw_py: int
    ccw_dir: int
    ccw_path: list[int]
    ccw_alive: bool
    ccw_cross: int
    ccw_wox: int
    ccw_woy: int
    winner: int
    win_x: int
    win_y: int
    met: bool
    walker_phase: int
    state: State
    last_yielded: int
    done_value: bool

    def __init__(self, cost, w, h, si, gi, path_idx):
        """Construct a new planner. Equivalent to entering the Python generator."""
        stride = int(50)
        n_pad = stride * stride
        sx = si % stride
        sy = si // stride
        gx = gi % stride
        gy = gi // stride
        mdx = gx - sx
        mdy = gy - sy
        goal_dot = mdx * mdx + mdy * mdy
        mline_seq = build_mline_seq(sx, sy, gx, gy)
        goal_blocked = cost[int(gi)] == 1000000
        initial_state = StateDone() if goal_blocked else StateAdvanceMLine()
        self.w = w
        self.h = h
        self.gi = gi
        self._path_idx = path_idx
        self.stride = stride
        self.n_pad = n_pad
        self.sx = sx
        self.sy = sy
        self.gx = gx
        self.gy = gy
        self.mdx = mdx
        self.mdy = mdy
        self.goal_dot = goal_dot
        self.mline_seq = mline_seq
        self.pos = si
        self.path_len = 1
        self.m_i = 0
        self.hit_d = 0
        self.cw_faces = []
        self.ccw_faces = []
        self.cw_px = 0
        self.cw_py = 0
        self.cw_dir = 0
        self.cw_path = []
        self.cw_alive = False
        self.cw_cross = 0
        self.cw_wox = 0
        self.cw_woy = 0
        self.ccw_px = 0
        self.ccw_py = 0
        self.ccw_dir = 0
        self.ccw_path = []
        self.ccw_alive = False
        self.ccw_cross = 0
        self.ccw_wox = 0
        self.ccw_woy = 0
        self.winner = -1
        self.win_x = -1
        self.win_y = -1
        self.met = False
        self.walker_phase = 0
        self.state = initial_state
        self.last_yielded = -1
        self.done_value = not goal_blocked

    def path_idx(self):
        """Read-only borrow of the in-progress `path_idx` array."""
        return self._path_idx

    def into_path_idx(self):
        """Take ownership of `path_idx`."""
        return self._path_idx

    def step(self, cost):
        """
        Advance one yield-equivalent. Returns `Some(true)` if reached goal,
        `Some(false)` if proven unreachable, `None` if more steps needed.

        `cost` is the per-tile cost grid; the caller may mutate it between
        `step()` calls and the next call sees the latest values (mirrors the
        Python generator's closure over the caller's mutable list).
        """
        while True:
            match self.state:
                case StateDone():
                    return self.done_value
                case StateAdvanceMLine():
                    if self.pos == self.gi:
                        self.state = StateDone()
                        self.done_value = True
                        return True
                    if self.m_i + 1 >= len(self.mline_seq):
                        self.state = StateDone()
                        self.done_value = False
                        return False
                    px = self.pos % self.stride
                    py = self.pos // self.stride
                    nx, ny = self.mline_seq[self.m_i + 1]
                    nb = ny * self.stride + nx
                    if cost[int(nb)] != 1000000:
                        self.pos = nb
                        self._path_idx[int(nb)] = self.path_len
                        self.path_len += 1
                        self.m_i += 1
                        self.last_yielded = nb
                        return None
                    ddx = px - self.gx
                    ddy = py - self.gy
                    self.hit_d = ddx * ddx + ddy * ddy
                    bdx = nx - px
                    bdy = ny - py
                    init_dir = (0 if bdy < 0 else 4) if bdx == 0 else ((1 if bdy < 0 else (2 if bdy == 0 else 3)) if bdx > 0 else (7 if bdy < 0 else (6 if bdy == 0 else 5)))
                    self.cw_faces = [0] * int(self.n_pad) * 4
                    self.ccw_faces = [0] * int(self.n_pad) * 4
                    self.cw_px = px
                    self.cw_py = py
                    self.cw_dir = init_dir
                    self.cw_path.clear()
                    self.cw_alive = True
                    self.cw_cross = (py - self.sy) * self.mdx - (px - self.sx) * self.mdy
                    self.cw_wox = px + DX[int(init_dir)]
                    self.cw_woy = py + DY[int(init_dir)]
                    self.ccw_px = px
                    self.ccw_py = py
                    self.ccw_dir = init_dir
                    self.ccw_path.clear()
                    self.ccw_alive = True
                    self.ccw_cross = self.cw_cross
                    self.ccw_wox = self.cw_wox
                    self.ccw_woy = self.cw_woy
                    self.winner = -1
                    self.win_x = -1
                    self.win_y = -1
                    self.met = False
                    self.walker_phase = 0
                    self.state = StateWalkerRace()
                case StateWalkerRace():
                    if not self.cw_alive and not self.ccw_alive:
                        if self.winner < 0:
                            self.state = StateDone()
                            self.done_value = False
                            return False
                        self.state = StateEmitChosen(idx=0)
                        continue
                    if self.walker_phase == 0:
                        if self.cw_alive:
                            self.cw_substep(cost)
                            self.walker_phase = 1
                            if self.winner >= 0 or self.met:
                                if self.winner < 0:
                                    self.state = StateDone()
                                    self.done_value = False
                                    return False
                                self.state = StateEmitChosen(idx=0)
                                continue
                            self.last_yielded = -1
                            return None
                        self.walker_phase = 1
                        continue
                    if self.ccw_alive:
                        self.ccw_substep(cost)
                        self.walker_phase = 0
                        if self.winner >= 0 or self.met:
                            if self.winner < 0:
                                self.state = StateDone()
                                self.done_value = False
                                return False
                            self.state = StateEmitChosen(idx=0)
                            continue
                        self.last_yielded = -1
                        return None
                    self.walker_phase = 0
                case StateEmitChosen(idx=idx):
                    chosen_path = self.cw_path if self.winner == 0 else self.ccw_path
                    if idx < len(chosen_path):
                        c = chosen_path[idx]
                        self._path_idx[int(c)] = self.path_len
                        self.path_len += 1
                        self.last_yielded = c
                        self.state = StateEmitChosen(idx=idx + 1)
                        return None
                    self.state = StateEmitWinner()
                case StateEmitWinner():
                    self.pos = self.win_y * self.stride + self.win_x
                    self._path_idx[int(self.pos)] = self.path_len
                    self.path_len += 1
                    self.last_yielded = self.pos
                    self.state = StateAdvanceAfterWinner()
                    return None
                case StateAdvanceAfterWinner():
                    walker_dot = (self.win_x - self.sx) * self.mdx + (self.win_y - self.sy) * self.mdy
                    while self.m_i + 1 < len(self.mline_seq):
                        mx, my = self.mline_seq[self.m_i + 1]
                        if (mx - self.sx) * self.mdx + (my - self.sy) * self.mdy <= walker_dot:
                            self.m_i += 1
                        else:
                            break
                    self.state = StateAdvanceMLine()
        return

    def cw_substep(self, cost):
        moved = False
        for _ in range(0, 8):
            self.cw_dir = ((self.cw_dir - 1) % (8))
            nx2 = self.cw_px + DX[int(self.cw_dir)]
            ny2 = self.cw_py + DY[int(self.cw_dir)]
            if not (0 <= nx2 and nx2 < self.w and 0 <= ny2 and ny2 < self.h):
                continue
            cell = ny2 * self.stride + nx2
            if cost[int(cell)] != 1000000:
                if 0 <= self.cw_wox and self.cw_wox < self.w and 0 <= self.cw_woy and self.cw_woy < self.h:
                    wdx = self.cw_wox - nx2
                    wdy = self.cw_woy - ny2
                    if wdx == 0 or wdy == 0:
                        face = 0 if wdx == -1 else (1 if wdx == 1 else (2 if wdy == 1 else 3))
                        k = int((self.cw_woy * self.stride + self.cw_wox) * 4 + face)
                        if self.ccw_faces[k] != 0:
                            self.met = True
                        self.cw_faces[k] = 1
                nxt_cross = (ny2 - self.sy) * self.mdx - (nx2 - self.sx) * self.mdy
                if self.cw_cross > 0 and nxt_cross < 0 or self.cw_cross < 0 and nxt_cross > 0 or nxt_cross == 0:
                    cell_dot = (nx2 - self.sx) * self.mdx + (ny2 - self.sy) * self.mdy
                    ddx = nx2 - self.gx
                    ddy = ny2 - self.gy
                    if 0 < cell_dot and cell_dot <= self.goal_dot and ddx * ddx + ddy * ddy < self.hit_d:
                        self.winner = 0
                        self.win_x = nx2
                        self.win_y = ny2
                        return
                self.cw_px = nx2
                self.cw_py = ny2
                self.cw_cross = nxt_cross
                self.cw_path.append(cell)
                if IS_CARDINAL[int(self.cw_dir)]:
                    self.cw_dir = ((self.cw_dir + 2) % (8))
                else:
                    self.cw_dir = ((self.cw_dir + 3) % (8))
                self.cw_wox = self.cw_px + DX[int(self.cw_dir)]
                self.cw_woy = self.cw_py + DY[int(self.cw_dir)]
                moved = True
                if not (0 <= self.cw_wox and self.cw_wox < self.w and 0 <= self.cw_woy and self.cw_woy < self.h):
                    self.cw_alive = False
                break
            if IS_CARDINAL[int(self.cw_dir)]:
                pdx = self.cw_px - nx2
                pdy = self.cw_py - ny2
                face = 0 if pdx == 1 else (1 if pdx == -1 else (2 if pdy == -1 else 3))
                k = int(cell * 4 + face)
                if self.ccw_faces[k] != 0:
                    self.met = True
                self.cw_faces[k] = 1
            self.cw_wox = nx2
            self.cw_woy = ny2
        if not moved:
            self.cw_alive = False

    def ccw_substep(self, cost):
        moved = False
        for _ in range(0, 8):
            self.ccw_dir = ((self.ccw_dir + 1) % (8))
            nx2 = self.ccw_px + DX[int(self.ccw_dir)]
            ny2 = self.ccw_py + DY[int(self.ccw_dir)]
            if not (0 <= nx2 and nx2 < self.w and 0 <= ny2 and ny2 < self.h):
                continue
            cell = ny2 * self.stride + nx2
            if cost[int(cell)] != 1000000:
                if 0 <= self.ccw_wox and self.ccw_wox < self.w and 0 <= self.ccw_woy and self.ccw_woy < self.h:
                    wdx = self.ccw_wox - nx2
                    wdy = self.ccw_woy - ny2
                    if wdx == 0 or wdy == 0:
                        face = 0 if wdx == -1 else (1 if wdx == 1 else (2 if wdy == 1 else 3))
                        k = int((self.ccw_woy * self.stride + self.ccw_wox) * 4 + face)
                        if self.cw_faces[k] != 0:
                            self.met = True
                        self.ccw_faces[k] = 1
                nxt_cross = (ny2 - self.sy) * self.mdx - (nx2 - self.sx) * self.mdy
                if self.ccw_cross > 0 and nxt_cross < 0 or self.ccw_cross < 0 and nxt_cross > 0 or nxt_cross == 0:
                    cell_dot = (nx2 - self.sx) * self.mdx + (ny2 - self.sy) * self.mdy
                    ddx = nx2 - self.gx
                    ddy = ny2 - self.gy
                    if 0 < cell_dot and cell_dot <= self.goal_dot and ddx * ddx + ddy * ddy < self.hit_d:
                        self.winner = 1
                        self.win_x = nx2
                        self.win_y = ny2
                        return
                self.ccw_px = nx2
                self.ccw_py = ny2
                self.ccw_cross = nxt_cross
                self.ccw_path.append(cell)
                if IS_CARDINAL[int(self.ccw_dir)]:
                    self.ccw_dir = ((self.ccw_dir - 2) % (8))
                else:
                    self.ccw_dir = ((self.ccw_dir - 3) % (8))
                self.ccw_wox = self.ccw_px + DX[int(self.ccw_dir)]
                self.ccw_woy = self.ccw_py + DY[int(self.ccw_dir)]
                moved = True
                if not (0 <= self.ccw_wox and self.ccw_wox < self.w and 0 <= self.ccw_woy and self.ccw_woy < self.h):
                    self.ccw_alive = False
                break
            if IS_CARDINAL[int(self.ccw_dir)]:
                pdx = self.ccw_px - nx2
                pdy = self.ccw_py - ny2
                face = 0 if pdx == 1 else (1 if pdx == -1 else (2 if pdy == -1 else 3))
                k = int(cell * 4 + face)
                if self.cw_faces[k] != 0:
                    self.met = True
                self.ccw_faces[k] = 1
            self.ccw_wox = nx2
            self.ccw_woy = ny2
        if not moved:
            self.ccw_alive = False
