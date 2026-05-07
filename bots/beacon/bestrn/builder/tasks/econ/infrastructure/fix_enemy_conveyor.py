"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/econ/infrastructure/fix_enemy_conveyor.py`.

Destroy any nearby tile that `leads_to_enemy_building` (i.e. a
friendly conveyor whose downstream chain ultimately reaches an enemy
building, leaking our resources to them) and pave a road in its place.
First tile in vision that qualifies wins.
"""

from __future__ import annotations

from builder.tasks.rejected import TaskRejected


def fix_enemy_conveyor(self_, ct):
    nearby = list(self_.nearby_tiles)
    for pos in nearby:
        if self_.leads_to_enemy_building(pos) and ct.can_destroy(pos):
            ct.destroy(pos)
            self_.apply_local_destroy(pos)
            if ct.can_build_road(pos):
                ct.build_road(pos)
                return None
    return TaskRejected("no enemy-feeding conveyor in action range")
