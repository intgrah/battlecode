#!/bin/bash
# Minimal AWS sweep driver: rsync the rust workspace stuff + maps + sweep.py
# to the running 'bc' EC2 instance, build there, run the sweep.
#
# Usage: ./scripts/aws_sweep.sh BOT_A BOT_B [extra args to sweep.py]
# Examples:
#   ./scripts/aws_sweep.sh drewfett_v1000 v56
#   ./scripts/aws_sweep.sh drewfett_v1000 v56 --workers 60

set -euo pipefail

if [ $# -lt 2 ]; then
    echo "usage: $0 BOT_A BOT_B [--workers N] [--maps m1,m2,...]"
    exit 1
fi
BOT_A=$1
BOT_B=$2
shift 2
EXTRA="$@"

REMOTE_USER=admin
REMOTE_DIR=/home/admin/battlecode
KEY=~/.ssh/AWS-LDN.pem

IP=$(~/Code/venvs/cambc/bin/python -c "
import boto3
c = boto3.resource('ec2', region_name='us-east-1')
for i in c.instances.filter(Filters=[{'Name':'tag:Name','Values':['bc']},{'Name':'instance-state-name','Values':['running']}]):
    print(i.public_ip_address); break
")
if [ -z "$IP" ]; then
    echo "no running 'bc' instance — run: aws.py up c7g.16xlarge"
    exit 1
fi
echo "AWS: $IP"

SSH_OPTS="-i $KEY -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"

echo "=== rsync (sources only) ==="
# Clean up paths from a previous run that flattened them.
ssh $SSH_OPTS $REMOTE_USER@$IP "rm -rf $REMOTE_DIR/rs $REMOTE_DIR/sweep.py" || true
# --relative preserves directory structure on the remote.
rsync -az -e "ssh $SSH_OPTS" --relative \
    --exclude=target --exclude=__pycache__ --exclude='*.replay26' \
    crates bots/rs Cargo.toml Cargo.lock maps scripts/sweep.py pkg \
    $REMOTE_USER@$IP:$REMOTE_DIR/

echo "=== build on remote ==="
ssh $SSH_OPTS $REMOTE_USER@$IP bash <<EOF
set -e
cd $REMOTE_DIR
which cc >/dev/null 2>&1 || sudo apt-get install -y -qq build-essential protobuf-compiler >/dev/null
which protoc >/dev/null 2>&1 || sudo apt-get install -y -qq protobuf-compiler >/dev/null
[ -d \$HOME/.cargo ] || curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable --profile minimal
. \$HOME/.cargo/env
# pyo3 needs Python 3.12+ (`Py_NewInterpreterFromConfig`). Debian 12
# default is 3.11; point pyo3 at uv's 3.12.
export PYO3_PYTHON=\$HOME/.local/share/uv/python/cpython-3.12-linux-aarch64-gnu/bin/python3
cargo build --release -p libre -p $BOT_A -p $BOT_B 2>&1 | tail -3
EOF

echo "=== sweep on remote ==="
ssh $SSH_OPTS $REMOTE_USER@$IP "cd $REMOTE_DIR && python3 scripts/sweep.py $BOT_A $BOT_B $EXTRA"
