from __future__ import annotations

from typing import Final

from rust.base import RustStruct, i32


class PlayerState(RustStruct):
    """
    PlayerState (20 B, align 4):

      +0   4  titanium            i32
      +4   4  axionite            i32
      +8   4  titanium_collected  i32
      +12  4  axionite_collected  i32
      +16  4  scale_milli         i32
    """

    _TITANIUM_OFF: Final = 0
    _AXIONITE_OFF: Final = 4
    _TITANIUM_COLLECTED_OFF: Final = 8
    _AXIONITE_COLLECTED_OFF: Final = 12
    _SCALE_MILLI_OFF: Final = 16

    titanium = i32(_TITANIUM_OFF)
    axionite = i32(_AXIONITE_OFF)
    titanium_collected = i32(_TITANIUM_COLLECTED_OFF)
    axionite_collected = i32(_AXIONITE_COLLECTED_OFF)
    scale_milli = i32(_SCALE_MILLI_OFF)
