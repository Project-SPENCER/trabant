package dockerlight

import (
	"bufio"
	"bytes"
	_ "embed"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/project-spencer/trabant/tfaas/pkg/dockerlight/runtimes"
	"github.com/project-spencer/trabant/tfaas/pkg/manager"
	"github.com/project-spencer/trabant/tfaas/pkg/util"
)

const (
	containerTimeout   = 3
	cpuMonitorInterval = 1 * time.Second
)

type dockerHandler struct {
	Name        string   `json:"name"`
	Env         string   `json:"env"`
	Threads     int      `json:"threads"`
	UniqueName  string   `json:"uniqueName"`
	FilePath    string   `json:"filePath"`
	Network     string   `json:"network"`
	Containers  []string `json:"containers"`
	HandlerIPs  []string `json:"handlerIPs"`
	persistPath string
}

type DockerLightBackend struct {
	tmpDir         string
	tfaasID        string
	persistFuncDir string
}

func New(tfaasID string, persistFuncDir string) *DockerLightBackend {
	// check that docker is in the path
	_, err := exec.LookPath("docker")
	if err != nil {
		log.Fatalf("docker not found in path: %s", err)
		return nil
	}

	// check that dockerd is running (three times)
	for i := 0; i < 3; i++ {
		cmd := exec.Command("docker", "info")
		err = cmd.Run()
		if err == nil {
			break
		}

		if i == 2 {
			log.Fatalf("dockerd not running: %s", err)
			return nil
		}

		log.Printf("dockerd not running, retrying in 2 seconds")

		time.Sleep(2 * time.Second)
	}

	// create a runtime cache directory in the tmp folder
	tmpDir := path.Join(os.TempDir(), fmt.Sprintf("tfaas-%s", tfaasID))

	log.Println("creating runtime cache directory", tmpDir)

	err = os.MkdirAll(tmpDir, 0777)

	if err != nil {
		log.Fatalf("error creating runtime cache directory: %s", err)
		return nil
	}

	for name, r := range runtimes.Runtimes {
		err = os.MkdirAll(path.Join(tmpDir, name), 0777)
		if err != nil {
			log.Fatalf("error creating runtime cache directory: %s", err)
			return nil
		}

		err = os.WriteFile(path.Join(tmpDir, name, "Dockerfile"), *r.Dockerfile, 0777)

		if err != nil {
			log.Fatalf("error writing Dockerfile: %s", err)
			return nil
		}

		err = os.WriteFile(path.Join(tmpDir, name, "blob.tar.xz"), *r.Blob, 0777)

		if err != nil {
			log.Fatalf("error writing blob: %s", err)
			return nil
		}
	}

	log.Println("created runtime cache directory", tmpDir)

	return &DockerLightBackend{
		tmpDir:         tmpDir,
		tfaasID:        tfaasID,
		persistFuncDir: persistFuncDir,
	}
}

func (db *DockerLightBackend) Stop() error {
	// remove the runtime cache directory
	err := os.RemoveAll(db.tmpDir)
	if err != nil {
		return err
	}

	return nil
}
func (db *DockerLightBackend) Resume() (map[string]manager.Handler, error) {
	handlers := make(map[string]manager.Handler)

	// check if the persistFuncDir exists
	_, err := os.Stat(db.persistFuncDir)
	if err != nil {
		// assuming there is nothing to do
		return handlers, nil
	}

	// read the directory
	files, err := os.ReadDir(db.persistFuncDir)
	if err != nil {
		return nil, err
	}

	for _, file := range files {
		h := dockerHandler{
			persistPath: path.Join(db.persistFuncDir, file.Name()),
		}

		b, err := os.ReadFile(h.persistPath)
		if err != nil {
			return nil, err
		}

		err = json.Unmarshal(b, &h)

		if err != nil {
			return nil, err
		}

		handlers[h.Name] = &h

		// check that the containers are still running
		// assuming docker handles container restart on sudden reboot
		for _, ip := range h.HandlerIPs {
			log.Println("waiting for container", ip, "to be ready")
			maxRetries := 10
			for {
				maxRetries--
				if maxRetries == 0 {
					return nil, fmt.Errorf("container %s not ready after 10 retries", ip)
				}

				// timeout of 3 second
				client := http.Client{
					Timeout: containerTimeout * time.Second,
				}

				resp, err := client.Get("http://" + ip + ":8000/health")
				if err != nil {
					log.Println(err)
					log.Println("retrying in 1 second")
					time.Sleep(1 * time.Second)
					continue
				}
				resp.Body.Close()
				if resp.StatusCode == http.StatusOK {
					log.Println("container", ip, "is ready")
					break
				}
				log.Println("container", ip, "is not ready yet, retrying in 1 second")
				time.Sleep(1 * time.Second)
			}
		}
	}

	return handlers, nil
}

func (db *DockerLightBackend) Create(fd manager.FunctionDefinition) (manager.Handler, error) {

	// check that the runtime exists
	_, ok := runtimes.Runtimes[fd.Env]
	if !ok {
		return nil, fmt.Errorf("runtime %s not found", fd.Env)
	}

	// check that the mountDirs exist
	for _, m := range fd.Mounts {
		_, err := os.Stat(m.Dir)
		if err != nil {
			return nil, fmt.Errorf("mount directory %s not found: %s", m.Dir, err)
		}
	}

	// make a unique function name by appending unique id string to function name
	uid := util.UID()

	dh := &dockerHandler{
		Name:        fd.Name,
		Env:         fd.Env,
		Threads:     fd.Threads,
		Containers:  make([]string, 0, fd.Threads),
		HandlerIPs:  make([]string, 0, fd.Threads),
		persistPath: path.Join(db.persistFuncDir, fd.Name),
	}

	dh.UniqueName = fd.Name + "-" + uid
	log.Println("creating function", fd.Name, "with unique name", dh.UniqueName)

	// make a folder for the function
	// mkdir <folder>
	dh.FilePath = path.Join(db.tmpDir, dh.UniqueName)

	err := os.MkdirAll(dh.FilePath, 0777)
	if err != nil {
		return nil, err
	}

	// copy Dockerfile and blob into folder
	// runtimes[<env>]/Dockerfile -> <folder>/Dockerfile
	// runtimes[<env>]/blob -> <folder>/blob
	err = os.WriteFile(path.Join(dh.FilePath, "Dockerfile"), *(runtimes.Runtimes[fd.Env].Dockerfile), 0777)

	if err != nil {
		return nil, err
	}

	// err = os.WriteFile(path.Join(dh.filePath, "blob.tar.xz"), *(runtimes.Runtimes[fd.Env].Blob), 0777)

	// if err != nil {
	// 	return nil, err
	// }

	// log.Println("copied runtime files to folder", dh.filePath)

	// symlink the blob and Dockerfile
	// ln -s <blob> <folder>/blob
	// ln -s <Dockerfile> <folder>/Dockerfile
	// err = os.Symlink(path.Join(db.tmpDir, fd.Env, "blob.tar.xz"), path.Join(dh.filePath, "blob.tar.xz"))
	// if err != nil {
	// 	return nil, err
	// }

	// err = os.Symlink(path.Join(db.tmpDir, fd.Env, "Dockerfile"), path.Join(dh.filePath, "Dockerfile"))
	// if err != nil {
	// 	return nil, err
	// }

	// log.Println("symlinked runtime files to folder", dh.filePath)

	// copy function into folder
	// into a subfolder called fn
	// cp <file> <folder>/fn
	err = os.MkdirAll(path.Join(dh.FilePath, "fn"), 0777)
	if err != nil {
		return nil, err
	}

	err = util.CopyAll(fd.FileDir, path.Join(dh.FilePath, "fn"))
	if err != nil {
		return nil, err
	}

	log.Printf("building image with name %s in folder %s", dh.UniqueName, dh.FilePath)
	t := time.Now()

	// build image
	// docker build --force-rm --label tfaas-function=<name> --label tfaas=<tfaasid> -t <image> --build-arg RUNTIME_DIR=<runtime> --build-arg FUNC_DIR=<func-dir> -f <func-dir>/Dockerfile <tfaas-dir>
	cmd := exec.Command("docker", "build", "--force-rm", "--label", "tfaas-function="+dh.Name, "--label", "tfaas="+db.tfaasID, "--build-arg", "RUNTIME_DIR="+fd.Env, "--build-arg", "FUNC_DIR="+dh.UniqueName, "-f", path.Join(dh.UniqueName, "Dockerfile"), "-t", dh.UniqueName, ".")
	cmd.Dir = db.tmpDir
	// cmd := exec.Command("docker", "build", "--force-rm", "--label", "tfaas-function="+dh.name, "--label", "tfaas="+db.tfaasID, "--build-arg", "RUNTIME_DIR=.", "--build-arg", "FUNC_DIR=.", "-t", dh.uniqueName, ".")
	// cmd.Dir = dh.filePath

	// stream build output to log.Println
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	log.Printf("running command %s", cmd.String())

	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("error building image with command %s", cmd.String())
	}

	log.Println("built image", dh.UniqueName, "in", time.Since(t))

	// create network
	// docker network create --label tfaas-function=<name> --label tfaas=<tfaasid> <network>
	cmd = exec.Command("docker", "network", "create", "--label", "tfaas-function="+dh.Name, "--label", "tfaas="+db.tfaasID, dh.UniqueName)

	out, err := cmd.CombinedOutput()

	if err != nil {
		return nil, fmt.Errorf("error building image: %s", out)
	}

	// get network id from output
	dh.Network = strings.TrimSpace(string(out))

	log.Println("created network", dh.UniqueName, "with id", dh.Network)

	e := make([]string, 0, len(fd.Envs))

	for k, v := range fd.Envs {
		e = append(e, fmt.Sprintf("%s=%s", k, v))
	}

	// create containers
	// docker create -d --label tfaas-function=<name> --label tfaas=<tfaasid> --env <e> --network <network> --name <container> --restart unless-stopped <image>
	for i := 0; i < dh.Threads; i++ {

		c := []string{"docker", "run", "-d", "--label", "tfaas-function=" + dh.Name, "--label", "tfaas=" + db.tfaasID, "--network", dh.UniqueName, "--name", dh.UniqueName + fmt.Sprintf("-%d", i), "--restart", "unless-stopped"}

		for _, env := range e {
			c = append(c, "--env")
			c = append(c, env)
		}

		for _, m := range fd.Mounts {
			mode := "ro"
			if m.Rw {
				mode = "rw"
			}
			c = append(c, "-v", m.Dir+":/files/"+m.Target+":"+mode)
		}

		// add the image as a final argument
		c = append(c, dh.UniqueName)

		// add the function name as first argument
		c = append(c, dh.Name)

		// and add function handler as argument so it appears in ps and top
		c = append(c, dh.UniqueName, strconv.Itoa(i))

		log.Println("creating container with command", c)

		cmd = exec.Command(c[0], c[1:]...)

		out, err := cmd.CombinedOutput()

		if err != nil {
			return nil, fmt.Errorf("error creating container: %s", out)
		}

		container := strings.TrimSpace(string(out))

		log.Printf("created container %s (id %d)", container, i)

		dh.Containers = append(dh.Containers, container)
	}

	// remove folder
	// rm -rf <folder>
	err = os.RemoveAll(dh.FilePath)
	if err != nil {
		return nil, err
	}

	log.Println("removed folder", dh.FilePath)

	return dh, nil

}

func (dh *dockerHandler) IPs() []string {
	return dh.HandlerIPs
}

func (dh *dockerHandler) Start() error {
	log.Printf("dh: %+v", dh)

	// start containers
	// docker start <container>

	wg := sync.WaitGroup{}
	for _, container := range dh.Containers {
		wg.Add(1)
		go func(c string) {
			cmd := exec.Command("docker", "start", c)

			out, err := cmd.CombinedOutput()

			wg.Done()

			if err != nil {
				log.Printf("error starting container %s: %s", c, out)
				return
			}

			log.Println("started container", c)
		}(container)
	}
	wg.Wait()

	// get container IPs
	// docker inspect <container>
	for _, container := range dh.Containers {

		cmd := exec.Command("docker", "inspect", container)

		out, err := cmd.CombinedOutput()

		if err != nil {
			return fmt.Errorf("error inspecting container %s: %s", container, out)
		}

		// get the ip address of the container
		// c.NetworkSettings.Networks.<network>.IPAddress

		var c []struct {
			State struct {
				Pid int `json:"Pid"`
			} `json:"State"`
			NetworkSettings struct {
				Networks map[string]struct {
					IPAddress string `json:"IPAddress"`
				} `json:"Networks"`
			} `json:"NetworkSettings"`
		}

		err = json.Unmarshal(out, &c)
		if err != nil {
			return err
		}

		if len(c) < 1 {
			return fmt.Errorf("no container found")
		}

		dh.HandlerIPs = append(dh.HandlerIPs, c[0].NetworkSettings.Networks[dh.UniqueName].IPAddress)

		ipAddr := c[0].NetworkSettings.Networks[dh.UniqueName].IPAddress

		if ipAddr == "" {
			return fmt.Errorf("no ip address found for container %s", container)
		}

		log.Println("got ip", ipAddr, "for container", container)

		log.Println("got pid", c[0].State.Pid, "for container", container)

		// go func(f string, p int) {
		// 	for {
		// 		usage, err := calculateCPUUsage(p, cpuMonitorInterval)
		// 		if err != nil {
		// 			log.Printf("error getting cpu usage for func %s pid %d: %s", f, p, err)
		// 			return
		// 		}

		// 		log.Printf("cpu usage for func %s pid %d: %.2f%%", f, p, usage)
		// 	}
		// }(dh.name, c[0].State.Pid)
	}

	// wait for the containers to be ready
	// curl http://<container>:8000/ready
	for _, ip := range dh.HandlerIPs {
		log.Println("waiting for container", ip, "to be ready")
		maxRetries := 10
		for {
			maxRetries--
			if maxRetries == 0 {
				return fmt.Errorf("container %s not ready after 10 retries", ip)
			}

			// timeout of 3 second
			client := http.Client{
				Timeout: containerTimeout * time.Second,
			}

			resp, err := client.Get("http://" + ip + ":8000/health")
			if err != nil {
				log.Println(err)
				log.Println("retrying in 1 second")
				time.Sleep(1 * time.Second)
				continue
			}
			resp.Body.Close()
			if resp.StatusCode == http.StatusOK {
				log.Println("container", ip, "is ready")
				break
			}
			log.Println("container", ip, "is not ready yet, retrying in 1 second")
			time.Sleep(1 * time.Second)
		}
	}

	// persist the configuration
	// write the configuration to a file

	b, err := json.Marshal(dh)

	if err != nil {
		return err
	}

	err = os.WriteFile(dh.persistPath, b, 0777)

	if err != nil {
		return err
	}

	return nil
}

func (dh *dockerHandler) Destroy() error {
	log.Println("destroying function", dh.Name)
	log.Printf("dh: %+v", dh)

	wg := sync.WaitGroup{}
	log.Printf("stopping containers: %v", dh.Containers)
	for _, c := range dh.Containers {
		log.Println("removing container", c)

		wg.Add(1)
		go func(c string) {
			log.Println("stopping container", c)

			timeout := containerTimeout // seconds

			// docker stop -t <timeout> <container>
			cmd := exec.Command("docker", "stop", "-t", strconv.Itoa(timeout), c)

			out, err := cmd.CombinedOutput()

			if err != nil {
				log.Printf("error stopping container %s: %s", c, out)
			}

			log.Println("stopped container", c)

			// docker rm <container>
			cmd = exec.Command("docker", "rm", c)

			out, err = cmd.CombinedOutput()

			wg.Done()
			if err != nil {
				log.Printf("error removing container %s: %s", c, out)
			}
		}(c)

		log.Println("removed container", c)
	}
	wg.Wait()

	// remove network
	// docker network rm <network>
	cmd := exec.Command("docker", "network", "rm", dh.Network)

	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("error removing network %s: %s", dh.Network, out)
	}

	log.Println("removed network", dh.Network)

	// remove image
	// docker rmi <image>
	cmd = exec.Command("docker", "rmi", dh.UniqueName)

	out, err = cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("error removing image %s: %s", dh.UniqueName, out)
	}

	log.Println("removed image", dh.UniqueName)

	// remove the persisted file
	err = os.Remove(dh.persistPath)

	if err != nil {
		return err
	}

	return nil
}

func (dh *dockerHandler) Logs() (io.Reader, error) {
	// get container logs
	var logs bytes.Buffer
	for i, container := range dh.Containers {
		// docker container logs <container>
		cmd := exec.Command("docker", "container", "logs", container)
		out, err := cmd.CombinedOutput()

		if err != nil {
			return nil, fmt.Errorf("error getting logs: %s", out)
		}

		// add a prefix to each line
		// function=<function> handler=<handler> <line>

		scanner := bufio.NewScanner(bytes.NewReader(out))

		for scanner.Scan() {
			logs.WriteString(fmt.Sprintf("function=%s handler=%d %s\n", dh.Name, i, scanner.Text()))
		}

		if err := scanner.Err(); err != nil {
			return nil, err
		}
	}

	return &logs, nil
}
