from __future__ import annotations

import random

from trolls.meme import Meme
from trolls.pong import Pong

_PLAYERS = [Meme, Pong]
Player = random.choice(_PLAYERS)
Player.on_load()
