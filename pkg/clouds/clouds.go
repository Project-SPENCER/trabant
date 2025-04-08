package clouds

import (
	"bytes"
	"image"
	"log"

	"github.com/project-spencer/trabant/pkg/model"
	"golang.org/x/image/tiff"
)

const tau = 0.2

// based on the Braaten-Cohen-Yang cloud detection algorithm
// https://custom-scripts.sentinel-hub.com/sentinel-2/cby_cloud_detection/
func BCYCoverage(img *model.Acquisition) float64 {
	// basically, the following must hold for a pixel to be a cloud:
	// B11 > tau (tau may be 0.2) AND ((B03 > 0.175 AND	NDGR > 0) OR B03 > 0.39)
	// NGDR = (B03 - B04) / (B03 + B04)
	// fairly simple

	tCount := 0

	log.Printf("got %d bytes for band b11", len(img.I[model.B11]))
	b11, err := tiff.Decode(bytes.NewReader(img.I[model.B11]))

	if err != nil {
		log.Fatalf("could not decode B11: %s", err)
	}

	b11G, ok := b11.(*image.Gray)

	if !ok {
		log.Fatalf("could not convert B11 to grayscale")
	}

	log.Printf("got %d bytes for band b03", len(img.I[model.B03]))
	b03, err := tiff.Decode(bytes.NewReader(img.I[model.B03]))

	if err != nil {
		log.Fatalf("could not decode B03: %s", err)
	}

	b03G, ok := b03.(*image.Gray)

	if !ok {
		log.Fatalf("could not convert B03 to grayscale")
	}

	log.Printf("got %d bytes for band b04", len(img.I[model.B04]))
	b04, err := tiff.Decode(bytes.NewReader(img.I[model.B04]))

	if err != nil {
		log.Fatalf("could not decode B04: %s", err)
	}

	b04G, ok := b04.(*image.Gray)

	if !ok {
		log.Fatalf("could not convert B04 to grayscale")
	}

	for p := 0; p < len(b11G.Pix); p++ {
		// check the first condition
		if float64(b11G.Pix[p])/255 <= tau {
			continue
		}

		// check the second condition
		if float64(b03G.Pix[p])/255 > 0.39 {
			tCount++
			continue
		}

		// check the third condition
		NGDR := (float64(b03G.Pix[p]) - float64(b04G.Pix[p])/(float64(b03G.Pix[p])+float64(b04G.Pix[p])))

		if float64(b03G.Pix[p])/255 > 0.175 && NGDR > 0 {
			tCount++
		}
	}

	return float64(tCount) / float64(len(b11G.Pix))
}

func CLDCoverage(img *model.Acquisition) float64 {
	cldImg, err := tiff.Decode(bytes.NewReader(img.I[model.CLD]))

	if err != nil {
		log.Fatalf("could not decode B11: %s", err)
	}

	cldImgG, ok := cldImg.(*image.Gray)

	if !ok {
		log.Fatalf("could not convert B11 to grayscale")
	}

	truePercentage := 0.0
	for p := 0; p < len(cldImgG.Pix); p++ {
		c := float64(cldImgG.Pix[p]) / 100

		if c > 1.0 {
			c = 1.0
		}
		if c < 0.0 {
			c = 0.0
		}

		truePercentage += c
	}

	return float64(truePercentage) / float64(len(cldImgG.Pix))
}

func Coverage(img *model.Acquisition) float64 {
	bcy := BCYCoverage(img)

	log.Printf("bcy coverage: %f", bcy)

	if _, ok := img.I[model.CLD]; ok {
		// there is a CLD band as well!
		cld := CLDCoverage(img)

		log.Printf("cld coverage %f", cld)
	}

	return bcy
}
