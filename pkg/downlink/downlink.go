package downlink

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"sync"
)

type s struct {
	Name string `json:"name"`
	Size uint64 `json:"size"`
}

func SendToRemote(name string, size uint64, endpoint string) error {
	j, err := json.Marshal(s{name, size})

	if err != nil {
		return err
	}

	res, err := http.Post(endpoint, "application/json", bytes.NewBuffer(j))

	if err != nil {
		return err
	}

	if res.StatusCode != http.StatusOK {
		return fmt.Errorf("unexpected status code: %d", res.StatusCode)
	}

	return nil
}

type Downlink struct {
	queueSizeBytes uint64
	*sync.Mutex
}

func NewDownlink() *Downlink {
	return &Downlink{
		queueSizeBytes: 0,
		Mutex:          &sync.Mutex{},
	}
}

func (d *Downlink) Start(port int) {
	// start the server
	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "POST" {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}

		// decode the image
		info := s{}

		err := json.NewDecoder(r.Body).Decode(&info)

		if err != nil {
			http.Error(w, "could not parse image info", http.StatusBadRequest)
			return
		}

		log.Printf("received image %s of size %d bytes", info.Name, info.Size)

		r.Body.Close()

		d.Receive(info.Name, info.Size)
	})

	go func() {
		log.Printf("downlink server started on port %d", port)
		err := http.ListenAndServe(fmt.Sprintf(":%d", port), nil)
		if err != nil {
			log.Fatal(err)
		}
	}()
}

func (d *Downlink) Receive(name string, size uint64) {
	d.Lock()
	defer d.Unlock()
	d.queueSizeBytes += uint64(size)
}

func (d *Downlink) ReadNBytes(n uint64) uint64 {
	d.Lock()
	defer d.Unlock()

	log.Printf("downlink queue size: %d bytes, reading %d bytes", d.queueSizeBytes, n)

	if d.queueSizeBytes <= uint64(n) {
		n = d.queueSizeBytes
	}

	d.queueSizeBytes -= uint64(n)
	return uint64(n)
}

func (d *Downlink) GetQueueSize() uint64 {
	// d.Lock()
	// defer d.Unlock()
	// not needed because we're only reading
	return d.queueSizeBytes
}
