package main

import (
	"archive/zip"
	"bytes"
	"embed"
	"encoding/base64"
	"encoding/json"
	"flag"
	"io/fs"
	"log"
	"net/http"
	"path"
	"time"

	"github.com/project-spencer/trabant/pkg/util"
)

const dirname = "compiledfns"

//go:embed all:compiledfns
var fns embed.FS

func main() {
	log.SetPrefix("[upload] ")
	log.SetFlags(log.Ldate | log.Ltime | log.Lmicroseconds | log.LstdFlags | log.Lshortfile | log.LUTC)

	var uploadEndpoint string
	var fnName string
	var inputDirFn string
	var outputDirFn string
	var inputDirHost string
	var outputDirHost string
	var threads int
	var environment string
	var timeout int

	flag.StringVar(&uploadEndpoint, "upload-endpoint", "", "upload endpoint")
	flag.StringVar(&fnName, "function", "", "function name to upload")
	flag.StringVar(&inputDirFn, "input-dir-fn", "", "internal input directory")
	flag.StringVar(&outputDirFn, "output-dir-fn", "", "internal output directory")
	flag.StringVar(&inputDirHost, "input-dir-host", "", "host input directory")
	flag.StringVar(&outputDirHost, "output-dir-host", "", "host output directory")
	flag.IntVar(&threads, "threads", 2, "number of threads")
	flag.StringVar(&environment, "env", "tflite", "environment")
	flag.IntVar(&timeout, "timeout", 60, "timeout in seconds")

	flag.Parse()

	if fnName == "" {
		log.Fatalf("function name is required")
	}

	funcs, err := fns.ReadDir(dirname)

	if err != nil {
		log.Fatalf("could not read compiled functions directory: %s", err)
	}

	var fn fs.DirEntry

	for _, fn = range funcs {
		if fn.Name() == fnName {
			break
		}
	}

	if fn == nil {
		log.Fatalf("function %s not found", fnName)
	}

	// check that fn is a directory
	if !fn.IsDir() {
		log.Fatalf("function %s is not a directory", fn.Name())
	}

	log.Printf("deploying function %s", fn.Name())

	// create a zip file for the function
	// zip -r - ./*
	buf := new(bytes.Buffer)
	w := zip.NewWriter(buf)

	// add files to the zip
	err = util.ZipFolder(fns, path.Join(dirname, fn.Name()), w)

	if err != nil {
		log.Fatalf("could not add files to zip: %s", err)
	}
	err = w.Close()

	if err != nil {
		log.Fatalf("could not close zip file: %s", err)
	}

	// base64 convert
	dst := make([]byte, base64.StdEncoding.EncodedLen(len(buf.Bytes())))
	base64.StdEncoding.Encode(dst, buf.Bytes())

	// deploy function
	// curl http://localhost:8080/upload --data "{\"name\": \"$2\", \"env\": \"$3\", \"threads\": $4, \"zip\": \"$(zip -r - ./* | base64 | tr -d '\n')\"}"

	upload := struct {
		Name    string `json:"name"`
		Env     string `json:"env"`
		Threads int    `json:"threads"`
		Zip     string `json:"zip"`
		Mounts  []struct {
			Dir    string `json:"mount_dir"`
			Target string `json:"mount_target"`
			Rw     bool   `json:"mount_rw"`
		} `json:"mounts"`
	}{
		Name:    fn.Name(),
		Env:     environment,
		Threads: threads,
		Zip:     string(dst),
		Mounts: []struct {
			Dir    string `json:"mount_dir"`
			Target string `json:"mount_target"`
			Rw     bool   `json:"mount_rw"`
		}{
			{
				Dir:    inputDirHost,
				Target: inputDirFn,
				Rw:     false,
			},
			{
				Dir:    outputDirHost,
				Target: outputDirFn,
				Rw:     true,
			},
		},
	}

	u, err := json.Marshal(upload)

	if err != nil {
		log.Fatalf("could not marshal upload: %s", err)
	}

	// wait for tfaas to be available
	for i := 0; i < timeout; i++ {
		_, err = http.Get(uploadEndpoint)

		if err == nil {
			break
		}

		log.Printf("could not connect to tfaas: %s (try %d/%d)", err, i+1, timeout)

		// wait 1 seconds
		<-time.After(1 * time.Second)
	}

	log.Print("connected to tfaas, uploading function...")

	t := time.Now()

	_, err = http.Post(uploadEndpoint, "application/json", bytes.NewReader(u))

	if err != nil {
		log.Fatalf("could not deploy function %s: %s", fn.Name(), err)
	}

	log.Printf("deployed function %s, took %s", fn.Name(), time.Since(t))
}
