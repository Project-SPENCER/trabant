//go:build tflite && arm64
// +build tflite,arm64

package runtimes

import _ "embed"

//go:embed tflite/blob-arm64.tar.xz
var TFLiteBlob []byte

//go:embed tflite/Dockerfile
var TFLiteDockerfile []byte
