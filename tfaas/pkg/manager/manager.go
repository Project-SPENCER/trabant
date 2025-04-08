package manager

import (
	"bytes"
	"encoding/base64"
	"fmt"
	"io"
	"log"
	"os"
	"path"
	"sync"

	"github.com/project-spencer/trabant/tfaas/pkg/rproxy"
	"github.com/project-spencer/trabant/tfaas/pkg/util"
)

type ManagementService struct {
	id                    string
	backend               Backend
	functionHandlers      map[string]Handler
	functionHandlersMutex sync.Mutex
	rproxyAddr            string
	rproxy                *rproxy.RProxy
	persistFuncDir        string
}

type Mount struct {
	Dir    string
	Target string
	Rw     bool
}

type FunctionDefinition struct {
	Name    string
	Env     string
	Threads int
	FileDir string
	Envs    map[string]string
	Mounts  []Mount
}

type Backend interface {
	Create(FunctionDefinition) (Handler, error)
	Resume() (map[string]Handler, error)
	Stop() error
}

type Handler interface {
	IPs() []string
	Start() error
	Destroy() error
	Logs() (io.Reader, error)
}

func New(id string, rproxyAddr string, rproxy *rproxy.RProxy, tfBackend Backend, resume bool) *ManagementService {
	ms := &ManagementService{
		id:               id,
		backend:          tfBackend,
		functionHandlers: make(map[string]Handler),
		rproxyAddr:       rproxyAddr,
		rproxy:           rproxy,
	}

	if resume {
		log.Println("resuming functions")
		handlers, err := tfBackend.Resume()
		if err != nil {
			log.Fatalf("could not resume functions: %s", err.Error())
		}

		for name, fh := range handlers {
			ms.functionHandlers[name] = fh

			// tell rproxy about the new function
			ms.rproxy.Add(name, fh.IPs())
		}
	}

	return ms
}

func (ms *ManagementService) Logs() (io.Reader, error) {

	var logs bytes.Buffer

	for name := range ms.functionHandlers {
		l, err := ms.LogsFunction(name)
		if err != nil {
			return nil, err
		}

		_, err = io.Copy(&logs, l)
		if err != nil {
			return nil, err
		}

		logs.WriteString("\n")
	}

	return &logs, nil
}

func (ms *ManagementService) LogsFunction(name string) (io.Reader, error) {

	fh, ok := ms.functionHandlers[name]
	if !ok {
		return nil, fmt.Errorf("function %s not found", name)
	}

	return fh.Logs()
}

func (ms *ManagementService) List() []string {
	list := make([]string, 0, len(ms.functionHandlers))
	for name := range ms.functionHandlers {
		list = append(list, name)
	}

	return list
}

func (ms *ManagementService) Wipe() error {
	for name := range ms.functionHandlers {
		log.Println("destroying function", name)
		ms.Delete(name)
	}

	return nil
}
func (ms *ManagementService) Delete(name string) error {

	fh, ok := ms.functionHandlers[name]
	if !ok {
		return fmt.Errorf("function %s not found", name)
	}

	log.Println("destroying function", name)

	ms.functionHandlersMutex.Lock()
	defer ms.functionHandlersMutex.Unlock()

	err := fh.Destroy()
	if err != nil {
		return err
	}

	// tell rproxy about the delete function
	ms.rproxy.Del(name)

	// delete locally
	delete(ms.functionHandlers, name)

	return nil
}

func (ms *ManagementService) Upload(name string, env string, threads int, zipped string, envs map[string]string, mounts []Mount) (string, error) {

	if name == "all" {
		return "", fmt.Errorf("function name 'all' is reserved")
	}

	// b64 decode zip
	funczip, err := base64.StdEncoding.DecodeString(zipped)
	if err != nil {
		// w.WriteHeader(http.StatusBadRequest)
		log.Println(err)
		return "", err
	}

	// create function handler

	// only allow alphanumeric characters
	if !util.IsAlphaNumeric(name) {
		return "", fmt.Errorf("function name %s contains non-alphanumeric characters", name)
	}

	// make a unique id for the function
	uid := util.UID()

	log.Println("creating function", name, "with uid", uid)

	// create a new function handler

	p := path.Join(os.TempDir(), fmt.Sprintf("tfaas-%s", ms.id), uid)

	err = os.MkdirAll(p, 0777)

	if err != nil {
		return "", err
	}

	log.Println("created folder", p)

	// write zip to file
	zipPath := path.Join(os.TempDir(), fmt.Sprintf("tfaas-%s", ms.id), uid+".zip")
	err = os.WriteFile(zipPath, funczip, 0777)

	if err != nil {
		return "", err
	}

	err = util.Unzip(zipPath, p)

	if err != nil {
		return "", err
	}

	defer func() {
		// remove folder
		err = os.RemoveAll(p)
		if err != nil {
			log.Println("error removing folder", p, err)
		}

		err = os.Remove(zipPath)
		if err != nil {
			log.Println("error removing zip", zipPath, err)
		}

		log.Println("removed folder", p)
		log.Println("removed zip", zipPath)
	}()

	// we know this function already, destroy its current handler
	if _, ok := ms.functionHandlers[name]; ok {
		err = ms.functionHandlers[name].Destroy()
		if err != nil {
			return "", err
		}
	}

	// create new function handler
	ms.functionHandlersMutex.Lock()
	defer ms.functionHandlersMutex.Unlock()

	fh, err := ms.backend.Create(FunctionDefinition{
		Name:    name,
		Env:     env,
		Threads: threads,
		FileDir: p,
		Envs:    envs,
		Mounts:  mounts,
	})

	if err != nil {
		return "", err
	}

	ms.functionHandlers[name] = fh

	err = ms.functionHandlers[name].Start()

	if err != nil {
		return "", err
	}

	// tell rproxy about the new function
	ms.rproxy.Add(name, fh.IPs())

	// return success
	// w.WriteHeader(http.StatusOK)
	r := fmt.Sprintf("http://%s/%s\n", ms.rproxyAddr, name)

	return r, nil
}

func (ms *ManagementService) Stop() error {
	err := ms.Wipe()
	if err != nil {
		return err
	}

	return ms.backend.Stop()
}
