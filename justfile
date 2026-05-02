default_map := `ls maps/*.map26 | shuf -n1`

run a b map=default_map:
    cambc run {{ a }} {{ b }} {{ map }}

r a b map=default_map:
    VIRTUAL_ENV= uv run --project pkg/cambc_pypy cambc_pypy run {{ a }} {{ b }} {{ map }}

w replay="replay.replay26":
    cambc watch {{ replay }}

gen:
    uv run python pkg/bench_nav/codegen/gen.py
    ruff check --fix pkg/bench_nav/src/bench_nav/spsp/astar_jps.py pkg/bench_nav/src/bench_nav/spsp/astar_jps_dial.py
    ruff format pkg/bench_nav/src/bench_nav/spsp/astar_jps.py pkg/bench_nav/src/bench_nav/spsp/astar_jps_dial.py

proto:
    protoc \
      --python_out=pkg/proto/src/proto \
      --pyi_out=pkg/proto/src/proto \
      --proto_path=pkg/proto/src/proto \
      pkg/proto/src/proto/cambc.proto
    ruff check --fix pkg/proto/
    ruff format pkg/proto/

docs:
    #!/usr/bin/env bash
    cd docs
    curl -s https://docs.battlecode.cam/llms.txt -o llms.txt
    grep -oP 'https://docs\.battlecode\.cam/\S+\.md' llms.txt | while read -r url; do
        path="${url#https://docs.battlecode.cam/}"
        mkdir -p "$(dirname "$path")"
        curl -s "$url" -o "$path"
        echo "$path"
    done

pyrust-build:
    cargo build -p pyrust -p pyrust-translate -p pyrust-harness

pyrust-test: pyrust-build
    target/debug/pyrust-harness

pyrust-translate *args: pyrust-build
    target/debug/pyrust-translate {{ args }}
