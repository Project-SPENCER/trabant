#!/bin/bash

set -ex

MONITOR_PORT=$1
START_TIME=$2
GENERATE_ENDPOINT=$3
TF_UPLOAD_ENDPOINT=$4
INPUT_DIR_FN=$5
OUTPUT_DIR_FN=$6
INPUT_DIR_HOST=$7
OUTPUT_DIR_HOST=$8
DOWNLINK_PORT=$9
UPLOAD_TIMEOUT=${10}
IMAGES_DIR=${11}
FN_ENVIRONMENT=${12}
FN_THREADS=${13}
START_OFFSET_SEC=${14}
TEMP_LIMIT=${15}
INITIAL_CHARGE_PERCENT=${16}
FUNCTIONS=${17}

if [ -z "$MONITOR_PORT" ] || [ -z "$START_TIME" ] || [ -z "$GENERATE_ENDPOINT" ] || [ -z "$TF_UPLOAD_ENDPOINT" ] || [ -z "$INPUT_DIR_FN" ] || [ -z "$OUTPUT_DIR_FN" ] || [ -z "$INPUT_DIR_HOST" ] || [ -z "$OUTPUT_DIR_HOST" ] || [ -z "$DOWNLINK_PORT" ] || [ -z "$UPLOAD_TIMEOUT" ] || [ -z "$IMAGES_DIR" ] || [ -z "$FN_ENVIRONMENT" ] || [ -z "$FN_THREADS" ] || [ -z "$START_OFFSET_SEC" ] || [ -z "$TEMP_LIMIT" ] || [ -z "$INITIAL_CHARGE_PERCENT" ]; then
  echo "Usage: $0 <monitor-port> <start-time> <generate-endpoint> <tf-upload-endpoint> <input-dir-fn> <output-dir-fn> <input-dir-host> <output-dir-host> <downlink-port> <upload-timeout> <images-dir> <fn-environment> <fn-threads> <start-offset-sec> <temp-limit> <initial-charge-percent> <functions>"
  exit 1
fi

pkill -f monitor.bin || true
pkill -f upload.bin || true

# upload functions
for f in $(echo "$FUNCTIONS" | tr "," "\n")
do
    ./upload.bin \
        -function="$f" \
        -upload-endpoint="$TF_UPLOAD_ENDPOINT" \
        -input-dir-fn="$INPUT_DIR_FN" \
        -output-dir-fn="$OUTPUT_DIR_FN" \
        -input-dir-host="$INPUT_DIR_HOST" \
        -output-dir-host="$OUTPUT_DIR_HOST" \
        -timeout="$UPLOAD_TIMEOUT" \
        -env="$FN_ENVIRONMENT" \
        -threads="$FN_THREADS"
done

# run monitor
echo "starting monitor"
./monitor.bin \
    -port="$MONITOR_PORT" \
    -start-time="$START_TIME" \
    -images-dir="$IMAGES_DIR" \
    -endpoint="$GENERATE_ENDPOINT" \
    -downlink-port="$DOWNLINK_PORT" \
    -start-offset-sec="$START_OFFSET_SEC" \
    -temp-limit="$TEMP_LIMIT" \
    -initial-charge-percent="$INITIAL_CHARGE_PERCENT" \
    > monitor.log 2>&1 &

wait

# kill monitor
pkill -f monitor.bin || true

echo "monitor done"
