//go:build ml && arm64
// +build ml,arm64

package runtimes

import _ "embed"

//go:embed ml/blob-arm64.tar.xz
var MLBlob []byte

//go:embed ml/Dockerfile
var MLDockerfile []byte
