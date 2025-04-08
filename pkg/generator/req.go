package generator

import (
	"bytes"
	"fmt"
	"log"
	"net/http"
	"time"

	"github.com/project-spencer/trabant/pkg/model"
)

func MakeReq(img *model.Acquisition, endpoint string) error {
	// encode and send to endpoint
	var b bytes.Buffer

	err := img.Encode(&b)

	if err != nil {
		return fmt.Errorf("could not encode image: %v", err)
	}

	r, err := http.NewRequest("POST", endpoint, &b)

	if err != nil {
		return fmt.Errorf("could not create request: %v", err)
	}

	r.Header.Set("Content-Type", "application/octet-stream")

	t1 := time.Now()
	log.Printf("sending image %d at %s", img.T, t1)
	resp, err := http.DefaultClient.Do(r)

	if err != nil {
		return err
	}

	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}

	t2 := time.Now()
	log.Printf("sent image %d at %s", img.T, t2)

	return nil
}
