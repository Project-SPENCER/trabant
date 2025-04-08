FROM python:3.11-bookworm@sha256:fd7aa06eae0869405141ed2c7e7734f77c03e6d1cf7b4b1be308712bc7c94883

ENV LANG=C.UTF-8

RUN python3 -m pip install "numpy<2.0" pillow==10.4.0 tflite-runtime==2.14.0

WORKDIR /usr/src/app
COPY server.py .
COPY fn.py .
COPY multiclass.tflite .

CMD ["python3", "server.py"]
