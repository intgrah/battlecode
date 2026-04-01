# Runtime Truth

This file records the local setup that agents should trust first in this repository.

## Local Toolchain

- The canonical CLI is `venv/bin/cambc`.
- As checked on March 30, 2026, `venv/bin/cambc --version` reports `1.5.2`.
- The repo-local import path resolves `cambc` from `venv/lib/python3.12/site-packages/cambc/__init__.py`.
- `vendor/cambc_runtime/` is only a checked-in snapshot. Its README still describes `1.4.2`, so treat the live `venv` install as the source of truth when behavior differs.

## Commands That Matter

- `venv/bin/cambc run ... --seed N --replay PATH` runs a deterministic local match for behavior and replay generation.
- `venv/bin/cambc watch replay.replay26` opens the bundled visualiser locally.
- `venv/bin/cambc match test BOT_A BOT_B [MAPS]...` runs a remote test match with TLE enforcement.
- `venv/bin/cambc match tests` lists remote test runs.
- `venv/bin/cambc match replay MATCH_ID` downloads remote replay files.

## Working Assumptions

- Use local runs for fast iteration and replay generation.
- Do not trust local `--tle` as a ladder-accurate timing signal. Use local profiling for hotspot work and remote test matches for real TLE validation.
- Use remote test matches before trusting performance-sensitive changes, because local hardware is not the ladder environment.
- Prefer repo-owned tooling under `tools/` over older notes that reference `falafel/...` scripts.
- When docs and local CLI help disagree, record the discrepancy here and bias toward the local runtime until verified otherwise.
- If `cambc.proto` changes, regenerate the local parser with:
  `venv/bin/python -m grpc_tools.protoc -I. --python_out=tools/generated cambc.proto`
