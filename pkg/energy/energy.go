package energy

import (
	_ "embed"
	"log"
	"time"

	"github.com/project-spencer/trabant/pkg/model"
)

type battery struct {
	chargemWh    float64
	maxChargemWh float64
	minChargemWh float64

	m *model.Model

	outgoingW func() float64

	bitrateBitps     int
	commPowermWspBit float64

	lastUpdate time.Time
}

func NewBattery(maxChargemWh int, minChargemWh int, currChargemWh float64, outgoingW func() float64, m *model.Model, bitrateBitps int, commPowermWspBit float64) *battery {

	return &battery{
		chargemWh:        currChargemWh,
		maxChargemWh:     float64(maxChargemWh),
		minChargemWh:     float64(minChargemWh),
		m:                m,
		outgoingW:        outgoingW,
		bitrateBitps:     bitrateBitps,
		commPowermWspBit: commPowermWspBit,
		lastUpdate:       m.GetTime(),
	}
}

func (b *battery) getCommsPowerWh(d time.Duration) float64 {
	elev := b.m.GetElev()
	log.Printf("elev: %f deg, downlink queue size %d bytes", elev, b.m.D.GetQueueSize())

	// no contact to ground station below 15deg
	if elev < 15.0 {
		return 0
	}

	// get the outstanding data
	// simulate transferring some data
	// calculate how much power that takes
	possiblyReadBytes := uint64(float64(b.bitrateBitps) * d.Seconds() / 8)

	readBytes := b.m.D.ReadNBytes(possiblyReadBytes)

	// mWspBit * bytes
	// 1/1000 WspBit * bytes
	// 1/1000 WspBit * 8*bit
	// 1/1000 * 1/36000 WhpBit * 8*bit

	log.Printf("read %d bytes", readBytes)
	// log.Print(float64(readBytes) / 1000 * 8)
	// log.Print(float64(readBytes) / 1000 * 8 * b.commPowermWspBit / 3600)
	return float64(readBytes) / 1000 * 8 * b.commPowermWspBit / 3600
}

func wattAndDurationToWh(watt float64, d time.Duration) float64 {
	return watt * d.Seconds() / 3600
}

func wHTomilliWattH(watt float64) float64 {
	return watt * 1e3
}

func (b *battery) Update() {
	// get the outgoing power
	outgoingPowerW := b.outgoingW()

	now := b.m.GetTime()
	elapsed := now.Sub(b.lastUpdate)
	b.lastUpdate = now

	// get the solar power
	solarPowerW := float64(b.m.GetSolarPowerW())

	// get the sat power
	satPowerW := float64(b.m.GetSatPowerW())

	// get the comms power
	commsPowermWh := wHTomilliWattH(b.getCommsPowerWh(elapsed))

	// update the charge
	b.chargemWh += wHTomilliWattH(wattAndDurationToWh((solarPowerW - satPowerW - outgoingPowerW), elapsed))

	b.chargemWh -= commsPowermWh

	if b.chargemWh >= b.maxChargemWh {
		b.chargemWh = b.maxChargemWh
	}

	if b.chargemWh <= b.minChargemWh {
		b.chargemWh = b.minChargemWh
	}

	log.Printf("solar: %fmWh, outgoing (sat): %fmWh, outgoing (RPi): %fmWh, outgoing (comms): %fmWh charge: %fmWh (%f%%) elapsed: %dus", wHTomilliWattH(wattAndDurationToWh(solarPowerW, elapsed)), wHTomilliWattH(wattAndDurationToWh(satPowerW, elapsed)), wHTomilliWattH(wattAndDurationToWh(outgoingPowerW, elapsed)), commsPowermWh, b.chargemWh, b.ChargePercent(), elapsed.Microseconds())
}

func (b *battery) ChargePercent() float64 {
	return b.chargemWh / b.maxChargemWh * 100
}
