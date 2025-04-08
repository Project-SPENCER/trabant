//go:build python3 && arm64
// +build python3,arm64

package runtimes

import _ "embed"

//go:embed python3/blob-arm64.tar.xz
var Python3Blob []byte

//go:embed python3/Dockerfile
var Python3Dockerfile []byte
