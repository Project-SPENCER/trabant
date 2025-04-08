# Based on https://github.com/CrafterKolyan/tiny-python-docker-image licensed
# under MIT License (see LICENSE), in turn based on
# https://github.com/haizaar/docker-python-minimal licensed under Apache 2.0
# License.
ARG PYTHON_VERSION=3.11
ARG ALPINE_VERSION=3.19

FROM python:${PYTHON_VERSION}-alpine${ALPINE_VERSION} AS builder

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

# I added this myself, which removes a further 1MB of files
# not sure if this breaks anything
RUN rm -rf /usr/local/lib/python*/site-packages
RUN rm -rf /usr/local/lib/python*/pydoc_data
RUN rm -rf /usr/local/lib/python*/asyncio/__pycache__/*
RUN rm -rf /usr/local/lib/python*/*/__pycache__/*

RUN rm -rf /usr/local/lib/python*/__pycache__/*
RUN find /usr/local/include/python* -not -name pyconfig.h -type f -exec rm {} \;
RUN find /usr/local/bin -not -name 'python*' \( -type f -o -type l \) -exec rm {} \;
RUN rm -rf /usr/local/share/*
RUN apk del binutils


FROM alpine:${ALPINE_VERSION} AS final

ENV LANG=C.UTF-8
RUN apk add --no-cache libbz2 expat libffi xz-libs sqlite-libs readline
COPY --from=builder /usr/local/ /usr/local/

WORKDIR /usr/src/app
COPY functionhandler.py .

FROM final AS final-amd64

FROM final AS final-arm64
