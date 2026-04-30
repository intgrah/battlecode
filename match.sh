#!/bin/bash
VIRTUAL_ENV= uv run --project cambc_pypy cambc_pypy run "$@"
lib/visualiser/viewer/target/release/visualiser-viewer replay.replay26
