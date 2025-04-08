package endpoint

import (
	"context"
	"io"
	"log"
	"net/http"
	"time"

	"github.com/project-spencer/trabant/tfaas/pkg/rproxy"
)

func Start(r *rproxy.RProxy, listenAddr string, kill <-chan struct{}) {

	mux := http.NewServeMux()

	mux.HandleFunc("/", func(w http.ResponseWriter, req *http.Request) {
		p := req.URL.Path

		for p != "" && p[0] == '/' {
			p = p[1:]
		}

		if p == "" {
			w.WriteHeader(http.StatusNotFound)
			return
		}

		async := req.Header.Get("X-TFaas-Sync") == ""
		id := req.Header.Get("X-TFaas-ID")

		log.Printf("have request for path: %s (async: %v, id: %s)", p, async, id)

		req_body, err := io.ReadAll(req.Body)

		if err != nil {
			w.WriteHeader(http.StatusInternalServerError)
			log.Print(err)
			return
		}

		s, res := r.Call(p, req_body, id, async)

		switch s {
		case rproxy.StatusOK:
			w.WriteHeader(http.StatusOK)
			w.Write(res)
		case rproxy.StatusAccepted:
			w.WriteHeader(http.StatusAccepted)
		case rproxy.StatusNotFound:
			w.WriteHeader(http.StatusNotFound)
		case rproxy.StatusError:
			w.WriteHeader(http.StatusInternalServerError)
		}
	})

	log.Printf("Starting HTTP server on %s", listenAddr)

	var srv http.Server
	srv.Addr = listenAddr
	srv.Handler = mux
	go srv.ListenAndServe()

	<-kill

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	err := srv.Shutdown(shutdownCtx)
	if err != nil {
		log.Println(err)
	}
	cancel()

	log.Print("HTTP server stopped")

	<-kill
}
