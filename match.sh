#!/bin/bash
VIRTUAL_ENV= uv run --project cambcpypy cambcpypy run "$@"
lib/visualiser/viewer/target/release/visualiser-viewer replay.replay26
