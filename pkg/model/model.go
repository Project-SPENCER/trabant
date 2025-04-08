package model

import (
	"archive/zip"
	"bytes"
	_ "embed"
	"encoding/csv"
	"fmt"
	"io"
	"log"
	"os"
	"path"
	"strconv"
	"time"

	"github.com/project-spencer/trabant/pkg/downlink"
)

//go:embed bupt_energy.csv
var buptEnergyData []byte

//go:embed bupt_trajectory.csv
var buptTrajectoryData []byte

//go:embed image_log_with_alt.csv
var imageLogData []byte

type energy struct {
	solarEnergyW float32
	satEnergyW   float32
}

type trajectory struct {
	lat  float32
	lon  float32
	alt  float32
	elev float32
}

type Acquisition struct {
	T      uint64
	I      map[Band][]byte
	Lat    float64
	Lon    float64
	Alt    float64
	Sunlit bool
}

type Model struct {
	offset          time.Duration
	startTime       time.Time
	energyTrace     []energy
	trajectoryTrace []trajectory
	imagesDir       string
	D               *downlink.Downlink
}

func readEnergyTrace() []energy {
	// load the data
	// time_s,solar_harvested_energy_w,total_energy_w
	c := csv.NewReader(bytes.NewReader(buptEnergyData))

	records, err := c.ReadAll()

	if err != nil {
		panic(err)
	}

	e := make([]energy, len(records)-1)

	for _, record := range records[1:] {
		timeS, err := strconv.ParseInt(record[0], 10, 64)
		if err != nil {
			panic(err)
		}

		solarW, err := strconv.ParseFloat(record[1], 64)
		if err != nil {
			panic(err)
		}

		satW, err := strconv.ParseFloat(record[2], 64)
		if err != nil {
			panic(err)
		}

		e[timeS] = energy{
			solarEnergyW: float32(solarW),
			satEnergyW:   float32(satW),
		}
	}

	return e
}

func (m *Model) GetSolarPowerW() float32 {
	// based on the csv trace

	t := m.traceIndexS() % int64(len(m.energyTrace))
	// log.Printf("trace index: %d", m.traceIndexS())

	return m.energyTrace[t].solarEnergyW
}

func (m *Model) GetSatPowerW() float32 {
	// based on the csv trace

	t := m.traceIndexS() % int64(len(m.energyTrace))

	return m.energyTrace[t].satEnergyW
}

// need to have tenth of a second as a unit
func msToTraceIndex(ms int64) int64 {
	return ms / 1e2
}

func readTrajectoryTrace() []trajectory {
	// load the data
	// time_ms,lat,lon,alt_km,elev_deg
	c := csv.NewReader(bytes.NewReader(buptTrajectoryData))

	records, err := c.ReadAll()

	if err != nil {
		panic(err)
	}

	t := make([]trajectory, len(records)-1)

	for _, record := range records[1:] {
		timeMS, err := strconv.ParseInt(record[0], 10, 64)
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

		elev := 0.0
		if record[4] != "" {
			elev, err = strconv.ParseFloat(record[4], 64)
			if err != nil {
				panic(err)
			}
		}

		t[msToTraceIndex(timeMS)] = trajectory{
			lat:  float32(lat),
			lon:  float32(lon),
			alt:  float32(alt),
			elev: float32(elev),
		}

	}

	return t
}

func readAcqusitionLog() []Acquisition {
	// load the data
	// time_ms,lon,lat,alt,sunlit
	c := csv.NewReader(bytes.NewReader(imageLogData))

	records, err := c.ReadAll()

	if err != nil {
		panic(err)
	}

	img := make([]Acquisition, len(records)-1)

	for i, record := range records[1:] {
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

		sunlit, err := strconv.ParseBool(record[4])
		if err != nil {
			panic(err)
		}

		img[i] = Acquisition{
			T:      uint64(timeMs),
			Lat:    lat,
			Lon:    lon,
			Alt:    alt,
			Sunlit: sunlit,
		}
	}

	return img
}

func (m *Model) GetLoc() (float32, float32, float32) {
	// based on the csv trace

	t := msToTraceIndex(m.traceIndexMS()) % int64(len(m.trajectoryTrace))

	return m.trajectoryTrace[t].lat, m.trajectoryTrace[t].lon, m.trajectoryTrace[t].alt
}

func (m *Model) GetElev() float32 {
	// based on the csv trace

	// log.Printf("traj trace index: %d", msToTraceIndex(m.traceIndexMS()))
	t := msToTraceIndex(m.traceIndexMS()) % int64(len(m.trajectoryTrace))

	return m.trajectoryTrace[t].elev
}

func (m *Model) traceIndexS() int64 {
	return m.traceIndexMS() / 1000
}

func (m *Model) traceIndexMS() int64 {
	return m.GetTime().Sub(m.startTime).Milliseconds()
}

func (m *Model) GetTime() time.Time {
	return time.Now().Add(m.offset)
}

func (m *Model) GetAcquisitionChan() <-chan Acquisition {
	c := make(chan Acquisition)

	startImage := uint64(m.GetTime().Sub(m.startTime).Milliseconds())

	go func() {
		aLog := readAcqusitionLog()

		// get the first index
		n := 0
		for i, a := range aLog {
			if a.T >= startImage {
				n = i
				break
			}
		}

		for ; ; n = (n + 1) % len(aLog) {
			a := aLog[n]

			if a.T < startImage {
				continue
			}

			img := make(map[Band][]byte)

			// open the zip file that has all the bands
			// zipFile, err := images.Open(fmt.Sprintf("images/%d.zip", a.T))
			zipFile, err := os.Open(path.Join(m.imagesDir, fmt.Sprintf("%d.zip", a.T)))

			if err != nil {
				log.Println(err)
				continue
			}

			info, err := zipFile.Stat()

			if err != nil {
				log.Println(err)
				continue
			}

			if info.IsDir() {
				log.Println("zip file is a directory")
				continue
			}

			zip, err := zip.NewReader(zipFile, info.Size())

			if err != nil {
				log.Println(err)
				continue
			}

			for _, f := range zip.File {
				if f.FileInfo().IsDir() {
					continue
				}

				// in the trace_dir, there is a subfolder named "i", which has more files named "i_B01.tiff", "i_B02.tiff", etc.
				// open this and read it into the image
				// i is a number
				band := Band(f.Name[len(f.Name)-3-len(".tiff") : len(f.Name)-len(".tiff")])

				// open the file
				b, err := f.Open()

				if err != nil {
					log.Println(err)
					continue
				}

				// read the file into the image
				// i, err := tiff.Decode(f)

				// if err != nil {
				// 	log.Println(err)
				// 	continue
				// }

				d, err := io.ReadAll(b)

				if err != nil {
					log.Println(err)
					continue
				}

				img[band] = d

				// log.Printf("putting %d bytes for band %s", len(d), band)

				b.Close()
			}

			a.I = img

			acquisitionDate := m.startTime.Add(time.Duration(a.T) * time.Millisecond)
			time.Sleep(acquisitionDate.Sub(m.GetTime()))

			// log.Printf("image at %d", a.T)
			c <- a
		}
	}()

	return c
}

func NewModel(startTime time.Time, startOffsetSec int, imagesDir string) *Model {
	e := readEnergyTrace()
	t := readTrajectoryTrace()

	offset := -time.Since(startTime) + time.Duration(startOffsetSec)*time.Second
	// startTime = time.Now().Add(offset)

	D := downlink.NewDownlink()

	return &Model{
		energyTrace:     e,
		trajectoryTrace: t,
		offset:          offset,
		startTime:       startTime,
		imagesDir:       imagesDir,
		D:               D,
	}
}
