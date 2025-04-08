PROJECT_NAME := "tfaas"
PKG := "github.com/project-spencer/trabant/${PROJECT_NAME}"
GO_FILES := $(shell find . -name '*.go' | grep -v /vendor/ | grep -v /ext/ | grep -v _test.go)
TEST_DIR := ./test
GOARCH := $(shell go env GOARCH)
GOOS := $(shell go env GOOS)
RUNTIMES = python3

.PHONY: all build clean tf

all: build

build: tf

.PRECIOUS: pkg/dockerlight/runtimes/%.tar.xz
pkg/dockerlight/runtimes/%.tar.xz: private _RUNTIME = $(word 1, $(subst /, ,$(basename $*)))
pkg/dockerlight/runtimes/%.tar.xz: private _PLATFORM = $(patsubst blob-%,%,$(notdir $*))
pkg/dockerlight/runtimes/%.tar.xz:
	echo "Building for runtime ${_RUNTIME} and platform ${_PLATFORM}"
	cd $(@D) ; docker build --platform=linux/${_PLATFORM} -t ${PROJECT_NAME}-${_RUNTIME} --target final-${_PLATFORM} -f build.Dockerfile .
	docker run -d -t --platform=linux/${_PLATFORM} --name ${PROJECT_NAME}-${_RUNTIME} --rm ${PROJECT_NAME}-${_RUNTIME}
	docker export ${PROJECT_NAME}-${_RUNTIME} | xz > $@
	docker kill ${PROJECT_NAME}-${_RUNTIME}

tf: tf-linux-amd64 tf-linux-arm64 tf-darwin-arm64

RUNTIME_DEPS := $(foreach i, $(RUNTIMES), pkg/dockerlight/runtimes/$i/blob-%.tar.xz pkg/dockerlight/runtimes/$i/Dockerfile)

tf-linux-%: ${GO_FILES} ${RUNTIME_DEPS}
	GOOS=linux GOARCH=$* CGOENABLED=0 go build -ldflags "-s -w" -tags "${RUNTIMES}" -o $@ -v ${PKG}/cmd/${@:%-linux-$*=%}

tf-darwin-%: ${GO_FILES} ${RUNTIME_DEPS}
	GOOS=darwin GOARCH=$* CGOENABLED=0 go build -ldflags "-s -w" -tags "${RUNTIMES}" -o $@ -v ${PKG}/cmd/${@:%-darwin-$*=%}

test: tf-${GOOS}-${GOARCH} ${TEST_DIR}/test_all.py
	@python3 ${TEST_DIR}/test_all.py

clean: clean.sh
	@sh clean.sh
