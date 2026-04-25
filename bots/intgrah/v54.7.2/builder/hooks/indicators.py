from __future__ import annotations

from typing import TYPE_CHECKING

from util.debug import dot

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


def indicators(self: Builder, ct: Controller) -> None:
    """Paint per-builder economy state into the replay: ore targets,
    foundry target, chain endpoints. Only has effect when DEBUG_LOG is set
    (the helpers in `util.log` are no-ops otherwise).
    """
    if self.ore_target is not None:
        dot(ct, self.ore_target, 255, 220, 0)  # Ti ore target: yellow
    if self.ax_ore_target is not None:
        dot(ct, self.ax_ore_target, 200, 0, 200)  # Ax ore target: magenta
    if self.offensive_ore_target is not None:
        dot(ct, self.offensive_ore_target, 255, 80, 0)  # offensive Ti ore: orange
    if self.foundry_target is not None:
        dot(ct, self.foundry_target, 0, 200, 0)  # foundry target: green
    if self.dangling_output is not None:
        dot(ct, self.dangling_output, 0, 200, 200)  # dangling: cyan
