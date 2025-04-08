package stateswitcher

import (
	"encoding/json"
	"io"
	"log"
	"net/http"
	"time"
)

type APISwitcher struct {
	host     string
	interval time.Duration

	idle bool
}

func NewAPI(host string, interval time.Duration) *APISwitcher {
	s := &APISwitcher{
		host:     host,
		interval: interval,
	}

	go func() {
		for {
			s.update()
			time.Sleep(interval)
		}
	}()

	return s
}

func (s *APISwitcher) update() {

	var idle bool

	r, err := http.Get(s.host)

	if err != nil {
		log.Printf("error: %v", err)
		s.idle = false
		return
	}

	defer r.Body.Close()

	if r.StatusCode != http.StatusOK {
		log.Printf("error: %v", r.Status)
		s.idle = false
		return
	}

	b, err := io.ReadAll(r.Body)

	if err != nil {
		log.Printf("error: %v", err)
		s.idle = false
		return
	}

	json.Unmarshal(b, &idle)

	s.idle = idle
	log.Printf("idle: %t", s.idle)
}

func (s *APISwitcher) Idle() bool {
	return s.idle
}
