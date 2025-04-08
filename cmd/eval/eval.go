package main

import (
	"bytes"
	_ "embed"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path"
	"strings"
	"time"

	"github.com/fsnotify/fsnotify"
	"github.com/project-spencer/trabant/pkg/clouds"
	"github.com/project-spencer/trabant/pkg/model"
)

//go:embed stress.Dockerfile
var stressDockerfile []byte

func handleReq(w http.ResponseWriter, r *http.Request, functionName string, inputDir string, outputDir string, fnInputDir string, fnOutputDir string, tfEndpoint string) {

	reqStartT := time.Now()

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

	log.Printf("decoded image in %s", t2.Sub(t1))
	log.Printf("received image at t=%d, lat=%f, lon=%f, alt=%f, bands=%d", img.T, img.Lat, img.Lon, img.Alt, len(img.I))

	// perform cloud detection
	t3 := time.Now()

	// more efficient CLD detection
	cloudCover := clouds.CLDCoverage(&img)

	log.Printf("cloud cover: %.2f", cloudCover)

	t4 := time.Now()

	// save each layer as a tiff
	dirname := fmt.Sprintf("%d", img.T)

	err = os.MkdirAll(path.Join(inputDir, dirname), 0755)

	if err != nil {
		log.Printf("could not create directory: %s", err.Error())
		return
	}

	var totalSize int64

	for b := range img.I {

		fname := fmt.Sprintf("%s.tiff", b)

		// save the image
		err := os.WriteFile(path.Join(inputDir, dirname, fname), img.I[b], 0644)

		if err != nil {
			log.Printf("could not write file: %s", err.Error())
			return
		}

		fileinfo, err := os.Stat(path.Join(inputDir, dirname, fname))

		if err != nil {
			log.Printf("could not stat file: %s", err.Error())
			return
		}

		totalSize += fileinfo.Size()

	}

	t5 := time.Now()

	log.Printf("cloud detection took %s, saving images took %s", t4.Sub(t3), t5.Sub(t4))

	log.Printf("saved images to %s", path.Join(inputDir, dirname))

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

	log.Printf("calling tf with %d", img.T)

	callStartT := time.Now()

	resp, err := http.DefaultClient.Do(req)

	if err != nil {
		log.Printf("could not call tf: %s", err.Error())
		return
	}

	resp.Body.Close()

	log.Printf("called tf with %d", img.T)

	watcher, err := fsnotify.NewWatcher()
	if err != nil {
		log.Fatal(err)
	}
	defer watcher.Close()

	// Add a path.
	err = watcher.Add(outputDir)
	if err != nil {
		log.Fatal(err)
	}
	defer watcher.Close()

	var callEndT time.Time
	var resultSize int64
	var found bool

	timeout := time.After(5 * time.Second)
	for !found {
		select {
		case <-timeout:
			log.Printf("timeout waiting for file")
			w.WriteHeader(http.StatusInternalServerError)
			return
		case err := <-watcher.Errors:
			log.Printf("error waiting for file: %s", err)
			w.WriteHeader(http.StatusInternalServerError)
			return
		case file, ok := <-watcher.Events:
			callEndT = time.Now()
			if !ok {
				log.Println("watch stopped")
				w.WriteHeader(http.StatusInternalServerError)
				return
			}

			if !file.Has(fsnotify.Create) {
				log.Printf("ignoring event %+v", file)
				continue
			}

			// log.Printf("found file %s, last modified %d, size %d bytes", file.Name, fileinfo.ModTime().UnixNano(), fileinfo.Size())

			// check that this is our output file
			// format should be "{function_name}-{img.T}"
			if file.Name != path.Join(outputDir, fmt.Sprintf("%s-%d", functionName, img.T)) {
				log.Printf("ignoring file %s", file.Name)
				continue
			}

			fileinfo, err := os.Stat(file.Name)

			if err != nil {
				log.Printf("could not stat file %s: %s", file.Name, err)
				w.WriteHeader(http.StatusInternalServerError)
				return
			}

			// yay, this is our file!
			// callEndT = fileinfo.ModTime()
			// mtime is not reliable enough (this is ok)
			// callEndT = time.Now()
			resultSize = fileinfo.Size()

			log.Printf("found file %s, last modified %d, size %d bytes", file.Name, fileinfo.ModTime().UnixNano(), fileinfo.Size())
			found = true
		}
	}

	reqEndT := time.Now()

	outData := struct {
		SetupTus   int64 `json:"setup_t_us"`
		ExecTus    int64 `json:"exec_t_us"`
		AfterTus   int64 `json:"after_t_us"`
		InputSize  int64 `json:"input_size"`
		OutputSize int64 `json:"output_size"`
	}{
		SetupTus:   callStartT.Sub(reqStartT).Microseconds(),
		ExecTus:    callEndT.Sub(callStartT).Microseconds(),
		AfterTus:   reqEndT.Sub(callEndT).Microseconds(),
		InputSize:  totalSize,
		OutputSize: resultSize,
	}

	outDataJSON, err := json.Marshal(outData)

	if err != nil {
		log.Printf("could not marshal json: %s", err.Error())
		return
	}

	w.Write(outDataJSON)

	log.Printf("reqStartT=%d, callStartT=%d, callEndT=%d, reqEndT=%d", reqStartT.UnixNano(), callStartT.UnixNano(), callEndT.UnixNano(), reqEndT.UnixNano())
	log.Printf("setup took %d us, exec took %d us, after took %d us", outData.SetupTus, outData.ExecTus, outData.AfterTus)
}

func main() {
	log.SetPrefix("[eval] ")
	log.SetFlags(log.Ldate | log.Ltime | log.Lmicroseconds | log.LstdFlags | log.Lshortfile | log.LUTC)

	var tfEndpoint string
	var port int
	var functionName string
	var inputDir string
	var outputDir string
	var fnInputDir string
	var fnOutputDir string
	var stress bool

	flag.StringVar(&tfEndpoint, "tf-endpoint", "", "endpoint of tfaas server")
	flag.IntVar(&port, "port", 0, "port to listen on")
	flag.StringVar(&functionName, "function-name", "", "name of the function to call")
	flag.StringVar(&inputDir, "input-dir", "", "input directory for images")
	flag.StringVar(&outputDir, "output-dir", "", "output directory for images")
	flag.StringVar(&fnInputDir, "fn-input-dir", "", "input directory for functions")
	flag.StringVar(&fnOutputDir, "fn-output-dir", "", "output directory for functions")
	flag.BoolVar(&stress, "stress", true, "whether to stress the CPU")

	flag.Parse()

	// make the input dir or delete it if it exists
	err := os.RemoveAll(inputDir)

	if err != nil {
		log.Fatalf("could not remove input directory: %s", err.Error())
	}

	err = os.MkdirAll(inputDir, 0755)

	if err != nil {
		log.Fatalf("could not create input directory: %s", err.Error())
	}

	// make the output dir or delete it if it exists
	err = os.RemoveAll(outputDir)

	if err != nil {
		log.Fatalf("could not remove output directory: %s", err.Error())
	}

	err = os.MkdirAll(outputDir, 0755)

	if err != nil {
		log.Fatalf("could not create output directory: %s", err.Error())
	}

	if stress {
		// spin up a worker to 100% on CPU 2
		log.Printf("building stress image")

		imageName := "stress-cpu2"
		cmd := exec.Command("docker", "build", "-f", "-", "-t", imageName, ".")
		cmd.Stdin = bytes.NewReader(stressDockerfile)
		cmd.Stdout = os.Stdout

		err = cmd.Run()

		if err != nil {
			log.Fatalf("could not build stress image: %s", err.Error())
		}

		log.Print("starting stress container")

		cmd = exec.Command("docker", "run", "-d", "--rm", "--cpuset-cpus", "2", imageName)

		out, err := cmd.CombinedOutput()

		if err != nil {
			log.Fatalf("could not start stress container: %s", err.Error())
		}

		container := strings.TrimSpace(string(out))
		log.Printf("started stress container %s", container)

		defer func() {
			log.Print("stopping stress container")
			cmd = exec.Command("docker", "stop", container)
			cmd.Stdout = os.Stdout

			err = cmd.Run()

			if err != nil {
				log.Fatalf("could not stop stress container: %s", err.Error())
			}
		}()
	}

	// start the server
	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		handleReq(w, r, functionName, inputDir, outputDir, fnInputDir, fnOutputDir, tfEndpoint)
	})

	log.Printf("listening on port %d", port)

	log.Fatal(http.ListenAndServe(fmt.Sprintf(":%d", port), nil))
}
