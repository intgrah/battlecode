"""Inject replay diffs by repurposing heal diffs.

Each call: possess builder, set its HP below max, zero action cooldown,
call `ct.heal(pos)` which emits an UpdateHp diff, then overwrite the diff
to be MoveBuilderBot or UpdateHp as desired. No markers, no tile issues,
no per-turn limits. One marker entity created on first call (from the heal
target), then reused.

Caller must reset builder base.position at end of frame if needed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rust import EntityBuilderBot, Game
from rust.game_diff import _NICHE_BASE
from rust.game_diff.move_builder_bot import GameDiffMoveBuilderBot
from rust.game_diff.remove_entity import GameDiffRemoveEntity
from rust.game_diff.update_hp import GameDiffUpdateHp

if TYPE_CHECKING:
    from cambc import Controller, Position

_MOVE_DISC = _NICHE_BASE + 1
_REMOVE_DISC = _NICHE_BASE + 2
_UPDATE_HP_DISC = _NICHE_BASE + 4


def _emit_diff(g: Game, ct: Controller, builder_id: int) -> None:
    old_id = ct.get_id()
    g.possess(builder_id)

    me = g.entities[builder_id].as_variant
    assert isinstance(me, EntityBuilderBot)
    me.base.hp = me.base.max_hp - 1
    me.action_cooldown = 0

    ct.heal(me.base.position)

    g.possess(old_id)


def fake_move(
    g: Game, ct: Controller, builder_id: int, target_id: int, to_pos: Position
) -> None:
    _emit_diff(g, ct, builder_id)
    diff = g.replay_recorder.last_diff
    g._raw.write_u64(diff._addr, _MOVE_DISC)
    move = GameDiffMoveBuilderBot(g._raw, diff._addr)
    move.id = target_id
    move.to = to_pos


def fake_remove(g: Game, ct: Controller, builder_id: int, target_id: int) -> None:
    _emit_diff(g, ct, builder_id)
    diff = g.replay_recorder.last_diff
    g._raw.write_u64(diff._addr, _REMOVE_DISC)
    rm = GameDiffRemoveEntity(g._raw, diff._addr)
    rm.id = target_id
    pos = g.entities[target_id].base.position
    tile = g.game_map.tile(pos.x, pos.y)
    if tile.builder_bot == target_id:
        tile.builder_bot = None
    if tile.building == target_id:
        tile.building = None


def fake_update_hp(
    g: Game, ct: Controller, builder_id: int, target_id: int, delta: int
) -> None:
    _emit_diff(g, ct, builder_id)
    diff = g.replay_recorder.last_diff
    g._raw.write_u64(diff._addr, _UPDATE_HP_DISC)
    hp_diff = GameDiffUpdateHp(g._raw, diff._addr)
    hp_diff.id = target_id
    hp_diff.delta = delta
