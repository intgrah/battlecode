"""Gunner turret logic for trollbot — fire at enemy builder bots in front."""

from cambc import Controller


def run_gunner(player, ct: Controller) -> None:
    pos = ct.get_position()
    facing = ct.get_direction()
    target = pos.add(facing)

    if not ct.is_in_vision(target):
        return

    bbid = ct.get_tile_builder_bot_id(target)
    if bbid is not None and ct.get_team(bbid) != ct.get_team() and ct.can_fire(target):
        ct.fire(target)
