//go:build darwin
// +build darwin

package dockerlight

import "time"

func calculateCPUUsage(pid int, interval time.Duration) (float64, error) {
	time.Sleep(interval)
	return 0, nil
}
