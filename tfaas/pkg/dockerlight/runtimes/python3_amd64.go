//go:build python3 && amd64
// +build python3,amd64

package runtimes

import _ "embed"

//go:embed python3/blob-amd64.tar.xz
var Python3Blob []byte

//go:embed python3/Dockerfile
var Python3Dockerfile []byte
