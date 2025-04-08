#!/bin/bash

# upload.sh folder-name name env threads

set -e

if ! command -v curl &> /dev/null
then
    echo "curl could not be found but is a pre-requisite for this script"
    exit
fi

if ! command -v zip &> /dev/null
then
    echo "zip could not be found but is a pre-requisite for this script"
    exit
fi

if ! command -v base64 &> /dev/null
then
    echo "base64 could not be found but is a pre-requisite for this script"
    exit
fi

pushd "$1" >/dev/null || exit
TMP_FILE=tmp.json

JSON="{"
JSON="$JSON\"name\": \"$2\""
JSON="$JSON, \"env\": \"$3\""
JSON="$JSON, \"threads\": $4"

# if there is a 5th argument, it is the mount directories
if [ "$5" ]; then

    # split on comma
    IFS=',' read -r -a mount_dirs <<< "$5"

    JSON="$JSON, \"mounts\": ["

    for mounts in "${mount_dirs[@]}"; do
        # split on : if exists
        IFS=':' read -r -a mount_dir_parts <<< "$mounts"

        # first part is the mount directory, second is the target name, third (optional) is ro or rw (default is ro)
        mount_dir=${mount_dir_parts[0]}

        # check that the mount directory exists
        if [ ! -d "$mount_dir" ]; then
            echo "Mount directory $mount_dir does not exist. Is an absolute path provided?"
            exit 1
        fi

        # make sure the mount directory is an absolute path
        if [[ "$mount_dir" != /* ]]; then
            echo "Mount directory $mount_dir is not an absolute path. Please provide an absolute path."
            exit 1
        fi

        # add to JSON
        JSON="$JSON{\"mount_dir\": \"$mount_dir\","
        JSON="$JSON\"mount_target\": \"${mount_dir_parts[1]}\","
        if [ "${mount_dir_parts[2]}" == "rw" ]; then
            JSON="$JSON\"mount_rw\": true},"
        else
            JSON="$JSON\"mount_rw\": false},"
        fi
    done

    # remove the last comma
    JSON="${JSON%?}"

    JSON="$JSON]"
fi

JSON="$JSON, \"zip\": \"$(zip -r - ./* | base64 | tr -d '\n')\""

JSON="$JSON}"

echo "$JSON" > $TMP_FILE
curl http://localhost:8080/upload -d @$TMP_FILE -H "Content-Type: application/json"
rm $TMP_FILE
popd >/dev/null || exit
