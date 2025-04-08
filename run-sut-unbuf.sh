#!/bin/bash

set -ex

PRE_PORT=$1
INPUT_DIR_HOST=$2
OUTPUT_DIR_HOST=$3
EXPERIMENT_DURATION_SEC=$4
TF_STATESWITCH=$5
TF_STATESWITCH_UPDATE_INTERVAL=$6
TF_STATESWITCH_INTERVAL=$7
TF_STATESWITCH_API_URL=$8
RPROXY_BACKOFF_SEC=$9
TF_HTTP_PORT=${10}
TF_CONFIG_PORT=${11}
INPUT_DIR_FN=${12}
OUTPUT_DIR_FN=${13}
DOWNLINK_ENDPOINT=${14}
TF_PERSIST_DIR=${15}
MAX_CC=${16}
TF_RESUME=${17}
TF_PERSIST_FUNC_DIR=${18}

if [ -z "$PRE_PORT" ] || [ -z "$INPUT_DIR_HOST" ] || [ -z "$OUTPUT_DIR_HOST" ] || [ -z "$EXPERIMENT_DURATION_SEC" ] || [ -z "$TF_STATESWITCH" ] || [ -z "$TF_STATESWITCH_UPDATE_INTERVAL" ] || [ -z "$TF_STATESWITCH_INTERVAL" ] || [ -z "$TF_STATESWITCH_API_URL" ] || [ -z "$RPROXY_BACKOFF_SEC" ] || [ -z "$TF_HTTP_PORT" ] || [ -z "$TF_CONFIG_PORT" ] || [ -z "$INPUT_DIR_FN" ] || [ -z "$OUTPUT_DIR_FN" ] || [ -z "$DOWNLINK_ENDPOINT" ] || [ -z "$TF_PERSIST_DIR" ] || [ -z "$MAX_CC" ] || [ -z "$TF_RESUME" ] || [ -z "$TF_PERSIST_FUNC_DIR" ]; then
  echo "Usage: $0 <pre-port> <input-dir-host> <output-dir-host> <experiment-duration-sec> <tf-stateswitch> <tf-stateswitch-update-interval> <tf-stateswitch-interval> <tf-stateswitch-api-url> <rproxy-backoff-sec> <tf-http-port> <tf-config-port> <input-dir-fn> <output-dir-fn> <downlink-endpoint> <tf-persist-dir> <max-cc> <tf-resume> <tf-persist-func-dir>"
  exit 1
fi

pkill -f tfaas.bin || true
# kill Pre
pkill -f pre.bin || true
# kill Post
pkill -f post.bin || true

# stop all docker containers if TF_RESUME is false
if [ "$TF_RESUME" = "false" ]; then
    docker stop $(docker ps -a -q) || true
    docker system prune -f

    # caused when the script runs after the files have been removed
    # docker decides to create the dir with root permissions
    # TODO: fix this
    sudo rm -rf "$INPUT_DIR_HOST" "$OUTPUT_DIR_HOST" "/tmp/trabant" "$TF_PERSIST_DIR" "$TF_PERSIST_FUNC_DIR"
    mkdir -p "$INPUT_DIR_HOST"
    mkdir -p "$OUTPUT_DIR_HOST"
fi

# run Pre
echo "starting pre"
stdbuf -o0 ./pre.bin \
    -tf-endpoint="http://localhost:$TF_HTTP_PORT/all" \
    -port="$PRE_PORT" \
    -output-dir="$INPUT_DIR_HOST" \
    -fn-input-dir="/files/$INPUT_DIR_FN" \
    -fn-output-dir="/files/$OUTPUT_DIR_FN" \
    -max-cloud-cover="$MAX_CC" \
    > pre.log 2>&1 &

# run Post
echo "starting post"
stdbuf -o0 ./post.bin \
    -input-dir="$INPUT_DIR_HOST" \
    -monitor-dir="$OUTPUT_DIR_HOST" \
    -downlink-endpoint="$DOWNLINK_ENDPOINT" \
    -persist-dir="$TF_PERSIST_DIR" \
    -resume="$TF_RESUME" \
    > post.log 2>&1 &

# run tfaas
echo "starting tfaas"
stdbuf -o0 ./tfaas.bin \
    -stateswitching="$TF_STATESWITCH" \
    -stateswitching-update-interval="$TF_STATESWITCH_UPDATE_INTERVAL" \
    -stateswitching-interval="$TF_STATESWITCH_INTERVAL" \
    -stateswitching-api-url="$TF_STATESWITCH_API_URL" \
    -rproxy-backoff-period="$RPROXY_BACKOFF_SEC" \
    -http-port="$TF_HTTP_PORT" \
    -config-port="$TF_CONFIG_PORT" \
    -persist-dir="$TF_PERSIST_DIR" \
    -resume="$TF_RESUME" \
    -persist-func-dir="$TF_PERSIST_FUNC_DIR" \
    > tfaas.log 2>&1 &

# wait 10 minutes
echo "Waiting for $EXPERIMENT_DURATION_SEC seconds..."
date
sleep "$EXPERIMENT_DURATION_SEC"

echo "getting tfaas logs"
curl -s http://localhost:$TF_CONFIG_PORT/logs > tfaas-fn.log 2>&1

# kill tfaas
pkill -f tfaas.bin || true

# kill Pre
pkill -f pre.bin || true

# kill Post
pkill -f post.bin || true

wait

echo "sut done"
