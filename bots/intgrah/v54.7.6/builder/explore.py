"""Reactive frontier exploration.

Each builder picks an unobserved tile as its target, scoring candidates
by:
  - distance from self (closer is better, base term)
  - heading commitment (prefer targets in the direction we last moved;
    prevents u-turning through already-observed territory)
  - frontier-density along the path to the target (reward routes that
    cross unobserved tiles, not already-trodden ones)
  - cluster penalty (avoid targets near other friendly builders)

Target sticks across turns until reached, observed, or unreachable
(UF component mismatch). The heading is set by `try_move_to` and decays
to None when the bot didn't move last turn.

No hard quadrants, no fixed landmarks. Map shape and other-bot positions
shape the target selection reactively.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Position
from util.constants import MAX_WIDTH

from builder.helpers import make_move

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder

__all__ = ["explore"]


_K_CANDIDATES: int = 20
"""Number of unobserved tiles to sample as candidate targets each replan."""

_LINE_SAMPLES: int = 8
"""Number of points sampled along self->target line for frontier-density score."""

_HEADING_WEIGHT: float = 8.0
"""α: penalty for picking targets misaligned with current heading.
0 = pure distance; large = strict heading commitment."""

_FRONTIER_REWARD: float = 6.0
"""β: reward per unobserved-tile-along-path. Drives the bot toward
candidates whose route cuts through fog rather than known territory."""

_CLUSTER_PENALTY: float = 30.0
"""γ: per-friendly-bot proximity penalty around candidate."""

_CLUSTER_RADIUS: int = 20
"""Friendly bots within this chebyshev radius of a candidate add the
full γ penalty; falls off linearly to 0 at radius."""


def explore(self: Builder, ct: Controller) -> None:
    if self.explore_target is None or _target_invalid(self, self.explore_target):
        self.explore_target = _pick_target(self)

    if self.explore_target is None:
        return
    make_move(self, ct, self.explore_target)


def _target_invalid(self: Builder, target: Position) -> bool:
    """A target is invalid once it has been observed (env transitioned
    from None). UF reachability isn't checked here: an unobserved
    candidate is necessarily not in any UF component (UF only admits
    tiles seeded by observed buildings), so requiring UF membership
    would reject every fog tile by definition.
    """
    i = target.y * MAX_WIDTH + target.x
    return self.env[i] is not None


def _pick_target(self: Builder) -> Position | None:
    """Sample K random unobserved tiles, score each, pick the lowest."""
    w, h = self.w, self.h
    env = self.env
    rng = self.rng
    candidates: list[Position] = []
    for _ in range(_K_CANDIDATES * 4):
        if len(candidates) >= _K_CANDIDATES:
            break
        x = rng.randrange(w)
        y = rng.randrange(h)
        if env[y * MAX_WIDTH + x] is None:
            candidates.append(Position(x, y))
    if not candidates:
        return None

    best: Position | None = None
    best_score = float("inf")
    heading = self.explore_heading
    for c in candidates:
        s = _score(self, c, heading)
        if s < best_score:
            best_score = s
            best = c
    return best


def _score(
    self: Builder,
    c: Position,
    heading: tuple[int, int] | None,
) -> float:
    pos = self.my_pos
    dx = c.x - pos.x
    dy = c.y - pos.y
    chebyshev_d = max(abs(dy), abs(dx))

    score = float(chebyshev_d)

    # Heading commitment: penalty when the target is misaligned with
    # the direction we've been going. cos_align in [-1, 1]; (1 - x) in
    # [0, 2] so a u-turn target costs 2*α.
    if heading is not None and (heading[0] != 0 or heading[1] != 0):
        hx, hy = heading
        # Normalise direction-to-target to chebyshev unit.
        cx = (dx > 0) - (dx < 0)
        cy = (dy > 0) - (dy < 0)
        h_mag = (hx * hx + hy * hy) ** 0.5
        c_mag = (cx * cx + cy * cy) ** 0.5
        if h_mag > 0 and c_mag > 0:
            cos_align = (hx * cx + hy * cy) / (h_mag * c_mag)
            score += _HEADING_WEIGHT * (1.0 - cos_align)

    # Frontier-density along the line: sample tiles between self and
    # target, count unobserved. Reward (subtract) is scaled to the
    # number of unobserved samples, normalised by sample count.
    env = self.env
    unseen = 0
    for k in range(1, _LINE_SAMPLES + 1):
        t = k / (_LINE_SAMPLES + 1)
        sx = int(round(pos.x + t * dx))
        sy = int(round(pos.y + t * dy))
        if 0 <= sx < self.w and 0 <= sy < self.h and env[sy * MAX_WIDTH + sx] is None:
            unseen += 1
    score -= _FRONTIER_REWARD * (unseen / _LINE_SAMPLES)

    # Cluster penalty: if any friendly bot is near the candidate, add
    # to the score. Linear falloff to zero at _CLUSTER_RADIUS.
    for fb in self.friendly_bots:
        if fb == pos:
            continue
        cx = abs(c.x - fb.x)
        cy = abs(c.y - fb.y)
        d = max(cy, cx)
        if d < _CLUSTER_RADIUS:
            score += _CLUSTER_PENALTY * (1.0 - d / _CLUSTER_RADIUS)

    return score
