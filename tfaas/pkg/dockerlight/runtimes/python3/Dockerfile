FROM scratch

ARG RUNTIME_DIR
ADD ${RUNTIME_DIR}/blob.tar.xz /

EXPOSE 8000

# Create app directory
WORKDIR /usr/src/app

ARG FUNC_DIR
COPY ${FUNC_DIR}/fn .

ENV PYTHONUNBUFFERED=1
ENTRYPOINT [ "python3", "functionhandler.py" ]
