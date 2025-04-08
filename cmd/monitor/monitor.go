package main

import (
	_ "embed"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"
	"time"

	"github.com/Tinkerforge/go-api-bindings/ipconnection"
	"github.com/Tinkerforge/go-api-bindings/lcd_128x64_bricklet"
	"github.com/Tinkerforge/go-api-bindings/temperature_ir_v2_bricklet"
	"github.com/Tinkerforge/go-api-bindings/voltage_current_v2_bricklet"
	"github.com/project-spencer/trabant/pkg/energy"
	"github.com/project-spencer/trabant/pkg/generator"
	"github.com/project-spencer/trabant/pkg/model"
)

const (
	updateInterval = 1 * time.Second

	tfHost                  = "localhost"
	tfPort                  = 4223
	tfVoltageUID            = "26vg"
	tfVoltageAveraging      = voltage_current_v2_bricklet.Averaging64
	tfVoltageConversionTime = voltage_current_v2_bricklet.ConversionTime8_244ms
	tfTempUID               = "TCq"
	tfLCDUID                = "24Q8"

	// initialChargePercent = 70
	maxChargemWh  = 575 * 100 // 115Wh * 2 / 4
	minChargemWh  = 0
	minDoDPercent = 70

	bitrateBitps = 80_000_000 // 80Mbps
	commPowerW   = 20         // 20W
)

var (
	tfEmissivity = 0.9 * 65535
)

func main() {

	log.SetPrefix("[monitor] ")
	log.SetFlags(log.Ldate | log.Ltime | log.Lmicroseconds | log.LstdFlags | log.Lshortfile | log.LUTC)

	var startTime int64
	var startOffsetSec int
	var listenPort int
	var imagesDir string
	var endpoint string
	var downlinkPort int
	var tempLimit int
	var initialChargePercent int

	flag.Int64Var(&startTime, "start-time", time.Now().Unix(), "start time for generator")
	flag.IntVar(&startOffsetSec, "start-offset-sec", 0, "start offset in seconds")
	flag.IntVar(&listenPort, "port", 8080, "port to listen on")
	flag.StringVar(&imagesDir, "images-dir", "", "directory to store images")
	flag.StringVar(&endpoint, "endpoint", "", "upload endpoint")
	flag.IntVar(&downlinkPort, "downlink-port", 8081, "downlink port")
	flag.IntVar(&tempLimit, "temp-limit", 60, "temperature limit")
	flag.IntVar(&initialChargePercent, "initial-charge-percent", 70, "initial charge percent")

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

	ipcon.Connect(fmt.Sprint(tfHost, ":", tfPort))
	defer ipcon.Disconnect()

	log.Print("connected to Tinkerforge devices")

	err = vc.SetConfiguration(tfVoltageAveraging, tfVoltageConversionTime, tfVoltageConversionTime)

	if err != nil {
		log.Fatalf("could not set configuration: %v", err)
	}

	model := model.NewModel(time.Unix(startTime, 0), startOffsetSec, imagesDir)

	model.D.Start(downlinkPort)

	log.Print("model started")

	// TODO: confirm this is the correct calculation
	commPowermWspBit := (float64(commPowerW) * 1000 / float64(bitrateBitps))
	log.Printf("comm power per bit: %fmWs/bit, derived from comm power %d W and bit rate %d bit/s", commPowermWspBit, commPowerW, bitrateBitps)

	b := energy.NewBattery(maxChargemWh, minChargemWh, (float64(initialChargePercent)/100.0)*maxChargemWh, func() float64 {
		v, err := vc.GetPower()
		if err != nil {
			log.Printf("Failed to get power: %v", err)
			return 0
		}
		return float64(v) / 1000
	}, model, bitrateBitps, commPowermWspBit)

	go func() {
		for {
			b.Update()
			time.Sleep(updateInterval)
		}
	}()

	log.Print("battery monitor started")

	tmp, err := temperature_ir_v2_bricklet.New(tfTempUID, &ipcon)

	if err != nil {
		log.Fatalf("Failed to create TemperatureIRV2Bricklet: %v", err)
	}

	tmp.SetEmissivity(uint16(tfEmissivity))

	var sentframes uint64

	// display updates
	go func() {
		lcd, err := lcd_128x64_bricklet.New(tfLCDUID, &ipcon)

		if err != nil {
			log.Fatalf("Failed to create LCD128x64Bricklet: %v", err)
		}

		t := time.NewTicker(1 * time.Second)
		s := time.Now()
		for {
			objTemp, err := tmp.GetObjectTemperature()

			if err != nil {
				log.Printf("Failed to get object temperature: %v", err)
				objTemp = 0
			}

			ambientTemp, err := tmp.GetAmbientTemperature()

			if err != nil {
				log.Printf("Failed to get ambient temperature: %v", err)
				ambientTemp = 0
			}

			power, err := vc.GetPower()

			if err != nil {
				log.Printf("Failed to get power: %v", err)
				power = 0
			}

			// lcd.ClearDisplay()
			lcd.WriteLine(0, 0, fmt.Sprintf("%-10s%10.2f%%", "Charge:", b.ChargePercent()))
			lcd.WriteLine(1, 0, fmt.Sprintf("%-10s%10.2fC", "Ambient:", float64(ambientTemp)/10))
			lcd.WriteLine(2, 0, fmt.Sprintf("%-10s%10.2fC", "Temp:", float64(objTemp)/10))
			lcd.WriteLine(3, 0, fmt.Sprintf("%-10s%10.2fW", "Power:", float64(power)/1000))
			lcd.WriteLine(4, 0, fmt.Sprintf("%-10s%10.2fs", "T:", time.Since(s).Seconds()))
			lcd.WriteLine(5, 0, fmt.Sprintf("%-10s%10d", "Frames:", sentframes))
			<-t.C
		}
	}()

	log.Print("display started")

	g, err := generator.New(model)

	if err != nil {
		log.Fatalf("could not create generator: %v", err)
	}

	go func() {
		for {
			img := g.GetAcquisition()
			log.Printf("generated image at lat=%f, lon=%f, alt=%f", img.Lat, img.Lon, img.Alt)

			err := generator.MakeReq(img, endpoint)

			if err != nil {
				log.Printf("could not send image: %v", err)
			}

			sentframes++
		}
	}()

	log.Print("generator started")

	getTemp := func() float64 {
		objTemp, err := tmp.GetObjectTemperature()

		if err != nil {
			log.Printf("Failed to get object temperature: %v", err)
			objTemp = 0
		}

		temp := float64(objTemp) / 10

		// log.Printf("current temp: %f", temp)
		return temp
	}

	go func() {
		for {
			log.Printf("current temp: %f", getTemp())
			time.Sleep(1 * time.Second)
		}
	}()

	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		idle := b.ChargePercent() > minDoDPercent && getTemp() < float64(tempLimit)
		v, err := json.Marshal(idle)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.Write(v)
	})

	log.Println("starting HTTP server")
	err = http.ListenAndServe(fmt.Sprintf(":%d", listenPort), mux)
	if err != nil {
		log.Fatal(err)
	}
}
