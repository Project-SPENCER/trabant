FROM alpine:3.19.4@sha256:e910e9408f39003d77ec0f83b18c8892d6899c0a8d4d53f35a67596c33ebfa1d AS builder

RUN apk add --update --no-cache \
    curl \
    git \
    python3 \
    py3-pip \
    python3-dev \
    py3-numpy \
    make \
    cmake \
    gcc \
    g++ \
    swig \
    libjpeg-turbo-dev \
    zlib-dev \
    bash \
    linux-headers \
    py3-numpy-dev \
    py3-numpy \
    py3-pybind11 \
    py3-pybind11-dev \
    py3-wheel \
    py3-setuptools

RUN apk add --no-cache libstdc++==13.2.1_git20231014-r0

RUN git clone https://github.com/tensorflow/tensorflow.git --branch v2.16.1 --depth 1
WORKDIR /tensorflow
COPY tf-alpine-3.19.patch /
RUN git apply /tf-alpine-3.19.patch
RUN BUILD_NUM_JOBS=8 bash tensorflow/lite/tools/pip_package/build_pip_package_with_cmake.sh
# RUN cp /tensorflow/tensorflow/lite/tools/pip_package/gen/tflite_pip/python3/dist/tflite_runtime-2.17.0-cp311-cp311-linux_x86_64.whl

# cp /usr/lib/libstdc++.so.6.0.32 $(@D)/libstdc++.so.6.0.32
# cp /usr/lib/libgcc_s.so.1 $(@D)/libgcc_s.so.1

# shutil.copy("libstdc++.so.6.0.32", "/usr/lib/libstdc++.so.6.0.32")
# os.symlink("/usr/lib/libstdc++.so.6.0.32", "/usr/lib/libstdc++.so.6")
# shutil.copy("libgcc_s.so.1", "/usr/lib/libgcc_s.so.1")

FROM python:3.11-alpine3.19@sha256:911a1f26d9b63c000b41f76fc5fe0a2b59a678a55afe6ced2a6fd4fe630daac8 AS src

COPY --from=builder /tensorflow/tensorflow/lite/tools/pip_package/gen/tflite_pip/python3/dist/tflite_runtime-2.16.1-cp311-cp311-linux_aarch64.whl .

RUN python3 -m pip install tflite_runtime-2.16.1-cp311-cp311-linux_aarch64.whl
RUN python3 -m pip install "numpy<2.0" pillow==10.4.0
RUN rm tflite_runtime-2.16.1-cp311-cp311-linux_aarch64.whl

RUN apk add --no-cache binutils
RUN find / -name '*.so' | xargs strip -s
RUN pip uninstall -y pip
RUN set -ex && \
    ARCH=$(apk --print-arch) && \
    cd /usr/local/lib/python*/config-*-${ARCH}-linux-musl/ && \
    rm -rf *.o *.a
RUN rm -rf /usr/local/lib/python*/ensurepip
RUN rm -rf /usr/local/lib/python*/idlelib
RUN rm -rf /usr/local/lib/python*/distutils/command
RUN rm -rf /usr/local/lib/python*/lib2to3

# RUN rm -rf /usr/local/lib/python*/site-packages
RUN rm -rf /usr/local/lib/python*/pydoc_data
RUN rm -rf /usr/local/lib/python*/asyncio/__pycache__/*
RUN rm -rf /usr/local/lib/python*/*/__pycache__/*

RUN rm -rf /usr/local/lib/python*/__pycache__/*
RUN find /usr/local/include/python* -not -name pyconfig.h -type f -exec rm {} \;
RUN find /usr/local/bin -not -name 'python*' \( -type f -o -type l \) -exec rm {} \;
RUN rm -rf /usr/local/share/*
RUN apk del binutils

FROM alpine:3.19.4@sha256:e910e9408f39003d77ec0f83b18c8892d6899c0a8d4d53f35a67596c33ebfa1d AS final

ENV LANG=C.UTF-8
RUN apk add --no-cache libbz2 expat libffi xz-libs sqlite-libs readline
COPY --from=src /usr/local/ /usr/local/

COPY --from=builder /usr/lib/libstdc++.so.6.0.32 /usr/lib/libstdc++.so.6.0.32
RUN ln -s /usr/lib/libstdc++.so.6.0.32 /usr/lib/libstdc++.so.6
COPY --from=builder /usr/lib/libgcc_s.so.1 /usr/lib/libgcc_s.so.1

WORKDIR /usr/src/app
COPY server.py .
COPY fn.py .
COPY multiclass.tflite .

CMD ["python3", "server.py"]
