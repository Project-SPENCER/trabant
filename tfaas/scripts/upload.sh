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
echo "{\"name\": \"$2\", \"env\": \"$3\", \"threads\": $4, \"zip\": \"$(zip -r - ./* | base64 | tr -d '\n')\"}" > $TMP_FILE
curl http://localhost:8080/upload -d @$TMP_FILE -H "Content-Type: application/json"
rm $TMP_FILE
popd >/dev/null || exit
