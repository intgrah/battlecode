#!/usr/bin/env fish

function usage
    echo "Usage: remote_match.fish HOST BOT_A BOT_B [OPTIONS]" >&2
    echo "" >&2
    echo "Run a cambc match on a remote machine." >&2
    echo "" >&2
    echo "  HOST       SSH host (e.g. bc, chi)" >&2
    echo "  BOT_A      Local path to bot A directory" >&2
    echo "  BOT_B      Local path to bot B directory" >&2
    echo "" >&2
    echo "Options:" >&2
    echo "  -m MAP     Map name (without .map26)" >&2
    echo "  -s SEED    Random seed (default: 1)" >&2
    echo "  -o REPLAY  Local replay output path (default: replay.replay26)" >&2
    echo "  -t TLE     Turn time limit in ms (default: 0 = off)" >&2
    exit 1
end

if test (count $argv) -lt 3
    usage
end

set HOST $argv[1]
set BOT_A $argv[2]
set BOT_B $argv[3]
set -e argv[1..3]

set MAP ""
set SEED 1
set REPLAY replay.replay26
set TLE 0

while set -q argv[1]
    switch $argv[1]
        case -m
            set MAP $argv[2]
            set -e argv[1..2]
        case -s
            set SEED $argv[2]
            set -e argv[1..2]
        case -o
            set REPLAY $argv[2]
            set -e argv[1..2]
        case -t
            set TLE $argv[2]
            set -e argv[1..2]
        case '*'
            usage
    end
end

set BOT_A_NAME (basename $BOT_A)
set BOT_B_NAME (basename $BOT_B)
set RUN_ID "run."(random)

rsync -a --exclude __pycache__ $BOT_A/ $HOST:~/battlecode/bots/$BOT_A_NAME/ -q
if test $BOT_A_NAME != $BOT_B_NAME
    rsync -a --exclude __pycache__ $BOT_B/ $HOST:~/battlecode/bots/$BOT_B_NAME/ -q
end

set MAP_ARG ""
if test -n "$MAP"
    set MAP_ARG "maps/"(string replace -r '\.map26$' '' $MAP)".map26"
end

ssh $HOST "bash -c '
cd ~/battlecode
REPLAY=/tmp/$RUN_ID.replay26
trap \"rm -f \$REPLAY\" EXIT INT TERM
cambc run $BOT_A_NAME $BOT_B_NAME $MAP_ARG --seed $SEED --tle $TLE --replay \$REPLAY >&2
cat \$REPLAY
'" >$REPLAY
