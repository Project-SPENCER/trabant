#!/bin/bash

USERNAME=spencer
SUT_IP=192.168.2.2
MONITOR_IP=192.168.2.5

echo "shutting down sut"
ssh $USERNAME@$SUT_IP sudo shutdown now
echo "shutting down monitor"
ssh $USERNAME@$MONITOR_IP sudo shutdown now
