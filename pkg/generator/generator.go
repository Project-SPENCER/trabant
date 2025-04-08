package generator

import (
	"log"
	"math/rand"

	"github.com/project-spencer/trabant/pkg/model"
)

const (
	// NORAD 55261
	TLE1        = "OBJECT P                "
	TLE2        = "1 55261U 23007P   24226.81623355  .00195180  00000+0  16111-2 0  9995"
	TLE3        = "2 55261  97.3038 308.3155 0002852   1.3554 358.7716 15.69722089 88777"
	a           = 6378.1370        // semi-major axis in km
	e2          = 6.69437999014e-3 // first eccentricity squared
	random_seed = 42
)

type Generator struct {
	r *rand.Rand

	m               *model.Model
	acquisitionChan <-chan model.Acquisition
}

func New(m *model.Model) (*Generator, error) {

	log.Print("starting generator")

	currLat, currLon, currAlt := m.GetLoc()

	log.Printf("current satellite position: lat=%f, lon=%f, alt=%f", currLat, currLon, currAlt)

	acquisitionChan := m.GetAcquisitionChan()

	return &Generator{
		r:               rand.New(rand.NewSource(random_seed)),
		m:               m,
		acquisitionChan: acquisitionChan,
	}, nil
}

func (g *Generator) GetAcquisition() *model.Acquisition {
	a, ok := <-g.acquisitionChan

	if !ok {
		log.Fatal("acquisition channel closed")
	}

	return &a
}
