package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/project-spencer/trabant/tfaas/pkg/dockerlight"
	"github.com/project-spencer/trabant/tfaas/pkg/dockerlight/runtimes"
	"github.com/project-spencer/trabant/tfaas/pkg/endpoint"
	"github.com/project-spencer/trabant/tfaas/pkg/manager"
	"github.com/project-spencer/trabant/tfaas/pkg/rproxy"
	"github.com/project-spencer/trabant/tfaas/pkg/stateswitcher"
	"github.com/project-spencer/trabant/tfaas/pkg/util"
)

const (
	RProxyConfigPort    = 8081
	RProxyListenAddress = ""
	RProxyBin           = "./rproxy"
)

type server struct {
	ms *manager.ManagementService
}

func main() {

	log.SetPrefix("[tf] ")
	log.SetFlags(log.Ldate | log.Ltime | log.Lmicroseconds | log.LstdFlags | log.Lshortfile | log.LUTC)

	// some flags as inputs
	var stateswitching string
	flag.StringVar(&stateswitching, "stateswitching", "false", "stateswitching type (false/off, api)")

	var stateswitchingUpdateInterval int
	flag.IntVar(&stateswitchingUpdateInterval, "stateswitching-update-interval", 1, "interval for stateswitching (s)")

	var stateswitchingInterval int
	flag.IntVar(&stateswitchingInterval, "stateswitching-interval", 1, "interval for stateswitching (s)")

	var stateswitchingAPIUrl string
	flag.StringVar(&stateswitchingAPIUrl, "stateswitching-api-url", "http://localhost:8080", "host for api stateswitching")

	var rproxyBackoffPeriod float64
	flag.Float64Var(&rproxyBackoffPeriod, "rproxy-backoff-period", 0.5, "backoff period for rproxy (s)")

	var resume bool
	flag.BoolVar(&resume, "resume", false, "resume from previous run")

	var httpPort int
	flag.IntVar(&httpPort, "http-port", 8000, "port for http server")

	var configPort int
	flag.IntVar(&configPort, "config-port", 8080, "port for config server")

	var backend string
	flag.StringVar(&backend, "tf-backend", "dockerlight", "backend for tfaas")

	var persistDir string
	flag.StringVar(&persistDir, "persist-dir", "/tmp/tfaas-persist", "directory to persist function calls")

	var persistFuncDir string
	flag.StringVar(&persistFuncDir, "persist-func-dir", "/tmp/tfaas-persist-func", "directory to persist functions")

	flag.Parse()

	// setting backend to docker
	id := util.UID()

	// find backend
	var tfBackend manager.Backend
	switch backend {
	case "dockerlight":
		log.Println("using docker backend")
		supported := "This docker backend supports the following runtimes:\n"
		for r := range runtimes.Runtimes {
			supported += fmt.Sprintf("  - %s\n", r)
		}
		log.Print(supported)

		if persistFuncDir != "" {
			err := os.MkdirAll(persistFuncDir, 0755)
			if err != nil {
				log.Fatalf("could not create directory: %s", err.Error())
			}
		}

		tfBackend = dockerlight.New(id, persistFuncDir)
	default:
		log.Fatalf("invalid backend %s", backend)
	}

	var switcher rproxy.StateServer
	switch stateswitching {
	case "api":
		log.Printf("stateswitching enabled: apiHost: %s", stateswitchingAPIUrl)
		switcher = stateswitcher.NewAPI(stateswitchingAPIUrl, time.Duration(stateswitchingUpdateInterval)*time.Second)
	default:
		log.Println("stateswitching disabled")
		switcher = &stateswitcher.NoSwitch{}
	}

	// start the rproxy
	// only http required
	r := rproxy.New(switcher, time.Duration(stateswitchingInterval)*time.Second, time.Duration(rproxyBackoffPeriod)*time.Second, persistDir, resume)

	rkill := make(chan struct{})

	rproxyListenAddr := fmt.Sprintf("%s:%d", RProxyListenAddress, httpPort)

	log.Printf("starting rproxy http server on %s", rproxyListenAddr)
	go endpoint.Start(r, rproxyListenAddr, rkill)

	log.Println("started rproxy")

	ms := manager.New(
		id,
		rproxyListenAddr,
		r,
		tfBackend,
		resume,
	)

	s := &server{
		ms: ms,
	}

	// create handlers
	mux := http.NewServeMux()
	mux.HandleFunc("/upload", s.uploadHandler)
	mux.HandleFunc("/delete", s.deleteHandler)
	mux.HandleFunc("/list", s.listHandler)
	mux.HandleFunc("/wipe", s.wipeHandler)
	mux.HandleFunc("/logs", s.logsHandler)

	var srv http.Server
	srv.Addr = fmt.Sprintf(":%d", configPort)
	srv.Handler = mux

	go func() {
		// start server
		log.Printf("starting management HTTP server on %s", srv.Addr)
		err := srv.ListenAndServe()
		if err != nil && err != http.ErrServerClosed {
			log.Fatal(err)
		}
	}()

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM, syscall.SIGINT)

	<-sig

	log.Println("received interrupt")
	log.Println("shutting down")

	// stop http server
	log.Println("stopping http server")
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	err := srv.Shutdown(shutdownCtx)
	if err != nil {
		log.Println(err)
	}
	cancel()

	// stop rproxy
	log.Println("stopping rproxy")

	rkill <- struct{}{}
	rkill <- struct{}{}

	// stop handlers
	log.Println("stopping management service")
	err = ms.Stop()

	if err != nil {
		log.Println(err)
	}

	log.Println("stopped all tfaas services")

	os.Exit(0)

}

func (s *server) uploadHandler(w http.ResponseWriter, r *http.Request) {

	if r.Method != http.MethodPost {
		w.WriteHeader(http.StatusBadRequest)
		return
	}

	// parse request
	d := struct {
		FunctionName     string   `json:"name"`
		FunctionEnv      string   `json:"env"`
		FunctionThreads  int      `json:"threads"`
		FunctionZip      string   `json:"zip"`
		FunctionEnvs     []string `json:"envs"`
		FunctionMountDir []struct {
			Dir    string `json:"mount_dir"`
			Target string `json:"mount_target"`
			Rw     bool   `json:"mount_rw"`
		} `json:"mounts"`
	}{}

	err := json.NewDecoder(r.Body).Decode(&d)
	if err != nil {
		w.WriteHeader(http.StatusBadRequest)
		log.Println(err)
		return
	}

	log.Println("got request to upload function: Name", d.FunctionName, "Env", d.FunctionEnv, "Threads", d.FunctionThreads, "Bytes", len(d.FunctionZip), "Envs", d.FunctionEnvs, "Mounts", d.FunctionMountDir)

	envs := make(map[string]string)
	for _, e := range d.FunctionEnvs {
		k, v, ok := strings.Cut(e, "=")

		if !ok {
			log.Println("invalid env:", e)
			continue
		}

		envs[k] = v
	}

	mounts := make([]manager.Mount, 0, len(d.FunctionMountDir))

	for _, m := range d.FunctionMountDir {
		mounts = append(mounts, manager.Mount{
			Dir:    m.Dir,
			Target: m.Target,
			Rw:     m.Rw,
		})
	}

	res, err := s.ms.Upload(d.FunctionName, d.FunctionEnv, d.FunctionThreads, d.FunctionZip, envs, mounts)

	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		log.Println(err)
		return
	}

	// return success
	w.WriteHeader(http.StatusOK)
	fmt.Fprint(w, res)

}

func (s *server) deleteHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.WriteHeader(http.StatusBadRequest)
		return
	}

	// parse request
	d := struct {
		FunctionName string `json:"name"`
	}{}

	err := json.NewDecoder(r.Body).Decode(&d)
	if err != nil {
		w.WriteHeader(http.StatusBadRequest)
		log.Println(err)
		return
	}

	log.Println("got request to delete function:", d.FunctionName)

	// delete function
	err = s.ms.Delete(d.FunctionName)

	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		log.Println(err)
		return
	}

	// return success
	w.WriteHeader(http.StatusOK)
}

func (s *server) listHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.WriteHeader(http.StatusBadRequest)
		return
	}

	l := s.ms.List()

	// return success
	w.WriteHeader(http.StatusOK)
	for _, f := range l {
		fmt.Fprintf(w, "%s\n", f)
	}
}

func (s *server) wipeHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.WriteHeader(http.StatusBadRequest)
		return
	}

	err := s.ms.Wipe()

	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		log.Println(err)
		return
	}

	w.WriteHeader(http.StatusOK)
}

func (s *server) logsHandler(w http.ResponseWriter, r *http.Request) {

	if r.Method != http.MethodGet {
		w.WriteHeader(http.StatusBadRequest)
		return
	}

	// parse request
	var logs io.Reader
	name := r.URL.Query().Get("name")

	if name == "" {
		l, err := s.ms.Logs()
		if err != nil {
			w.WriteHeader(http.StatusInternalServerError)
			log.Println(err)
			return
		}
		logs = l
	}

	if name != "" {
		l, err := s.ms.LogsFunction(name)
		if err != nil {
			w.WriteHeader(http.StatusInternalServerError)
			log.Println(err)
			return
		}
		logs = l
	}

	// return success
	w.WriteHeader(http.StatusOK)
	// w.Header().Set("Content-Type", "text/plain")
	_, err := io.Copy(w, logs)
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		log.Println(err)
		return
	}
}
