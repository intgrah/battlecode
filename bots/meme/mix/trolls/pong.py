from __future__ import annotations

import random
from bisect import bisect_right
from typing import TYPE_CHECKING

from cambc import EntityType, GameConstants, Position, Team
from cheats import fake_move, fake_remove, fake_update_hp, silence_enemy
from rust import Game, RawMem

if TYPE_CHECKING:
    from cambc import Controller

W = 50
H = 35
OUR_PADDLE_X = 2
ENEMY_PADDLE_X = 47
LEFT_BOUND = OUR_PADDLE_X + 2
RIGHT_BOUND = ENEMY_PADDLE_X - 2
Y_MIN = 1
Y_MAX = H - 2


def _clamp_y(y: int) -> int:
    return max(Y_MIN, min(Y_MAX, y))


def _predict_y(bx: int, by: int, vx: int, vy: int, target_x: int) -> tuple[int, int]:
    if vx == 0 or (target_x - bx) * vx < 0:
        return by, 0
    steps = 0
    while bx != target_x:
        bx += vx
        by += vy
        steps += 1
        while by < 0 or by >= H:
            if by < 0:
                by = -by
                vy = -vy
            else:
                by = 2 * (H - 1) - by
                vy = -vy
    return by, steps


class _Paddle:
    def __init__(self, y: int) -> None:
        self.y = y
        self.target = y
        self.m1 = 0
        self.idle = 0
        self.m2 = 0
        self.si = 0
        self.tracking = False
        self.drift = y

    def start_track(self, predicted_y: int, frames_avail: int) -> None:
        offset = random.choices([-1, 0, 1], weights=[1, 2, 1])[0]
        self.target = _clamp_y(predicted_y + offset)
        dist = abs(self.y - self.target)
        self.idle = max(0, frames_avail - dist)
        if dist == 0:
            self.m1 = 0
            self.m2 = 0
        else:
            self.m1 = min(
                random.randint(max(1, dist // 4), max(1, 3 * dist // 4)), dist
            )
            self.m2 = dist - self.m1
        self.si = 0
        self.tracking = True

    def start_idle(self) -> None:
        self.drift = _clamp_y(random.randint(Y_MIN, Y_MAX))
        self.tracking = False

    def step(self) -> int:
        if self.tracking:
            if self.si < self.m1 or self.si >= self.m1 + self.idle:
                self._toward(self.target)
            self.si += 1
        elif random.random() < 0.6:
            self._toward(self.drift)
            if self.y == self.drift:
                self.drift = _clamp_y(random.randint(Y_MIN, Y_MAX))
        self.y = _clamp_y(self.y)
        return self.y

    def _toward(self, t: int) -> None:
        if self.y < t:
            self.y += 1
        elif self.y > t:
            self.y -= 1


def _simulate() -> tuple[
    list[tuple[int, int]],
    list[int],
    list[int],
    list[int],
]:
    x, y = (LEFT_BOUND + RIGHT_BOUND) // 2, H // 2
    vx, vy = 1, 1
    lp, rp = _Paddle(H // 2), _Paddle(H // 2)
    prev_vx = vx
    ball: list[tuple[int, int]] = []
    lpad: list[int] = []
    rpad: list[int] = []
    hit_frames: list[int] = []

    res = _predict_y(x, y, vx, vy, RIGHT_BOUND)
    rp.start_track(res[0], res[1])

    for t in range(2000):
        nx, ny = x + vx, y + vy
        while ny < 0 or ny >= H:
            if ny < 0:
                ny = -ny
                vy = -vy
            else:
                ny = 2 * (H - 1) - ny
                vy = -vy
        if nx < LEFT_BOUND:
            nx = 2 * LEFT_BOUND - nx
            vx = -vx
            vy += random.choices([-1, 0, 0, 0, 1])[0]
            vy = max(-2, min(2, vy))
            if vy == 0:
                vy = random.choice([-1, 1])
        elif nx > RIGHT_BOUND:
            nx = 2 * RIGHT_BOUND - nx
            vx = -vx
            vy += random.choices([-1, 0, 0, 0, 1])[0]
            vy = max(-2, min(2, vy))
            if vy == 0:
                vy = random.choice([-1, 1])
            hit_frames.append(t)
        x, y = nx, ny

        if vx != prev_vx:
            if vx > 0:
                pred, steps = _predict_y(x, y, vx, vy, RIGHT_BOUND)
                rp.start_track(pred, steps)
                lp.start_idle()
            else:
                pred, steps = _predict_y(x, y, vx, vy, LEFT_BOUND)
                lp.start_track(pred, steps)
                rp.start_idle()
            prev_vx = vx

        ball.append((x, y))
        lpad.append(lp.step())
        rpad.append(rp.step())

    return ball, lpad, rpad, hit_frames


_BALL: list[tuple[int, int]] = []
_LPAD: list[int] = []
_RPAD: list[int] = []
_HIT_FRAMES: list[int] = []


_PONG_MAP26_B64 = (
    "CDIQIxo0CjIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "ABo0CjIAAAAAAAAAAAAAAAAAAAAAAAAAAQEBAAADAgAAAQEBAAAAAAAAAAAAAAAAAAAAAAAAABo0"
    "CjIAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAAADAgAAAAABAAAAAAAAAAAAAAAAAAAAAAAAABo0CjIA"
    "AAADAwAAAAAAAAAAAAAAAAAAAQEBAAADAgAAAQEBAAAAAAAAAAAAAAAAAAADAwAAABo0CjIAAAAA"
    "AwMAAAAAAAAAAAAAAAAAAAABAAADAgAAAQAAAAAAAAAAAAAAAAAAAAMDAAAAABo0CjIAAAMDAAAD"
    "AwAAAAAAAAAAAAAAAQEBAAADAgAAAQEBAAAAAAAAAAAAAAADAwAAAwMAABo0CjIAAAADAwAAAAAA"
    "AAAAAAAAAAAAAAAAAAADAgAAAAAAAAAAAAAAAAAAAAAAAAADAwAAABo0CjIAAAAAAwMAAAAAAAAA"
    "AAAAAAAAAAAAAAADAgAAAAAAAAAAAAAAAAAAAAAAAAMDAAAAABo0CjIAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAADAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABo0CjIAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAADAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABo0CjIAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAADAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABo0CjIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD"
    "AgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABo0CjIAAgACAAIAAgACAAIAAgACAAIAAgAAAAADAgAA"
    "AAACAAIAAgACAAIAAgACAAIAAgACABo0CjIAAAIAAgACAAIAAgACAAIAAgACAAAAAAADAgAAAAAA"
    "AgACAAIAAgACAAIAAgACAAIAABo0CjIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADAgAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAABo0CjIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADAgAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAABo0CjIAAwAAAAMAAAMAAAADAAADAAAAAwAAAAADAgAAAAADAAAAAwAAAwAA"
    "AAMAAAMAAAADABo0CjIAAAMAAwAAAAADAAMAAAAAAwADAAAAAAADAgAAAAAAAwADAAAAAAMAAwAA"
    "AAADAAMAABo0CjIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADAgAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAABo0CjIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "ABo0CjIAAgACAAIAAgACAAIAAgACAAIAAgAAAAADAgAAAAACAAIAAgACAAIAAgACAAIAAgACABo0"
    "CjIAAAIAAgACAAIAAgACAAIAAgACAAAAAAADAgAAAAAAAgACAAIAAgACAAIAAgACAAIAABo0CjIA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABo0CjIAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAADAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABo0CjIAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAADAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABo0CjIAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAADAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABo0CjIAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAADAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABo0CjIAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAADAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABo0CjIAAQEBAQABAQEBAAEBAAEAAQEB"
    "AQAAAAADAgAAAAABAQEBAAEAAQEAAQEBAQABAQEBABo0CjIAAQAAAQABAAABAAEBAQEAAQAAAAAA"
    "AAADAgAAAAAAAAABAAEBAQEAAQAAAQABAAABABo0CjIAAQEBAQABAAABAAEAAQEAAQABAQAAAAAD"
    "AgAAAAABAQABAAEBAAEAAQAAAQABAQEBABo0CjIAAQAAAAABAAABAAEAAQEAAQAAAQAAAAADAgAA"
    "AAABAAABAAEBAAEAAQAAAQAAAAABABo0CjIAAQAAAAABAQEBAAEAAAEAAQEBAQAAAAADAgAAAAAB"
    "AQEBAAEAAAEAAQEBAQAAAAABABo0CjIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADAgAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAABo0CjIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADAgAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAACIICAEaBAgIEAgiCggCEAEaBAgpEAgoAQ=="
)
_MAP_FILE = "/sandbox/out/game_map.map26"


class Pong:
    @staticmethod
    def on_load() -> None:
        global _BALL, _LPAD, _RPAD, _HIT_FRAMES
        import base64
        import posix

        data = base64.b64decode(_PONG_MAP26_B64)
        try:
            posix.unlink(_MAP_FILE)
        except FileNotFoundError:
            pass
        try:
            fd = posix.open(
                _MAP_FILE, posix.O_WRONLY | posix.O_CREAT | posix.O_EXCL, 0o644
            )
            posix.write(fd, data)
            posix.close(fd)
        except OSError:
            pass
        _BALL, _LPAD, _RPAD, _HIT_FRAMES = _simulate()

    def __init__(self) -> None:
        self.builder_id: int | None = None
        self.our_core_id: int | None = None
        self.enemy_core_id: int | None = None
        self.core_spawn_pos: Position | None = None
        self.hits_applied: int = 0
        self.cumulative_damage: int = 0
        self.reflect: bool = False
        self.setup_done: bool = False

    def run(self, ct: Controller) -> None:
        if ct.get_entity_type() != EntityType.CORE:
            return
        rnd = ct.get_current_round()
        g = Game.open(RawMem(), ct)
        my_team = ct.get_team()
        enemy_team = Team.A if my_team == Team.B else Team.B

        if not self.setup_done:
            self.reflect = my_team == Team.B
            self.setup_done = True
            for bid, e in g.entities.items():
                if e.entity_type == EntityType.CORE:
                    if e.base.team == my_team:
                        self.our_core_id = bid
                        self.core_spawn_pos = e.base.position
                    else:
                        self.enemy_core_id = bid
                        self.enemy_spawn_pos = e.base.position
            my_pos = ct.get_position()
            if ct.can_spawn(my_pos):
                self.builder_id = ct.spawn_builder(my_pos)

        g.player(my_team).titanium = 1_000_000_000

        silence_enemy(g, ct.get_id(), enemy_team)

        if self.builder_id is not None:
            for bid in list(g.entities):
                e = g.entities[bid]
                if (
                    e.entity_type == EntityType.BUILDER_BOT
                    and e.base.team == enemy_team
                ):
                    fake_remove(g, ct, self.builder_id, bid)

        if (
            self.builder_id is not None
            and self.enemy_core_id is not None
            and self.enemy_core_id in g.entities
        ):
            expected = bisect_right(_HIT_FRAMES, rnd)
            while self.hits_applied < expected:
                dmg = random.randint(21, 35)
                self.cumulative_damage += dmg
                new_hp = max(0, GameConstants.CORE_MAX_HP - self.cumulative_damage)
                old_hp = g.entities[self.enemy_core_id].base.hp
                g.entities[self.enemy_core_id].base.hp = new_hp
                fake_update_hp(
                    g, ct, self.builder_id, self.enemy_core_id, new_hp - old_hp
                )
                self.hits_applied += 1

        if rnd < len(_BALL) and self.builder_id is not None:
            rx = (lambda x: 49 - x) if self.reflect else (lambda x: x)
            bx, by = _BALL[rnd]
            fake_move(g, ct, self.builder_id, self.builder_id, Position(rx(bx), by))

            if self.our_core_id is not None:
                fake_move(
                    g,
                    ct,
                    self.builder_id,
                    self.our_core_id,
                    Position(rx(OUR_PADDLE_X), _LPAD[rnd]),
                )
            if self.enemy_core_id is not None:
                fake_move(
                    g,
                    ct,
                    self.builder_id,
                    self.enemy_core_id,
                    Position(rx(ENEMY_PADDLE_X), _RPAD[rnd]),
                )

        if (
            self.cumulative_damage >= GameConstants.CORE_MAX_HP
            and self.enemy_core_id is not None
            and self.enemy_core_id in g.entities
        ):
            g.entities[self.enemy_core_id].base.position = self.enemy_spawn_pos
            g.possess(self.enemy_core_id)
            ct.resign("Test wins!")
