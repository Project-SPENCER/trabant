package runtimes

type Runtime struct {
	Blob       *[]byte
	Dockerfile *[]byte
}

var Runtimes map[string]Runtime

func init() {
	Runtimes = make(map[string]Runtime)
	if Python3Blob != nil {
		Runtimes["python3"] = Runtime{
			Blob:       &Python3Blob,
			Dockerfile: &Python3Dockerfile,
		}
	}

	if MLBlob != nil {
		Runtimes["ml"] = Runtime{
			Blob:       &MLBlob,
			Dockerfile: &MLDockerfile,
		}
	}

	if TFLiteBlob != nil {
		Runtimes["tflite"] = Runtime{
			Blob:       &TFLiteBlob,
			Dockerfile: &TFLiteDockerfile,
		}
	}
}
