"""Data contracts for the HITL annotation platform.

Three main records: Game, Event, Annotation. Closed tag sets for outcomes and
reasons are defined here so they can't drift from the UI.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class OutcomeAuto(StrEnum):
    """Auto-tags derived from the replay. Every game has these."""

    CORE_DESTROYED_US = "core_destroyed_us"
    CORE_DESTROYED_THEM = "core_destroyed_them"
    LOST_AX = "lost_ax"
    LOST_TI = "lost_ti"
    LOST_HARVESTERS = "lost_harvesters"
    WON_AX = "won_ax"
    WON_TI = "won_ti"
    WON_HARVESTERS = "won_harvesters"
    COINFLIP = "coinflip"
    TLE = "tle"
    CRASH = "crash"
    NO_REFINED_AX = "no_refined_ax_produced"
    NO_FOUNDRY = "no_foundry_built"
    BUILDERS_LOST_MANY = "builders_lost_many"


class OutcomeSubjective(StrEnum):
    """Subjective game-level tags added by the annotator."""

    CHAIN_BROKEN = "chain_broken"
    DEFENCE_TOO_LATE = "defence_too_late"
    OFFENCE_TOO_GREEDY = "offence_too_greedy"
    EXPOSED_HARVESTER = "exposed_harvester"
    BUILDERS_WASTED = "builders_wasted"
    WRONG_ROLE_MIX = "wrong_role_mix"
    ROLE_THRASHING = "role_thrashing"
    NEVER_FOUND_CORE = "never_found_core"
    WRONG_SYMMETRY_COMMIT = "wrong_symmetry_commit"


class Reason(StrEnum):
    """Per-event rationale tags for why the bot's decision was wrong."""

    WRONG_ROLE = "wrong_role"
    BAD_PATH = "bad_path"
    MISSED_BUILD = "missed_build"
    OVEREXTENDED = "overextended"
    UNDEREXTENDED = "underextended"
    WASTED_ACTION = "wasted_action"
    FRIENDLY_FIRE_RISK = "friendly_fire_risk"
    EXPOSED_SELF = "exposed_self"
    IGNORED_TARGET = "ignored_target"
    WRONG_BUILD_DIR = "wrong_build_dir"


class Direction(StrEnum):
    N = "n"
    NE = "ne"
    E = "e"
    SE = "se"
    S = "s"
    SW = "sw"
    W = "w"
    NW = "nw"
    CENTRE = "centre"
    NONE = "none"


class ActionKind(StrEnum):
    MOVE = "move"
    BUILD = "build"
    ATTACK = "attack"
    HEAL = "heal"
    DESTROY = "destroy"
    NOTHING = "nothing"


class BuildType(StrEnum):
    ROAD = "road"
    CONVEYOR = "conveyor"
    BRIDGE = "bridge"
    SPLITTER = "splitter"
    HARVESTER = "harvester"
    GUNNER = "gunner"
    SENTINEL = "sentinel"
    LAUNCHER = "launcher"
    BREACH = "breach"
    FOUNDRY = "foundry"
    BARRIER = "barrier"
    ARMOURED_CONVEYOR = "armoured_conveyor"
    MARKER = "marker"


class EventTrigger(StrEnum):
    """Why this event was selected as critical."""

    UNIT_DIED_NEXT_TURN = "unit_died_next_turn"
    ASTAR_FAILED = "astar_failed"
    BUILD_FAILED = "build_failed"
    ROLE_CHANGED = "role_changed"
    HP_DROP = "hp_drop"
    IDLE_WITH_TI = "idle_with_ti"
    TASK_SWITCH_BURST = "task_switch_burst"


class Game(BaseModel):
    replay_id: str
    our_side: Literal["A", "B"]
    opponent: str
    map_name: str
    winner: Literal["us", "them"] | None
    end_turn: int
    outcome_auto: list[OutcomeAuto] = Field(default_factory=list)
    outcome_subjective: list[OutcomeSubjective] = Field(default_factory=list)


class BeliefState(BaseModel):
    role: str | None
    ore_target: tuple[int, int] | None
    dangling_output: tuple[int, int] | None
    scout_target: tuple[int, int] | None
    symmetry: str | None
    # Compact grid references. The full grids live in the event blob on disk.
    ti: int
    ax: int
    scale: float


class GameState(BaseModel):
    my_pos: tuple[int, int]
    hp: int
    max_hp: int
    action_cooldown: int
    move_cooldown: int
    nearby_enemies: list[tuple[int, int]]
    nearby_allies: list[tuple[int, int]]


class Event(BaseModel):
    event_id: str
    replay_id: str
    turn: int
    unit_id: int
    unit_type: str
    team: Literal["A", "B"]
    trigger: EventTrigger
    belief: BeliefState
    game: GameState
    bot_action: str  # human-readable, e.g. "move N" or "build conveyor E"


class Annotation(BaseModel):
    event_id: str
    direction: Direction = Direction.NONE
    action: ActionKind
    build_type: BuildType | None = None
    reasons: list[Reason] = Field(default_factory=list)
    free_text: str = ""
    bot_was_right: bool | None = None  # filled on reveal step
    outcome_context: list[OutcomeSubjective] = Field(default_factory=list)
    session_id: str
    timestamp_ms: int
