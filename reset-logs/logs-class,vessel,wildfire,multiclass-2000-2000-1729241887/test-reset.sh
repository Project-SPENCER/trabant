#!/bin/bash

set -ex

FUNCTION="$1"
DURATION_BEFORE="$2"
DURATION_AFTER="$3"

if [ -z "$DURATION_BEFORE" ] || [ -z "$DURATION_AFTER" ]; then
  echo "Usage: $0 <function> <duration-before> <duration-after>"
  exit 1
fi

# log dir
LOG_NAME="logs-$FUNCTION-$DURATION_BEFORE-$DURATION_AFTER-$(date +%s)"

USERNAME=spencer
SUT_IP=192.168.2.2
MONITOR_IP=192.168.2.5

MONITOR_PORT=7000
START_TIME=1682379292
PRE_PORT=7001
DOWNLINK_PORT=7004
INPUT_DIR_HOST=/home/spencer/trabant/input
OUTPUT_DIR_HOST=/home/spencer/trabant/output
INPUT_DIR_FN=/input
OUTPUT_DIR_FN=/output
TF_PERSIST_DIR=/home/spencer/tfaas-persist
TF_PERSIST_FUNC_DIR=/home/spencer/tfaas-persist-func
# IMAGES_DIR_LOCAL=./pkg/model/images
IMAGES_DIR_MONITOR=/home/$USERNAME/trabant-images
RESET_AFTER=$DURATION_BEFORE
TF_STATESWITCH=api
TF_STATESWITCH_UPDATE_INTERVAL=1
TF_STATESWITCH_INTERVAL=1
RPROXY_BACKOFF_SEC=0.01
UPLOAD_TIMEOUT=60
TF_HTTP_PORT=7002
TF_CONFIG_PORT=7003
ROOT_LOG_DIR=reset-logs
LOG_DIR=$ROOT_LOG_DIR/$LOG_NAME
RSYNC_TIMEOUT=15
FN_ENVIRONMENT=tflite
FN_THREADS=8
START_OFFSET_SEC=11000 # 15618 # 0
MAX_CC=0.3
TEMP_LIMIT=50 # degC
TF_RESUME=false
INITIAL_CHARGE_PERCENT=68

TF_STATESWITCH_API_URL=http://$MONITOR_IP:$MONITOR_PORT
DOWNLINK_ENDPOINT=http://$MONITOR_IP:$DOWNLINK_PORT
SUT=$USERNAME@$SUT_IP
MONITOR=$USERNAME@$MONITOR_IP

mkdir -p $LOG_DIR

# place a copy of this script in the log dir so we can check parameters later
cp "$0" "$LOG_DIR/."

echo "making"
make

echo "uploading to sut"
# upload the experiment script to the SUT
rsync -ave ssh run-sut-unbuf.sh $SUT:.
# upload dependencies
rsync -avze ssh pre.bin $SUT:.
rsync -avze ssh post.bin $SUT:.
rsync -avze ssh tfaas.bin $SUT:.

echo "uploading to monitor"
# upload the experiment script to the monitor
rsync -ave ssh run-monitor.sh $MONITOR:.
rsync -avze ssh monitor.bin $MONITOR:.
rsync -avze ssh upload.bin $MONITOR:.
# rsync -avze ssh --exclude "*.png" "$IMAGES_DIR_LOCAL" $MONITOR:$IMAGES_DIR_MONITOR

# clear any existing logs
ssh $MONITOR rm -rf monitor.log
ssh $MONITOR touch monitor.log
ssh $SUT rm -rf pre.log
ssh $SUT touch pre.log
ssh $SUT rm -rf post.log
ssh $SUT touch post.log
ssh $SUT rm -rf tfaas.log
ssh $SUT touch tfaas.log

# start the monitor
# <monitor-port> <start-time> <image-width> <image-height> <interval-sec> <generate-endpoint> <functions> <tf-upload-endpoint> <input-dir-fn> <output-dir-fn> <input-dir-host> <output-dir-host>
echo "starting monitor"
ssh $MONITOR ./run-monitor.sh \
    $MONITOR_PORT \
    $START_TIME \
    http://$SUT_IP:$PRE_PORT/ \
    http://$SUT_IP:$TF_CONFIG_PORT/upload \
    $INPUT_DIR_FN \
    $OUTPUT_DIR_FN \
    $INPUT_DIR_HOST \
    $OUTPUT_DIR_HOST \
    $DOWNLINK_PORT \
    $UPLOAD_TIMEOUT \
    $IMAGES_DIR_MONITOR \
    $FN_ENVIRONMENT \
    $FN_THREADS \
    $START_OFFSET_SEC \
    $TEMP_LIMIT \
    $INITIAL_CHARGE_PERCENT \
    "$FUNCTION" &

# start the SUT
# <monitor-addr> <pre-port> <input-dir> <output-dir> <experiment-duration-secs> <tf-stateswitch> <tf-stateswitch-update-interval> <tf-stateswitch-interval> <tf-stateswitch-api-url> <rproxy-backoff-sec> <tf-http-port> <tf-config-port>
echo "starting sut"
ssh $SUT ./run-sut-unbuf.sh \
    $PRE_PORT \
    $INPUT_DIR_HOST \
    $OUTPUT_DIR_HOST \
    "$(( DURATION_BEFORE * 10))" \
    $TF_STATESWITCH \
    $TF_STATESWITCH_UPDATE_INTERVAL \
    $TF_STATESWITCH_INTERVAL \
    $TF_STATESWITCH_API_URL \
    $RPROXY_BACKOFF_SEC \
    $TF_HTTP_PORT \
    $TF_CONFIG_PORT \
    $INPUT_DIR_FN \
    $OUTPUT_DIR_FN \
    $DOWNLINK_ENDPOINT \
    $TF_PERSIST_DIR \
    $MAX_CC \
    $TF_RESUME \
    $TF_PERSIST_FUNC_DIR &

sleep 20
# first, wait for monitor.bin to be running
while ! ssh $MONITOR pgrep -f monitor.bin; do
    echo "waiting for monitor to start"
    sleep 1
done

# wait for reset duration
echo "waiting for reset duration"
for i in $(seq 1 $RESET_AFTER); do
    echo "reset in $((RESET_AFTER - i)) seconds"
    sleep 1
done

# pull the cable!
echo "PULL CABLE NOW!"

# wait for the cable to be pulled by ssh into the SUT

while ssh -o ConnectTimeout=1 -o ServerAliveInterval=1 $SUT true; do
    echo "SUT still up"
    sleep 1
done

# put the cable back
echo "PUT CABLE BACK NOW!"

# wait for the SUT to come back up
until ssh -o ConnectTimeout=1 $SUT true; do
    echo "SUT still down"
    sleep 2
done

echo "SUT is back"

echo "starting sut"
sleep 5

# first, backup the old logs
rsync -avz --timeout $RSYNC_TIMEOUT -e ssh $SUT:pre.log $LOG_DIR/pre-before.log
rsync -avz --timeout $RSYNC_TIMEOUT -e ssh $SUT:post.log $LOG_DIR/post-before.log
rsync -avz --timeout $RSYNC_TIMEOUT -e ssh $SUT:tfaas.log $LOG_DIR/tfaas-before.log

TF_RESUME=true
ssh $SUT ./run-sut-unbuf.sh \
    $PRE_PORT \
    $INPUT_DIR_HOST \
    $OUTPUT_DIR_HOST \
    "$DURATION_AFTER" \
    $TF_STATESWITCH \
    $TF_STATESWITCH_UPDATE_INTERVAL \
    $TF_STATESWITCH_INTERVAL \
    $TF_STATESWITCH_API_URL \
    $RPROXY_BACKOFF_SEC \
    $TF_HTTP_PORT \
    $TF_CONFIG_PORT \
    $INPUT_DIR_FN \
    $OUTPUT_DIR_FN \
    $DOWNLINK_ENDPOINT \
    $TF_PERSIST_DIR \
    $MAX_CC \
    $TF_RESUME \
    $TF_PERSIST_FUNC_DIR &

SUT_PID=$!

# wait for the SUT to finish
wait $SUT_PID

# kill the monitor
ssh $MONITOR pkill -f monitor.bin || true

echo "downloading logs"

# download the monitor logs
rsync -avz --timeout $RSYNC_TIMEOUT -e ssh $MONITOR:monitor.log $LOG_DIR/monitor.log

# download the SUT log
rsync -avz --timeout $RSYNC_TIMEOUT -e ssh $SUT:pre.log $LOG_DIR/pre-after.log
rsync -avz --timeout $RSYNC_TIMEOUT -e ssh $SUT:post.log $LOG_DIR/post-after.log
rsync -avz --timeout $RSYNC_TIMEOUT -e ssh $SUT:tfaas.log $LOG_DIR/tfaas-after.log

echo "test done"
