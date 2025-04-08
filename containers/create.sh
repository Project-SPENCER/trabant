#!/bin/bash

# 1. zip file
# add only fn.py and multiclass.tflite
# then give us the size
echo "zip file compressed"
zip -r - fn.py multiclass.tflite | wc -c
echo "tar file uncompressed"
tar -cf - fn.py multiclass.tflite | wc -c

# 2. normal container
# print the size of each layer
echo "normal container"
docker build -t mc-normal -f debian.Dockerfile .
docker history mc-normal
docker image save mc-normal | wc -c
docker image save mc-normal | gzip | wc -c

# test that the container works
docker run --rm \
    -d \
    --name mc-normal \
    -p8080:8080 \
    -v "$(pwd)/example:/example" \
    mc-normal

sleep 5
# python3 test.py http://localhost:8080 "$(pwd)/example" /example
curl --data '{"in_path": "/example", "out_path": "/example/mc-normal.out", "lat": 0.0, "lon": 0.0, "alt": 0.0, "clouds": 0.0, "sunlit": 0.0}' -H "Content-Type: application/json" -X POST http://localhost:8080

echo "\n $!"
rm -rf example/mc-normal.out

docker stop mc-normal
docker image rm mc-normal

# 3. slim container
# print the size of each layer
echo "slim container"
docker build -t mc-slim -f slim.Dockerfile .
docker history mc-slim
docker image save mc-slim | wc -c
docker image save mc-slim | gzip | wc -c

# test that the container works
docker run --rm \
    -d \
    --name mc-slim \
    -p8080:8080 \
    -v "$(pwd)/example:/example" \
    mc-slim

sleep 5
# python3 test.py http://localhost:8080 "$(pwd)/example" /example
curl --data '{"in_path": "/example", "out_path": "/example/mc-slim.out", "lat": 0.0, "lon": 0.0, "alt": 0.0, "clouds": 0.0, "sunlit": 0.0}' -H "Content-Type: application/json" -X POST http://localhost:8080

echo "\n $!"
rm -rf example/mc-slim.out

docker stop mc-slim
docker image rm mc-slim

# 4. alpine container
# print the size of each layer
echo "alpine container"
docker build -t mc-alpine -f alpine.Dockerfile .
docker history mc-alpine
docker image save mc-alpine | wc -c
docker image save mc-alpine | gzip | wc -c

# test that the container works
docker run --rm \
    -d \
    --name mc-alpine \
    -p8080:8080 \
    -v "$(pwd)/example:/example" \
    mc-alpine

sleep 5
curl --data '{"in_path": "/example", "out_path": "/example/mc-alpine.out", "lat": 0.0, "lon": 0.0, "alt": 0.0, "clouds": 0.0, "sunlit": 0.0}' -H "Content-Type: application/json" -X POST http://localhost:8080

echo "\n $!"
rm -rf example/mc-alpine.out

docker stop mc-alpine
docker image rm mc-alpine
