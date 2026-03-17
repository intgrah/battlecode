from __future__ import annotations

Pos = tuple[int, int]

TEAM_LABEL: dict[int, str] = {0: "A", 1: "B"}

DIR_DELTA: dict[int, Pos] = {
    0: (0, 0),
    1: (0, -1),
    2: (1, -1),
    3: (1, 0),
    4: (1, 1),
    5: (0, 1),
    6: (-1, 1),
    7: (-1, 0),
    8: (-1, -1),
}

MOBILE_KINDS: frozenset[str] = frozenset({"builder_bot"})
CONVEYOR_KINDS: frozenset[str] = frozenset(
    {"conveyor", "armoured_conveyor", "splitter", "bridge"},
)
TURRET_KINDS: frozenset[str] = frozenset({"gunner", "sentinel", "breach", "launcher"})

VISION_SQ: dict[str, int] = {
    "builder_bot": 20,
    "core": 36,
    "gunner": 13,
    "sentinel": 32,
    "breach": 10,
    "launcher": 26,
}

ATTACK_SQ: dict[str, int] = {
    "gunner": 13,
    "sentinel": 32,
    "breach": 5,
    "launcher": 26,
}

SCALE_PCT: dict[str, float] = {
    "builder_bot": 0.0,
    "conveyor": 1.0,
    "armoured_conveyor": 1.0,
    "splitter": 1.0,
    "bridge": 1.0,
    "harvester": 10.0,
    "foundry": 100.0,
    "road": 0.5,
    "barrier": 1.0,
    "gunner": 10.0,
    "sentinel": 10.0,
    "breach": 10.0,
    "launcher": 10.0,
}
