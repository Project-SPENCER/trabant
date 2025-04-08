package main

import (
	"flag"
	"fmt"
	"log"
	"os"
	"path"
	"regexp"
	"strings"
	"time"

	"github.com/fsnotify/fsnotify"
	"github.com/project-spencer/trabant/pkg/downlink"
)

func checkFile(nameCheck *regexp.Regexp, fileName string, inputDir string, persistDir string, downlinkEndpoint string) error {
	// log.Println("event:", event)

	// check that this is our output file
	// format should be "{function_name}-{img.T}"
	if !strings.Contains(path.Base(fileName), "-") || !nameCheck.MatchString(path.Base(fileName)) {
		// log.Printf("ignoring file %s", file.Name)
		// continue
		return nil
	}

	fileinfo, err := os.Stat(fileName)

	if err != nil {
		return fmt.Errorf("could not stat file %s: %s", fileName, err)
	}

	log.Printf("found file %s, last modified %d, size %d bytes (t %s)", fileName, fileinfo.ModTime().UnixNano(), fileinfo.Size(), time.Now())

	// only send if the size is larger than 0
	if fileinfo.Size() != 0 {
		downlink.SendToRemote(fileName, uint64(fileinfo.Size()), downlinkEndpoint)
	}

	// remove file
	// done in the same routine to save some resources
	// doesn't matter for time measurement, since we go by mtime
	// actually we go by normal time but we don't measure any time
	err = os.Remove(fileName)

	if err != nil {
		log.Printf("could not remove file %s: %s", fileName, err)
	}

	// check if we can also remove the input file
	fns, err := os.ReadDir(persistDir)

	if err != nil {
		return fmt.Errorf("could not read directory %s: %s", inputDir, err)
	}

	p := strings.Split(path.Base(fileName), "-")

	id := p[len(p)-1]
	found := false
	for _, fn := range fns {
		if !fn.IsDir() {
			continue
		}

		// find out if the file /persistDir/fn.Name/id exists
		p := path.Join(persistDir, fn.Name(), id)
		_, err := os.Stat(p)
		log.Printf("checking for file %s: %v", p, err == nil)
		if err == nil {
			// it exists! so there is more to do
			found = true
			break
		}
	}

	if !found {
		log.Printf("all calls for id %s processed, removing input directory", id)

		// remove the input directory
		err = os.RemoveAll(path.Join(inputDir, id))

		if err != nil {
			log.Printf("could not remove directory %s: %s", path.Join(inputDir, id), err)
		}
	}

	return nil
}

func main() {
	log.SetPrefix("[post] ")
	log.SetFlags(log.Ldate | log.Ltime | log.Lmicroseconds | log.LstdFlags | log.Lshortfile | log.LUTC)

	var inputDir string
	var persistDir string
	var monitorDir string
	var downlinkEndpoint string
	var resume bool

	flag.StringVar(&inputDir, "input-dir", "", "directory where input images land")
	flag.StringVar(&persistDir, "persist-dir", "", "directory to persist fn calls")
	flag.StringVar(&monitorDir, "monitor-dir", "", "directory to monitor for images")
	flag.StringVar(&downlinkEndpoint, "downlink-endpoint", "", "endpoint to send image data to")
	flag.BoolVar(&resume, "resume", false, "resume from previous run")

	flag.Parse()

	nameCheck := regexp.MustCompile(`^\w*-\d+$`)

	if resume {
		// we first check existing files
		f, err := os.ReadDir(monitorDir)

		if err != nil {
			log.Fatalf("could not read directory %s: %s", monitorDir, err)
		}

		for _, file := range f {
			err := checkFile(nameCheck, file.Name(), inputDir, persistDir, downlinkEndpoint)
			if err != nil {
				log.Println("error checking file:", err)
			}
		}
	}

	log.Printf("monitoring directory %s", monitorDir)
	watcher, err := fsnotify.NewWatcher()
	if err != nil {
		log.Fatal(err)
	}
	defer watcher.Close()

	// Add a path.
	err = watcher.Add(monitorDir)
	if err != nil {
		log.Fatal(err)
	}

	for {
		select {
		case file, ok := <-watcher.Events:
			if !ok {
				log.Println("watch stopped")
				return
			}

			if !file.Has(fsnotify.Create) {
				continue
			}

			err := checkFile(nameCheck, file.Name, inputDir, persistDir, downlinkEndpoint)
			if err != nil {
				log.Println("error checking file:", err)
			}

		case err, ok := <-watcher.Errors:
			if !ok {
				log.Println("watch stopped")
				return
			}
			log.Println("error:", err)
		}
	}
}
