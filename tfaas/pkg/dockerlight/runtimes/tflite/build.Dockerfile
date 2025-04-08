ARG PYTHON_VERSION=3.11
ARG DEBIAN_VERSION=slim-bookworm

FROM python:${PYTHON_VERSION}-${DEBIAN_VERSION} AS final

ENV LANG=C.UTF-8

RUN python3 -m pip install "numpy<2.0" pillow==10.4.0 tflite-runtime==2.14.0

WORKDIR /usr/src/app
COPY functionhandler.py .

FROM final AS final-amd64

FROM final AS final-arm64
