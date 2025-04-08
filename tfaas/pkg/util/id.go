package util

import (
	"crypto/rand"
	"fmt"
)

// UID returns a new unique identifier
func UID() string {
	// generate a new unique identifier that is 16 bytes long
	b := make([]byte, 16)
	_, err := rand.Read(b)
	if err != nil {
		panic(err)
	}

	// convert to hex string
	return fmt.Sprintf("%x", b)
}
