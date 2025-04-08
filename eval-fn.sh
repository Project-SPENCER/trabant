#!/bin/bash

set -ex

FUNCTION="$1"
RNG_SEED="$2"
BASELINE_LENGTH="$3"
N="$4"
STRESS=${5:-"-stress=true"}

if [ -z "$FUNCTION" ] || [ -z "$RNG_SEED" ] || [ -z "$BASELINE_LENGTH" ] || [ -z "$N" ]; then
  echo "Usage: $0 <function> <rng-seed> <baseline-length> <N>"
  exit 1
fi

USERNAME=spencer
SUT_IP=192.168.2.2
MONITOR_IP=192.168.2.5

MEASUREMENT_INTERVAL=1

INPUT_DIR_HOST=/tmp/trabant/input
OUTPUT_DIR_HOST=/tmp/trabant/output
INPUT_DIR_FN=/input
OUTPUT_DIR_FN=/output
# IMAGES_DIR_LOCAL=./pkg/model/images
IMAGES_DIR_MONITOR=/home/$USERNAME/trabant-images
TF_STATESWITCH=off
TF_STATESWITCH_UPDATE_INTERVAL=1
TF_STATESWITCH_INTERVAL=1
RPROXY_BACKOFF_SEC=0.01
UPLOAD_TIMEOUT=60
EVAL_PORT=7010
TF_HTTP_PORT=7002
TF_CONFIG_PORT=7003
LOG_DIR=logs

SUT=$USERNAME@$SUT_IP
MONITOR=$USERNAME@$MONITOR_IP

echo "making"
make

echo "uploading to sut"
rsync -avze ssh eval.bin $SUT:.
rsync -avze ssh tfaas.bin $SUT:.

echo "uploading to monitor"
rsync -avze ssh measure.bin $MONITOR:.
rsync -avze ssh upload.bin $MONITOR:.
# rsync -avze ssh --exclude "*.png" "$IMAGES_DIR_LOCAL" $MONITOR:$IMAGES_DIR_MONITOR

# start the SUT
echo "prepare sut"
ssh $SUT pkill -f tfaas.bin || true
ssh $SUT pkill -f eval.bin || true
ssh $SUT pkill -f pre.bin || true
ssh $SUT pkill -f post.bin || true
ssh $SUT docker stop $(ssh $SUT docker ps -a -q) || true
# ssh $SUT docker system prune -f -a
ssh $SUT sudo rm -rf "$INPUT_DIR_HOST" "$OUTPUT_DIR_HOST" "/tmp/trabant"
ssh $SUT mkdir -p "$INPUT_DIR_HOST"
ssh $SUT mkdir -p "$OUTPUT_DIR_HOST"

echo "start tfaas"
ssh $SUT ./tfaas.bin \
    -stateswitching="$TF_STATESWITCH" \
    -stateswitching-update-interval="$TF_STATESWITCH_UPDATE_INTERVAL" \
    -stateswitching-interval="$TF_STATESWITCH_INTERVAL" \
    -rproxy-backoff-period="$RPROXY_BACKOFF_SEC" \
    -http-port="$TF_HTTP_PORT" \
    -config-port="$TF_CONFIG_PORT" \
    > $LOG_DIR/tfaas.log 2>&1 &

echo "start eval"
ssh $SUT ./eval.bin \
    --tf-endpoint="http://localhost:$TF_HTTP_PORT/all" \
    --port="$EVAL_PORT" \
    --input-dir="$INPUT_DIR_HOST" \
    --output-dir="$OUTPUT_DIR_HOST" \
    --function-name="$FUNCTION" \
    --output-dir="$OUTPUT_DIR_HOST" \
    --fn-input-dir="/files$INPUT_DIR_FN" \
    --fn-output-dir="/files$OUTPUT_DIR_FN" \
    "$STRESS" \
    > $LOG_DIR/eval.log 2>&1 &

echo "upload function"
ssh $MONITOR pkill -f upload.bin || true
ssh $MONITOR ./upload.bin \
    -function="$FUNCTION" \
    -upload-endpoint="http://$SUT_IP:$TF_CONFIG_PORT/upload" \
    -input-dir-fn="$INPUT_DIR_FN" \
    -output-dir-fn="$OUTPUT_DIR_FN" \
    -input-dir-host="$INPUT_DIR_HOST" \
    -output-dir-host="$OUTPUT_DIR_HOST" \
    -timeout="$UPLOAD_TIMEOUT" \
    -env="tflite" \
    -threads=2

echo "waiting 30s to stabilize"
sleep 30

echo "start measurements"
ssh $MONITOR pkill -f measure.bin || true
ssh $MONITOR ./measure.bin \
    --images-dir="$IMAGES_DIR_MONITOR" \
    --endpoint="http://$SUT_IP:$EVAL_PORT" \
    --interval="$MEASUREMENT_INTERVAL" \
    --baseline-length="$BASELINE_LENGTH" \
    --N="$N" \
    --rng-seed="$RNG_SEED"

echo "getting tf logs"
curl -s http://$SUT_IP:$TF_CONFIG_PORT/logs > $LOG_DIR/tfaas-fn.log

# kill the sut
ssh $SUT pkill -f tfaas.bin
ssh $SUT pkill -f eval.bin
wait

echo "test done"
