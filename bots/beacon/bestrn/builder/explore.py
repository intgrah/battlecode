"""
Reactive frontier exploration.

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

import math
from typing import Final

from cambc import Position

from builder.helpers import make_move

_K_CANDIDATES: Final[int] = 20
"""Number of unobserved tiles to sample as candidate targets each replan."""
_LINE_SAMPLES: Final[int] = 8
"""Number of points sampled along self->target line for frontier-density score."""
_HEADING_WEIGHT: Final[float] = 8.0
"""
α: penalty for picking targets misaligned with current heading.
0 = pure distance; large = strict heading commitment.
"""
_FRONTIER_REWARD: Final[float] = 6.0
"""
β: reward per unobserved-tile-along-path. Drives the bot toward
candidates whose route cuts through fog rather than known territory.
"""
_CLUSTER_PENALTY: Final[float] = 30.0
"""γ: per-friendly-bot proximity penalty around candidate."""
_CLUSTER_RADIUS: Final[int] = 20
"""
Friendly bots within this chebyshev radius of a candidate add the
full γ penalty; falls off linearly to 0 at radius.
"""


def explore(builder, ct) -> None:
    if (builder.explore_target is None) or _target_invalid(
        builder, builder.explore_target
    ):
        builder.explore_target = _pick_target(builder)
    target = builder.explore_target
    if target is None:
        return
    make_move(builder, ct, target)


def _target_invalid(builder, target):
    """
    A target is invalid once it has been observed (env transitioned
    from None). UF reachability isn't checked here: an unobserved
    candidate is necessarily not in any UF component (UF only admits
    tiles seeded by observed buildings), so requiring UF membership
    would reject every fog tile by definition.
    """
    i = int(target.y) * 50 + int(target.x)
    return builder.env[i] is not None


def _pick_target(builder):
    """
    Sample K random unobserved tiles within an expanding Chebyshev
    radius of a center, score each, pick the lowest. The radius grows
    linearly from 0.4·s at T0 to cap·s at T100 (capped), where
    `s = max(w, h)`.

    For OFFENSE the center is `en_core_guess` — fog gets cleared in a
    growing orbit around the enemy core rather than around the bot.
    Cap is 1.0 (eventually full map). For ECON / DEFENSE the center
    is the bot itself with cap 0.8.
    """
    w = builder.state.width
    h = builder.state.height
    is_offense = builder.role is not None and (lambda r: r.is_offensive())(builder.role)
    cap: float = 1.0 if is_offense else 0.8
    frac = min(cap, 0.4 + (cap - 0.4) * float(builder.state.round) / 100.0)
    radius = int(float(max(w, h)) * frac)
    center = builder.en_core_guess if is_offense else builder.state.my_pos
    cx = center.x
    cy = center.y
    candidates: list[Position] = []
    for _ in range(20 * 4):
        if len(candidates) >= 20:
            break
        x = int(builder.state.rng.randint(0, int(w - 1)))
        y = int(builder.state.rng.randint(0, int(h - 1)))
        if max(abs(x - cx), abs(y - cy)) > radius:
            continue
        i = int(y) * 50 + int(x)
        if builder.env[i] is None:
            candidates.append(Position(x=x, y=y))
    if not candidates:
        return None
    heading = builder.explore_heading
    best: Position | None = None
    best_score = float("inf")
    for c in candidates:
        score = _score(builder, c, heading)
        if score < best_score:
            best_score = score
            best = c
    return best


def _score(builder, c, heading):
    pos = builder.state.my_pos
    dx = c.x - pos.x
    dy = c.y - pos.y
    chebyshev_d = max(abs(dx), abs(dy))
    score = float(chebyshev_d)
    __opt_hx_hy = heading
    hx = __opt_hx_hy[0] if __opt_hx_hy is not None else None
    hy = __opt_hx_hy[1] if __opt_hx_hy is not None else None
    if __opt_hx_hy is not None and (hx != 0 or hy != 0):
        cx = int(dx > 0) - int(dx < 0)
        cy = int(dy > 0) - int(dy < 0)
        h_mag = abs(math.sqrt(float(hx * hx + hy * hy)))
        c_mag = abs(math.sqrt(float(cx * cx + cy * cy)))
        if h_mag > 0.0 and c_mag > 0.0:
            cos_align = float(hx * cx + hy * cy) / (h_mag * c_mag)
            score += 8.0 * (1.0 - cos_align)
    unseen = 0
    for k in range(1, (8) + 1):
        t = float(k) / float(8 + 1)
        sx = round(float(pos.x) + t * float(dx))
        sy = round(float(pos.y) + t * float(dy))
        if (
            sx >= 0
            and sx < builder.state.width
            and sy >= 0
            and sy < builder.state.height
            and (builder.env[int(sy) * 50 + int(sx)] is None)
        ):
            unseen += 1
    score -= 6.0 * float(unseen) / float(8)
    friendlies: list[Position] = list(builder.state.friendly_bots)
    friendlies.sort(key=lambda p: (p.y, p.x))
    for fb in friendlies:
        if fb == pos:
            continue
        cdx = abs(c.x - fb.x)
        cdy = abs(c.y - fb.y)
        d = max(cdx, cdy)
        if d < 20:
            score += 30.0 * (1.0 - float(d) / float(20))
    return score
