package rproxy

import (
	"bytes"
	"container/list"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path"
	"sync"
	"sync/atomic"
	"time"
)

type Status uint32

const (
	StatusOK Status = iota
	StatusAccepted
	StatusNotFound
	StatusError
)

type StateServer interface {
	Idle() bool
}

type queuedCall struct {
	Name    string
	Id      string
	Payload []byte
}

func (q *queuedCall) String() string {
	return fmt.Sprintf("(fn: %s, id: %s, payload_len: %d)", q.Name, q.Id, len(q.Payload))
}

type handler string
type fn struct {
	hosts      chan handler
	inflight   *atomic.Int32
	persistDir string
}

type RProxy struct {
	fns    map[string]*fn
	hl     sync.RWMutex
	signal chan struct{}
	// fq          funcQueue.FuncQueue
	fq            list.List
	fql           sync.Mutex
	persistDir    string
	resume        bool
	s             StateServer
	checkPeriod   time.Duration
	backoffPeriod time.Duration
}

func New(s StateServer, checkPeriod time.Duration, backoffPeriod time.Duration, persistDir string, resume bool) *RProxy {
	err := os.MkdirAll(persistDir, 0755)

	if err != nil {
		log.Fatalf("could not create directory: %s", err.Error())
	}

	rp := &RProxy{
		fns: make(map[string]*fn),
		// hosts:    make(map[string]chan handler),
		// inflight: make(map[string]*atomic.Int32),
		signal: make(chan struct{}),
		// fq:          *funcQueue.NewFuncQueue(50),
		fq:            list.List{},
		persistDir:    persistDir,
		resume:        resume,
		s:             s,
		checkPeriod:   checkPeriod,
		backoffPeriod: backoffPeriod,
	}

	//funcs that will await new might require a kill switch
	go rp.executor()
	return rp
}

func (r *RProxy) Add(name string, ips []string) error {
	if len(ips) == 0 {
		return fmt.Errorf("no ips given")
	}

	persistDir := path.Join(r.persistDir, name)

	err := os.MkdirAll(persistDir, 0755)
	if err != nil {
		return fmt.Errorf("could not create directory: %s", err.Error())
	}

	fn := &fn{
		hosts:      make(chan handler, len(ips)),
		inflight:   &atomic.Int32{},
		persistDir: persistDir,
	}

	for _, ip := range ips {
		fn.hosts <- handler(ip)
	}

	r.hl.Lock()
	defer r.hl.Unlock()

	r.fns[name] = fn

	// if function exists, we should update!
	// if _, ok := r.hosts[name]; ok {
	// 	return fmt.Errorf("function already exists")
	// }

	// r.hosts[name] = make(chan handler, len(ips))

	// for _, ip := range ips {
	// 	r.hosts[name] <- handler(ip)
	// }

	// r.inflight[name] = &atomic.Int32{}

	if r.resume {
		// check if there are any existing persisted requests for this function
		files, err := os.ReadDir(persistDir)

		if err != nil {
			log.Printf("could not read directory: %s", err.Error())
		}

		for _, f := range files {
			log.Printf("found persisted request: %s", f.Name())

			p := path.Join(fn.persistDir, f.Name())

			payload, err := os.ReadFile(p)

			if err != nil {
				log.Printf("could not read persisted request: %s", err.Error())
				continue
			}

			r.fql.Lock()
			r.fq.PushBack(queuedCall{Name: name, Id: f.Name(), Payload: payload})
			r.fql.Unlock()
		}
	}

	return nil
}

func (r *RProxy) Del(name string) error {
	r.hl.Lock()
	defer r.hl.Unlock()

	if _, ok := r.fns[name]; !ok {
		return fmt.Errorf("function not found")
	}

	delete(r.fns, name)
	return nil
}

func (r *RProxy) Call(name string, payload []byte, id string, async bool) (Status, []byte) {

	var names []string
	if name == "all" {
		names = []string{}
		r.hl.RLock()
		for f := range r.fns {
			names = append(names, f)
		}
		r.hl.RUnlock()
	} else {
		names = []string{name}

		if !async {
			return r.execute(name, id, payload)
		}
	}

	for _, n := range names {
		// check that the function exists
		r.hl.RLock()
		f, ok := r.fns[n]
		r.hl.RUnlock()

		if !ok {
			log.Printf("function not found: %s", n)
			return StatusNotFound, nil
		}

		// persist the request
		if id != "" {
			p := path.Join(f.persistDir, id)
			log.Printf("creating persisted request: %s", p)

			err := os.WriteFile(p, payload, 0644)
			if err != nil {
				log.Printf("could not persist request: %s", err.Error())
			}
		}
	}

	for _, n := range names {
		//add async requests (calls) to the queue
		r.fql.Lock()
		r.fq.PushBack(queuedCall{Name: n, Id: id, Payload: payload})
		r.fql.Unlock()
		select {
		// if someone is waiting for this
		case r.signal <- struct{}{}:
		default:
		}
	}

	log.Printf("queued call %s %s", name, id)

	return StatusAccepted, nil
}

func (r *RProxy) execute(name string, id string, payload []byte) (Status, []byte) {
	r.hl.RLock()
	f, ok := r.fns[name]
	r.hl.RUnlock()

	if !ok {
		log.Printf("function not found: %s", name)
		return StatusNotFound, nil
	}

	f.inflight.Add(1)
	defer f.inflight.Add(-1)

	h := <-f.hosts // get an available handler
	defer func() {
		f.hosts <- h // return the handler
	}()

	// log.Printf("have handler: %s", h)

	// choose random handler
	// h := handler[rand.Intn(len(handler))]

	log.Printf("chosen handler: %s", h)

	// call function and return results
	log.Printf("start sync request %s %s", name, id)
	req, err := http.NewRequest("POST", fmt.Sprintf("http://%s:8000/fn", h), bytes.NewBuffer(payload))

	if err != nil {
		log.Print(err)
		return StatusError, nil
	}

	req.Header.Set("Content-Type", "application/binary")

	if id != "" {
		req.Header.Set("X-TFaas-ID", id)
	}

	resp, err := http.DefaultClient.Do(req)

	if err != nil {
		log.Print(err)
		return StatusError, nil
	}

	log.Printf("end sync request %s %s", name, id)

	// remove persisted request
	if id != "" {
		p := path.Join(f.persistDir, id)
		log.Printf("removing persisted request: %s", p)

		err := os.Remove(p)
		if err != nil {
			log.Printf("could not remove persisted request: %s", err.Error())
		}
	}

	defer resp.Body.Close()

	res_body, err := io.ReadAll(resp.Body)

	if err != nil {
		log.Print(err)
		return StatusError, nil
	}

	// log.Printf("have response for sync request: %s", res_body)

	if resp.StatusCode != http.StatusOK {
		return StatusError, res_body
	}

	return StatusOK, res_body
}

// profaastinate implementation:
func (r *RProxy) executor() {
	wait := true
	lastCheck := time.Now()
	idle := r.s.Idle()
	maxInflight := int32(50)

	for {
		// either we wait for the signal or the check period
		if wait {
			select {
			case <-r.signal:
			case <-time.After(r.checkPeriod):
			}
		}

		if time.Since(lastCheck) > r.checkPeriod {
			idle = r.s.Idle()
			lastCheck = time.Now()
		}

		wait = true

		if !idle {
			r.fql.Lock()
			log.Printf("state: busy, len(fq) == %d", r.fq.Len())
			r.fql.Unlock()
			continue
		}

		r.fql.Lock()
		if r.fq.Len() == 0 {
			log.Printf("state: idle, len(fq) == %d", r.fq.Len())
			r.fql.Unlock()
			continue
		}

		log.Printf("state: idle, len(fq) == %d", r.fq.Len())

		f := r.fq.Front()

		if f == nil {
			r.fql.Unlock()
			log.Printf("state idle, f == nil")
			continue
		}

		if f.Value == nil {
			log.Printf("state idle, f.Value == nil")
			r.fq.Remove(f)
			r.fql.Unlock()
			continue
		}

		e := r.fq.Remove(f)
		r.fql.Unlock()

		if e == nil {
			log.Printf("state idle, e == nil")
			continue
		}

		q := e.(queuedCall)

		log.Printf("state idle, dequeued %s %s", q.Name, q.Id)

		go func(call queuedCall) {
			s, _ := r.execute(call.Name, call.Id, call.Payload)

			switch s {
			case StatusOK:
				log.Printf("call %s OK", call.Name)
			case StatusNotFound:
				log.Printf("function for call %s not found", call.Name)
			case StatusError:
				log.Printf("call %s error", call.Name)
			}
		}(q)

		r.hl.RLock()
		var totalInflight int32
		for name, f := range r.fns {
			l := f.inflight.Load()
			log.Printf("inflight[%s] == %d", name, l)
			totalInflight += l
		}
		r.hl.RUnlock()
		log.Printf("total inflight == %d", totalInflight)

		wait = totalInflight > maxInflight
		time.Sleep(r.backoffPeriod)
	}
}
