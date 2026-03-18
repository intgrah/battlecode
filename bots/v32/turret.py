import json

from cambc import Controller, EntityType


class TurretUnit:
    def run(self, ct: Controller) -> None:
        my = ct.get_team()
        best = None
        best_prio = -1
        best_type = None
        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) == my:
                continue
            epos = ct.get_position(eid)
            if not ct.can_fire(epos):
                continue
            et = ct.get_entity_type(eid)
            prio = 10 if et == EntityType.BUILDER_BOT else 1
            if prio > best_prio:
                best_prio = prio
                best = epos
                best_type = et.name
        if best:
            ct.fire(best)
            print(
                json.dumps(
                    {
                        "_dbg": True,
                        "unit": "turret",
                        "action": "fire",
                        "target": [best.x, best.y],
                        "target_type": best_type,
                    },
                    separators=(",", ":"),
                ),
            )
