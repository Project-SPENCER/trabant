package stateswitcher

type NoSwitch struct{}

func (s *NoSwitch) Idle() bool {
	// do nothing
	return true
}
