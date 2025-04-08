ARG PYTHON_VERSION=3.11
ARG DEBIAN_VERSION=slim-bookworm

FROM python:${PYTHON_VERSION}-${DEBIAN_VERSION} AS final

ENV LANG=C.UTF-8

RUN python3 -m pip install pillow==10.4.0 tensorflow==2.17.0 matplotlib==3.9.2 scikit-learn==1.5.2

WORKDIR /usr/src/app
COPY functionhandler.py .

FROM final AS final-amd64

FROM final AS final-arm64
