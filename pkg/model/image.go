package model

import (
	"encoding/gob"
	"image"
	"image/color"
	"io"
)

type Band string

const (
	B01 Band = "B01"
	B02 Band = "B02"
	B03 Band = "B03"
	B04 Band = "B04"
	B05 Band = "B05"
	B06 Band = "B06"
	B07 Band = "B07"
	B08 Band = "B08"
	B8A Band = "B8A"
	B09 Band = "B09"
	B11 Band = "B11"
	B12 Band = "B12"
	CLD Band = "CLD"
)

// var bands = []Band{B01, B02, B03, B04, B05, B06, B07, B08, B8A, B09, B11, B12}

type Image struct {
	X   int
	Y   int
	Pix []uint8
}

func (i *Image) At(x, y int) uint8 {
	return i.Pix[y*i.X+x]
}

func FromImage(i image.Image) *Image {
	b := i.Bounds()
	img := Image{
		X:   b.Dx(),
		Y:   b.Dy(),
		Pix: make([]uint8, b.Dx()*b.Dy()),
	}

	if _, ok := i.(*image.Gray); !ok {
		img.Pix = i.(*image.Gray).Pix
		return &img
	}

	for y := 0; y < b.Dy(); y++ {
		for x := 0; x < b.Dx(); x++ {
			img.Pix[y*b.Dx()+x] = i.At(x, y).(color.Gray).Y
		}
	}

	return &img
}

func ToImage(i *Image) image.Image {
	img := image.NewGray(image.Rect(0, 0, i.X, i.Y))
	img.Pix = i.Pix

	return img
}

func (a *Acquisition) Encode(w io.Writer) error {
	enc := gob.NewEncoder(w)
	return enc.Encode(a)
}

func (a *Acquisition) Decode(r io.Reader) error {
	dec := gob.NewDecoder(r)

	return dec.Decode(a)
}

// func (a *Acquisition) Encode(w io.Writer) error {
// 	// enc := gob.NewEncoder(w)
// 	// return enc.Encode(a)
// 	// trying custom encoding
// 	binary.Write(w, binary.LittleEndian, a.T)
// 	binary.Write(w, binary.LittleEndian, a.Lat)
// 	binary.Write(w, binary.LittleEndian, a.Lon)
// 	binary.Write(w, binary.LittleEndian, a.Alt)
// 	binary.Write(w, binary.LittleEndian, a.Sunlit)

// 	binary.Write(w, binary.LittleEndian, uint64(len(a.I)))

// 	for name, band := range a.I {
// 		binary.Write(w, binary.LittleEndian, uint64(len(name)))
// 		binary.Write(w, binary.LittleEndian, []byte(name))
// 		binary.Write(w, binary.LittleEndian, uint64(len(band)))
// 		binary.Write(w, binary.LittleEndian, band)
// 	}

// 	return nil
// }

// func (a *Acquisition) Decode(r io.Reader) error {
// 	// dec := gob.NewDecoder(r)
// 	// return dec.Decode(a)

// 	// trying custom decoding
// 	binary.Read(r, binary.LittleEndian, &a.T)
// 	binary.Read(r, binary.LittleEndian, &a.Lat)
// 	binary.Read(r, binary.LittleEndian, &a.Lon)
// 	binary.Read(r, binary.LittleEndian, &a.Alt)
// 	binary.Read(r, binary.LittleEndian, &a.Sunlit)

// 	var n uint64
// 	binary.Read(r, binary.LittleEndian, &n)

// 	a.I = make(map[Band][]byte)

// 	for i := uint64(0); i < n; i++ {
// 		var m uint64
// 		binary.Read(r, binary.LittleEndian, &m)
// 		name := make([]byte, m)
// 		binary.Read(r, binary.LittleEndian, name)
// 		binary.Read(r, binary.LittleEndian, &m)
// 		band := make([]byte, m)
// 		binary.Read(r, binary.LittleEndian, band)

// 		a.I[Band(name)] = band
// 	}

// 	return nil
// }
