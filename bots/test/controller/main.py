from typing import cast

from cambc import (
    Controller,
)
from patch import patch
from save import save


class Player:
    def __init__(self) -> None:
        self.done = False

    def run(self, ct: Controller) -> None:
        if not self.done:
            saved = save(ct)
            patch(saved)
            self.done = True
            ct = cast("Controller", saved)
