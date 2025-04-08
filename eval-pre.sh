#!/bin/bash

set -ex

# DURATION=120
DURATION=$1
REPEAT=$2

if [ -z "$DURATION" ] || [ -z "$REPEAT" ]; then
    echo "Usage: $0 <duration> <repeat>"
    exit 1
fi

USERNAME=spencer
SUT_IP=192.168.2.2
MONITOR_IP=192.168.2.5
PRE_PORT=7001
MONITOR=$USERNAME@$MONITOR_IP
LOG_DIR=eval-pre-logs/d"$DURATION"-r"$REPEAT"

mkdir -p "$LOG_DIR"

echo "uploading to monitor"
rsync -avze ssh measure.bin $MONITOR:.

./test-fn.sh "" "$DURATION" &

echo "waiting 30s to stabilize"
sleep 30

echo "start measurements"
ssh $MONITOR pkill -f measure.bin || true
ssh $MONITOR ./measure.bin \
    --images-dir="" \
    --endpoint="http://$SUT_IP:$PRE_PORT/" \
    --interval="1" \
    --baseline-length=$(( DURATION-30 )) \
    --N="0" \
    --rng-seed="0" \
    > "$LOG_DIR"/measure.log 2>&1 &

wait

echo "copying logs"
mv logs/monitor.log "$LOG_DIR"
mv logs/tfaas.log "$LOG_DIR"
mv logs/tfaas-fn.log "$LOG_DIR"
mv logs/pre.log "$LOG_DIR"
mv logs/post.log "$LOG_DIR"

echo "eval pre done"
