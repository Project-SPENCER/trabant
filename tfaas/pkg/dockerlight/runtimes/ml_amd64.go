//go:build ml && amd64
// +build ml,amd64

package runtimes

import _ "embed"

//go:embed ml/blob-amd64.tar.xz
var MLBlob []byte

//go:embed ml/Dockerfile
var MLDockerfile []byte
