"""Translation of `bots/intgrah/v54.7.9/builder/hooks/indicators.py`."""

from __future__ import annotations

from util.debug import dot


def indicators(builder, ct) -> None:
    """
    Paint per-builder economy state into the replay: ore targets,
    foundry target, chain endpoints. Only has effect when `DEBUG_LOG` is set
    (the helpers in `util.log` are no-ops otherwise).
    """
    target = builder.ore_target
    if target is not None:
        dot(ct, target, 255, 220, 0)
    target = builder.ax_ore_target
    if target is not None:
        dot(ct, target, 200, 0, 200)
    target = builder.offensive_ore_target
    if target is not None:
        dot(ct, target, 255, 80, 0)
    target = builder.foundry_target
    if target is not None:
        dot(ct, target, 0, 200, 0)
    target = builder.dangling_output
    if target is not None:
        dot(ct, target, 0, 200, 200)
