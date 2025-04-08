package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"path"
	"time"

	"github.com/project-spencer/trabant/pkg/clouds"
	"github.com/project-spencer/trabant/pkg/model"
)

func sendToTF(img model.Acquisition, outputDir string, fnInputDir string, fnOutputDir string, tfEndpoint string, maxCC float64) {
	// perform cloud detection
	t1 := time.Now()

	if !img.Sunlit {
		log.Printf("image is not sunlit, skipping")
		return
	}

	cloudCover := clouds.Coverage(&img)

	log.Printf("cloud cover: %.2f", cloudCover)

	if cloudCover >= maxCC {
		log.Printf("cloud cover above %.2f, skipping", maxCC)
		return
	}

	t2 := time.Now()

	// save each layer as a tiff
	dirname := fmt.Sprintf("%d", img.T)

	err := os.MkdirAll(path.Join(outputDir, dirname), 0755)

	if err != nil {
		log.Printf("could not create directory: %s", err.Error())
		return
	}

	for b := range img.I {

		fname := fmt.Sprintf("%s.tiff", b)

		// save the image
		err := os.WriteFile(path.Join(outputDir, dirname, fname), img.I[b], 0644)

		if err != nil {
			log.Printf("could not write file: %s", err.Error())
			return
		}
	}

	t3 := time.Now()

	log.Printf("cloud detection took %s, saving images took %s", t2.Sub(t1), t3.Sub(t2))

	log.Printf("saved images to %s", path.Join(outputDir, dirname))

	// call subsequent steps (if necessary)

	out := struct {
		Lat     float64 `json:"lat"`
		Lon     float64 `json:"lon"`
		Alt     float64 `json:"alt"`
		Clouds  float64 `json:"clouds"`
		Sunlit  bool    `json:"sunlit"`
		InPath  string  `json:"in_path"`
		OutPath string  `json:"out_path"`
	}{
		Lat:     img.Lat,
		Lon:     img.Lon,
		Alt:     img.Alt,
		Clouds:  cloudCover,
		Sunlit:  img.Sunlit,
		InPath:  path.Join(fnInputDir, dirname),
		OutPath: fnOutputDir,
	}

	j, err := json.Marshal(out)

	if err != nil {
		log.Printf("could not marshal json: %s", err.Error())
		return
	}

	req, err := http.NewRequest("POST", tfEndpoint, bytes.NewBuffer(j))

	if err != nil {
		log.Printf("could not create request: %s", err.Error())
		return
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-TFaas-ID", fmt.Sprintf("%d", img.T))

	log.Printf("calling tf with %d", img.T)

	resp, err := http.DefaultClient.Do(req)

	if err != nil {
		log.Printf("could not call tf: %s", err.Error())
		return
	}

	resp.Body.Close()

	log.Printf("called tf with %d", img.T)
}

func handleReq(w http.ResponseWriter, r *http.Request, outputDir string, fnInputDir string, fnOutputDir string, tfEndpoint string, maxCC float64) {
	if r.Method != "POST" {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// decode the image
	var img model.Acquisition

	t1 := time.Now()

	err := img.Decode(r.Body)

	t2 := time.Now()

	if err != nil {
		http.Error(w, "could not decode image", http.StatusBadRequest)
		return
	}

	log.Printf("received image at t=%d, lat=%f, lon=%f, alt=%f, bands=%d", img.T, img.Lat, img.Lon, img.Alt, len(img.I))

	w.WriteHeader(http.StatusOK)

	log.Printf("decoded image in %s", t2.Sub(t1))

	sendToTF(img, outputDir, fnInputDir, fnOutputDir, tfEndpoint, maxCC)
}

func main() {
	log.SetPrefix("[pre] ")
	log.SetFlags(log.Ldate | log.Ltime | log.Lmicroseconds | log.LstdFlags | log.Lshortfile | log.LUTC)

	var tfEndpoint string
	var port int
	var maxCC float64
	var outputDir string
	var fnInputDir string
	var fnOutputDir string

	flag.StringVar(&tfEndpoint, "tf-endpoint", "", "endpoint of tfaas server")
	flag.IntVar(&port, "port", 0, "port to listen on")
	flag.Float64Var(&maxCC, "max-cloud-cover", 0.3, "maximum cloud cover")
	flag.StringVar(&outputDir, "output-dir", "", "output directory for images")
	flag.StringVar(&fnInputDir, "fn-input-dir", "", "input directory for functions")
	flag.StringVar(&fnOutputDir, "fn-output-dir", "", "output directory for functions")

	flag.Parse()

	// make the output dir or delete it if it exists
	err := os.RemoveAll(outputDir)

	if err != nil {
		log.Fatalf("could not remove output directory: %s", err.Error())
	}

	err = os.MkdirAll(outputDir, 0755)

	if err != nil {
		log.Fatalf("could not create output directory: %s", err.Error())
	}

	// start the server
	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		handleReq(w, r, outputDir, fnInputDir, fnOutputDir, tfEndpoint, maxCC)
	})

	log.Fatal(http.ListenAndServe(fmt.Sprintf(":%d", port), nil))
}
