from cambc import Controller, EntityType


class TurretUnit:
    def run(self, ct: Controller) -> None:
        my = ct.get_team()
        best = None
        best_prio = -1
        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) == my:
                continue
            epos = ct.get_position(eid)
            if not ct.can_fire(epos):
                continue
            prio = 10 if ct.get_entity_type(eid) == EntityType.BUILDER_BOT else 1
            if prio > best_prio:
                best_prio = prio
                best = epos
        if best:
            ct.fire(best)
