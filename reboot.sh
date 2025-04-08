#!/bin/bash

USERNAME=spencer
SUT_IP=192.168.2.2
MONITOR_IP=192.168.2.5

echo "rebooting sut"
ssh $USERNAME@$SUT_IP sudo reboot now
echo "rebooting monitor"
ssh $USERNAME@$MONITOR_IP sudo reboot now

sleep 5

# wait until devices are available again
until ssh -o ConnectTimeout=1 $USERNAME@$SUT_IP true; do
    echo "waiting for sut to come back"
    sleep 2
done
echo "sut is back"

until ssh -o ConnectTimeout=1 $USERNAME@$MONITOR_IP true; do
    echo "waiting for monitor to come back"
    sleep 2
done

echo "monitor is back"
