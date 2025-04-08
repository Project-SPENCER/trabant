//go:build linux
// +build linux

package dockerlight

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

// getProcessCPUTime reads the CPU time of a process from /proc/[pid]/stat
func getProcessCPUTime(pid int) (int64, error) {
	data, err := os.ReadFile(fmt.Sprintf("/proc/%d/stat", pid))
	if err != nil {
		return 0, err
	}
	fields := strings.Fields(string(data))

	// fields[13] is utime (time in user mode), fields[14] is stime (time in kernel mode)
	utime, err := strconv.ParseInt(fields[13], 10, 64)
	if err != nil {
		return 0, err
	}
	stime, err := strconv.ParseInt(fields[14], 10, 64)
	if err != nil {
		return 0, err
	}

	return utime + stime, nil
}

// getTotalCPUTime reads the total CPU time from /proc/stat
func getTotalCPUTime() (int64, error) {
	data, err := os.ReadFile("/proc/stat")
	if err != nil {
		return 0, err
	}
	lines := strings.Split(string(data), "\n")
	cpuFields := strings.Fields(lines[0]) // The first line contains the total CPU stats

	var totalCPUTime int64
	for _, field := range cpuFields[1:] { // Skip the "cpu" label
		value, err := strconv.ParseInt(field, 10, 64)
		if err != nil {
			return 0, err
		}
		totalCPUTime += value
	}

	return totalCPUTime, nil
}

func calculateCPUUsage(pid int, interval time.Duration) (float64, error) {
	// Get initial CPU times
	initialProcessTime, err := getProcessCPUTime(pid)
	if err != nil {
		return 0, err
	}
	initialTotalTime, err := getTotalCPUTime()
	if err != nil {
		return 0, err
	}

	// Wait for the interval
	time.Sleep(interval)

	// Get CPU times again after the interval
	finalProcessTime, err := getProcessCPUTime(pid)
	if err != nil {
		return 0, err
	}
	finalTotalTime, err := getTotalCPUTime()
	if err != nil {
		return 0, err
	}

	// Calculate deltas
	deltaProcess := finalProcessTime - initialProcessTime
	deltaTotal := finalTotalTime - initialTotalTime

	// Calculate CPU usage percentage
	cpuUsage := (float64(deltaProcess) / float64(deltaTotal)) * 100.0

	return cpuUsage, nil
}
