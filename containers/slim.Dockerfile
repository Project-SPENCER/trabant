FROM python:3.11-slim-bookworm@sha256:46551c798118948d3bef042dd736ad048e9150056db0fa74625e19dac1b317e2

ENV LANG=C.UTF-8

RUN python3 -m pip install "numpy<2.0" pillow==10.4.0 tflite-runtime==2.14.0

WORKDIR /usr/src/app
COPY server.py .
COPY fn.py .
COPY multiclass.tflite .

CMD ["python3", "server.py"]
