#!/bin/bash

set -e

PYTHON_VERSION=3.11
ALPINE_VERSION=3.19

if ! command -v docker &> /dev/null
then
    echo "docker could not be found but is a pre-requisite for this script"
    exit
fi

pushd "$1" >/dev/null || exit
# check that there is a requirements.txt file
if [ ! -f requirements.txt ]; then
    echo "requirements.txt file not found"
    exit
fi

docker run --rm --entrypoint /bin/sh \
    -v "$(pwd)":/app \
    -w /app \
    python:${PYTHON_VERSION}-alpine${ALPINE_VERSION} \
    -c "pip install -r requirements.txt --upgrade -t ."
popd >/dev/null || exit
