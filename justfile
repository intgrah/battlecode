default_map := `ls maps/*.map26 | shuf -n1`

run a b map=default_map:
    cambc run {{ a }} {{ b }} {{ map }}

r a b map=default_map:
    VIRTUAL_ENV= uv run --project pkg/cambcpypy cambcpypy run {{ a }} {{ b }} {{ map }}

v replay="replay.replay26": vv
    pkg/target/release/visualiser-viewer {{ replay }}

vv:
    cargo build --release --manifest-path pkg/Cargo.toml -p visualiser-viewer

be map=default_map: bee
    pkg/target/release/blueprint-editor {{ map }}

bee:
    cargo build --release --manifest-path pkg/Cargo.toml -p blueprint-editor

bv map=default_map: bvv
    pkg/target/release/bugnav-viewer {{ map }}

bvv:
    cargo build --release --manifest-path pkg/Cargo.toml -p bugnav-viewer

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
