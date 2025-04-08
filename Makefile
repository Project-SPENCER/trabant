PROJECT_NAME := trabant
PYTHON_VERSION := 3.11
# ALPINE_VERSION := 3.19
DEBIAN_VERSION := slim-bookworm
OS:=linux
ARCH:=arm64
PKG:=github.com/project-spencer/$(PROJECT_NAME)
GO_FILES:=$(shell find . -name '*.go' -not -path "./vendor/*" -not -path "./tfaas/*")
TFAAS_FILES:=$(shell find ./tfaas -name '*.go' -not -path "./vendor/*")
FN_FILES:=$(shell find fns -type f)
COMPILED_FNS_FILES:=$(shell find cmd/upload/compiledfns -type f)

.PHONY: all

all: build

build: pre.bin post.bin tfaas.bin monitor.bin upload.bin eval.bin measure.bin

%.bin: go.mod go.sum ${GO_FILES}
	GOOS=linux GOARCH=arm64 CGOENABLED=0 go build -ldflags "-s -w" -o $@ ${PKG}/cmd/$(basename $@)

monitor.bin: cmd/monitor/monitor.go go.mod go.sum pkg/model/*.csv ${GO_FILES}
	GOOS=linux GOARCH=arm64 CGOENABLED=0 go build -ldflags "-s -w" -o $@ ${PKG}/cmd/monitor

upload.bin: cmd/upload/upload.go cmd/upload/compiledfns go.mod go.sum ${GO_FILES}
	GOOS=linux GOARCH=arm64 CGOENABLED=0 go build -ldflags "-s -w" -o $@ ${PKG}/cmd/upload

tfaas.bin: go.mod go.sum ${TFAAS_FILES}
	@mkdir -p $(dir $@)
	pushd tfaas && \
	make RUNTIMES="tflite python3" tf-${OS}-${ARCH} && \
	popd && \
	mv tfaas/tf-${OS}-${ARCH} $@

cmd/upload/compiledfns: ${FN_FILES}
	rm -rf $@
	mkdir -p $@
	for fn in fns/*; do \
	fn_name=$$(basename $$fn) ; \
		cp -r "$$fn" "./$@/$$fn_name" ; \
		if [ -f $$fn/requirements.txt ]; then \
			docker run --rm --entrypoint /bin/sh \
				--platform=linux/arm64  \
			    -v "$$(realpath ./$@/$$fn_name)":/app \
    			-w /app \
    			python:${PYTHON_VERSION}-${DEBIAN_VERSION} \
    			-c "ls && pwd && pip install -r requirements.txt --upgrade -t ." ; \
				rm -rf "compiled_fns/$$fn_name/requirements.txt" ; \
		fi ; \
	done
