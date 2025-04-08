//go:build tflite && amd64
// +build tflite,amd64

package runtimes

import _ "embed"

//go:embed tflite/blob-amd64.tar.xz
var TFLiteBlob []byte

//go:embed tflite/Dockerfile
var TFLiteDockerfile []byte
