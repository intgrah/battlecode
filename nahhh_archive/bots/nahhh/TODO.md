# TODO (v57)

## Critical — Losing Games

- [ ] **Core defense** — builders patrol far from core, enemy turrets snipe core at turns 500-900 with nobody nearby. Need builders staying near core or proactive turret placement.
- [ ] **Gunner ammo validation** — offensive gunners placed without working ammo feed. Conveyors don't output sideways, bridges can't feed, chain arrival may equal gunner facing.
- [ ] **TLE reduction** — 37-82 TLEs per match on server. Chain cache rebuilds every turn (round_no in key). Profile and optimize hot paths.

## High Priority — Winning More

- [ ] **Core kills** — offensive gunners target peripheral buildings instead of pushing to core. Need reliable ammo chain to gunner within r²≤13 of enemy core.
- [ ] **Splitter tap from existing chains** — route ammo from our econ chains to offensive gunners. Currently only sources from harvesters.
- [ ] **Spawning control** — 49 units on long games. Reserve formula doesn't account for maintenance builders needing ~0 Ti.
- [ ] **Launchers near core** — throw enemy builders away. Cheap disruption.

## Medium Priority

- [ ] **Marker-based ore sharing** — fresh builders skip exploration, walk straight to known ore positions.
- [ ] **Smarter patrol** — maintain builders should patrol a bounded region near core, not entire chain length.
- [ ] **Offensive ammo chain direction** — verify chain's last conveyor doesn't feed into gunner's facing direction.
- [ ] **Counter-parasiting** — detect enemy sentinels on our harvesters, reactive gunner to kill them.

## Low Priority / Ideas

- [ ] **Barriers** around core or key chain junctions
- [ ] **Multiple gunners sharing ammo** — splitter feeds two gunners
- [ ] **Builder death tracking** — core detects unit count drop, spawns replacements
- [ ] **Pre-placed core turret** — gunner/sentinel near core before enemy arrives
- [ ] **Armoured conveyors** — need Ax economy first (shelved)

## Resolved

- [x] Unified builder refactor — dropped aggro/healer roles, all builders generalist
- [x] Chain repair — detect gaps, rebuild with stored direction, cross-builder repair
- [x] Reactive gunner defense — detect enemy turrets, place counter-gunner with ammo
- [x] Turret avoidance — A* danger zones from enemy turret attack tiles
- [x] Task commitment model — seek_ore/connect/idle, suspension/resumption
- [x] Opportunistic sentinels — place on exposed enemy harvesters while exploring
- [x] Offensive gunner attack system — target hierarchy, ammo routing from harvesters
- [x] Gunner rotation — 45° per step toward targets when idle (with ammo check)
- [x] Emergency core spawn — bypass reserve when enemies detected near core
- [x] Sentinel fire control — shoot non-adjacent enemy harvesters, protect ammo sources
- [x] Futile heal prevention — stop healing buildings under 10+ turn sustained attack
- [x] Stuck detection — no_dir counts as stuck, abandon unreachable targets
