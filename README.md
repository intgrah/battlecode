# Battlecode 2026

Bot code for the [Cambridge Battlecode](https://docs.battlecode.cam) competition. Set on Titan — destroy the enemy core.

## Structure

- `bots/intgrah/` — versioned bot iterations (`v0` through `v46`)
- `scripts/` — replay analysis and visualisation tools
- `docs/` — local copy of game docs
- `maps/` — map files for local testing

## Quick start

Requires Python 3.12 and `cambc` CLI.

```sh
just match v46 v45          # run a match and print summary
just watch v46 v45          # run with live visualiser
just stats                  # summary of last replay
just analyze                # full analysis of last replay
```

## Development

```sh
just snapshot               # freeze current version, create next
just lint                   # ruff check --fix
just fmt                    # ruff format
just f                      # ty + lint + fmt
just submit                 # upload latest version to ladder
just status                 # check ladder rating
```

See `justfile` for the full list of commands.
