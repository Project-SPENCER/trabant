package main

import (
	"archive/zip"
	"bytes"
	_ "embed"
	"encoding/csv"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"math/rand"
	"net/http"
	"os"
	"path"
	"strconv"
	"time"

	"github.com/Tinkerforge/go-api-bindings/ipconnection"
	"github.com/Tinkerforge/go-api-bindings/voltage_current_v2_bricklet"
	"github.com/project-spencer/trabant/pkg/clouds"
	"github.com/project-spencer/trabant/pkg/model"
)

const (
	tfHost                  = "localhost"
	tfPort                  = 4223
	tfVoltageUID            = "26vg"
	tfVoltageAveraging      = voltage_current_v2_bricklet.Averaging4
	tfVoltageConversionTime = voltage_current_v2_bricklet.ConversionTime204us
	tfLatency               = 0 * time.Millisecond // 300 * time.Millisecond

	measurementRateHz = 20
)

//go:embed image_log_with_alt.csv
var imageLogData []byte

type call struct {
	t          time.Duration
	inputSize  int64
	outputSize int64
	startT     time.Time
	endT       time.Time
	execStartT time.Time
	execEndT   time.Time
}

func readAcqusitionLog() []model.Acquisition {
	// load the data
	// time_ms,lon,lat,alt,sunlit
	c := csv.NewReader(bytes.NewReader(imageLogData))

	records, err := c.ReadAll()

	if err != nil {
		panic(err)
	}

	img := make([]model.Acquisition, 0)

	for _, record := range records[1:] {
		sunlit, err := strconv.ParseBool(record[4])
		if err != nil {
			panic(err)
		}

		if !sunlit {
			continue
		}

		timeMs, err := strconv.ParseInt(record[0], 10, 64)
		if err != nil {
			panic(err)
		}

		lat, err := strconv.ParseFloat(record[1], 64)
		if err != nil {
			panic(err)
		}

		lon, err := strconv.ParseFloat(record[2], 64)
		if err != nil {
			panic(err)
		}

		alt, err := strconv.ParseFloat(record[3], 64)
		if err != nil {
			panic(err)
		}

		img = append(img, model.Acquisition{
			T:      uint64(timeMs),
			Lat:    lat,
			Lon:    lon,
			Alt:    alt,
			Sunlit: sunlit,
		})
	}

	return img
}

func getAcquisition(rng *rand.Rand, acquisitions []model.Acquisition, imagesDir string) model.Acquisition {

	var acq *model.Acquisition

	for acq == nil {

		_acq := acquisitions[rng.Intn(len(acquisitions))]
		// remove the first element

		log.Printf("testing acquisition: %d", _acq.T)

		// read the image
		img := make(map[model.Band][]byte)
		zipFile, err := os.Open(path.Join(imagesDir, fmt.Sprintf("%d.zip", _acq.T)))

		if err != nil {
			log.Printf("could not open zip file: %v", err)
			continue
		}

		info, err := zipFile.Stat()

		if err != nil {
			log.Printf("could not stat zip file: %v", err)
			continue
		}

		if info.IsDir() {
			log.Printf("zip file %s is a directory", zipFile.Name())
			continue
		}

		zip, err := zip.NewReader(zipFile, info.Size())

		if err != nil {
			log.Printf("could not open zip file: %v", err)
			continue
		}

		for _, f := range zip.File {
			if f.FileInfo().IsDir() {
				continue
			}

			band := model.Band(f.Name[len(f.Name)-3-len(".tiff") : len(f.Name)-len(".tiff")])

			b, err := f.Open()

			if err != nil {
				log.Printf("could not open image: %v", err)
				continue
			}

			d, err := io.ReadAll(b)

			if err != nil {
				log.Printf("could not read image: %v", err)
				continue
			}

			img[band] = d

			b.Close()
		}

		_acq.I = img

		// check the cloud cover
		cloudCover := clouds.CLDCoverage(&_acq)
		log.Printf("cloud cover: %.2f", cloudCover)

		if cloudCover > 0.3 {
			log.Printf("cloud cover too high: %.2f", cloudCover)
			// _acq.I = nil
			continue
		}

		acq = &_acq
	}

	return *acq
}

func sendAndMeasure(acquisitions []model.Acquisition, rng *rand.Rand, imagesDir string, endpoint string) (call, error) {

	acq := getAcquisition(rng, acquisitions, imagesDir)
	// defer func() {
	// acq.I = nil // clear the image
	// }()

	var b bytes.Buffer

	err := acq.Encode(&b)

	if err != nil {
		return call{}, fmt.Errorf("could not encode image: %v", err)
	}

	req, err := http.NewRequest("POST", endpoint, &b)

	req.Header.Set("Content-Type", "application/octet-stream")

	if err != nil {
		return call{}, fmt.Errorf("could not create request: %v", err)
	}

	// now that we've read the image, we can finally send it
	startT := time.Now()
	resp, err := http.DefaultClient.Do(req)
	endT := time.Now()

	if err != nil {
		return call{}, fmt.Errorf("could not send image: %v", err)
	}

	if resp.StatusCode != http.StatusOK {
		return call{}, fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}

	var outData struct {
		SetupTus   int64 `json:"setup_t_us"`
		ExecTus    int64 `json:"exec_t_us"`
		AfterTus   int64 `json:"after_t_us"`
		InputSize  int64 `json:"input_size"`
		OutputSize int64 `json:"output_size"`
	}

	// read the response from json
	err = json.NewDecoder(resp.Body).Decode(&outData)

	if err != nil {
		return call{}, fmt.Errorf("could not decode response: %v", err)
	}

	// get the measurement logs and total up energy
	// sort the log first
	// then sum up energy by multiplying the power by the time difference
	// and don't use the first setupns and last aftertns
	// also, convert the power to watts (Watt seconds = Joules)

	// log.Printf("setup time %d us", outData.SetupTus)

	remoteT := time.Duration(outData.SetupTus+outData.ExecTus+outData.AfterTus) * time.Microsecond
	// log.Printf("remote time %d us", remoteT.Microseconds())
	localT := endT.Sub(startT)
	// log.Printf("local time %d us", localT.Microseconds())

	offset := (localT - remoteT) / 2

	// log.Printf("offset %d us", offset.Microseconds())

	start := startT.Add(time.Duration(outData.SetupTus) * time.Microsecond).Add(offset)
	end := start.Add(time.Duration(outData.ExecTus) * time.Microsecond)

	return call{
		t:          time.Duration(outData.ExecTus) * time.Microsecond,
		inputSize:  outData.InputSize,
		outputSize: outData.OutputSize,
		execStartT: start,
		execEndT:   end,
		startT:     startT,
		endT:       endT,
	}, nil
}

func main() {

	log.SetPrefix("[measure] ")
	log.SetFlags(log.Ldate | log.Ltime | log.Lmicroseconds | log.LstdFlags | log.Lshortfile | log.LUTC)

	var imagesDir string
	var endpoint string
	var intervalS int
	var rngSeed int
	var baselineLength int
	var N int

	flag.StringVar(&imagesDir, "images-dir", "", "directory to store images")
	flag.StringVar(&endpoint, "endpoint", "", "upload endpoint")
	flag.IntVar(&intervalS, "interval", 2, "interval between measurements in seconds")
	flag.IntVar(&baselineLength, "baseline-length", 10, "length of baseline measurement in seconds")
	flag.IntVar(&N, "N", 10, "number of measurements")
	flag.IntVar(&rngSeed, "rng-seed", 0, "seed for random number generator")

	flag.Parse()

	log.Print("starting")

	ipcon := ipconnection.New()
	defer ipcon.Close()

	log.Print("created IP connection")

	vc, err := voltage_current_v2_bricklet.New(tfVoltageUID, &ipcon)

	if err != nil {
		log.Fatalf("Failed to create VoltageCurrentV2Bricklet: %v", err)
	}

	log.Print("created VoltageCurrentV2Bricklet")

	err = ipcon.Connect(fmt.Sprint(tfHost, ":", tfPort))

	if err != nil {
		log.Fatalf("could not connect to Tinkerforge devices: %v", err)
	}

	defer ipcon.Disconnect()

	log.Print("connected to Tinkerforge devices")

	err = vc.SetConfiguration(tfVoltageAveraging, tfVoltageConversionTime, tfVoltageConversionTime)

	if err != nil {
		log.Fatalf("could not set configuration: %v", err)
	}

	p, err := vc.GetPower()

	if err != nil {
		log.Fatalf("could not get power: %v", err)
	}

	log.Printf("test: %v", p)

	// wait for service to be available
	for i := 0; i < 60; i++ {
		_, err = http.Get(endpoint)

		if err == nil {
			break
		}

		log.Printf("could not connect to service: %s (try %d)", err, i+1)

		// wait 1 seconds
		<-time.After(1 * time.Second)
	}

	// get the baseline
	log.Print("getting baseline power")

	r := vc.RegisterPowerCallback(func(power int32) {
		log.Printf("power: %s %d", time.Now().Add(-tfLatency), power)
	})

	vc.SetPowerCallbackConfiguration(uint32(1000/measurementRateHz), false, 'x', 0, 0)

	defer vc.DeregisterCurrentCallback(r)

	startT := time.Now()
	time.Sleep(time.Duration(baselineLength) * time.Second)
	endT := time.Now()

	log.Printf("baseline startT: %s", startT)
	log.Printf("baseline endT: %s", endT)
	log.Printf("baseline duration: %d us", endT.Sub(startT).Microseconds())

	acquisitions := readAcqusitionLog()

	rng := rand.New(rand.NewSource(int64(rngSeed)))

	// shuffle the acquisitions
	// rng.Shuffle(len(acquisitions), func(i, j int) {
	// 	acquisitions[i], acquisitions[j] = acquisitions[j], acquisitions[i]
	// })

	for i := 0; i < N; i++ {
		c, err := sendAndMeasure(acquisitions, rng, imagesDir, endpoint)

		if err != nil {
			log.Printf("(%d/%d) could not send and measure: %v", i, N, err)
			// i--
			continue
		}

		log.Printf("(%d/%d) duration: %d us", i, N, c.t.Microseconds())
		log.Printf("(%d/%d) input size: %d bytes", i, N, c.inputSize)
		log.Printf("(%d/%d) output size: %d bytes", i, N, c.outputSize)
		log.Printf("(%d/%d) start: %s", i, N, c.execStartT)
		log.Printf("(%d/%d) end: %s", i, N, c.execEndT)
		log.Printf("(%d/%d) startT: %s", i, N, c.startT)
		log.Printf("(%d/%d) endT: %s", i, N, c.endT)

		time.Sleep(time.Duration(intervalS) * time.Second)
	}

	log.Print("done")
}
