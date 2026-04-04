# drewfett/v1 — TODO

## Ideas to explore

### Parallel chain building
Multiple builders work on the same chain simultaneously. One approach: builder A starts routing from the harvester, drops a marker indicating "chain heading toward core from here." Builder B picks up the marker, builds from the other direction (core outward). They meet in the middle. Needs a marker protocol for chain endpoints. Alternative: bidirectional FlowAstar search. Risk: stale beliefs cause chains to not meet or overlap.

### Expanded FlowAstar goals
Allow routing to existing transport that confirms delivery to core (not just core tiles). Would shorten paths and speed up connections. Rejected for now — attaching to inferred chains is fragile if belief is stale. Revisit if we add chain validation (builder walks the chain to verify connectivity before attaching).

## Combat

### Offense
- PLACE_GUNNER task — like PLACE_SENTINEL but for gunners on enemy harvesters. Cheaper, rotatable.
- Targeted attacks using `en_core_pos` — builders explore toward enemy core, place turrets.
- Use `en_frac` / `en_total` from flow to identify high-value enemy infrastructure.

### Defense
- Pre-place sentinel or gunner near core when econ is established (state-driven, not round-driven).
- Launcher near core for throwing enemy builders.
- Score PATROL higher when `my_frac` drops on key infra (chain disruption detection).

## Econ improvements

### Smarter exploration
- Bias explore toward enemy half once own half is well-mapped.
- Use `en_core_pos` to direct exploration.

### Cost awareness
- Check affordability before committing to harvest — don't walk to ore if can't afford harvester.
- Reserve Ti for in-progress chains (don't start a harvester if a chain is half-built).

## Performance
- Profile bucket A* with danger zones — is COST_DANGER adding significant overhead?
- Consider C extension for pathfinding if CPU becomes tight with more builders.
