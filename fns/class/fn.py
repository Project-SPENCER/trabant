#!/usr/bin/env python3

import os
import numpy as np
import tflite_runtime.interpreter as tflite
from PIL import Image
import traceback
import threading
import typing

# Define class
class_labels = [
    "AnnualCrop",
    "Forest",
    "Herb.Vegetation",
    "Highway",
    "Industrial",
    "Pasture",
    "PermanentCrop",
    "Residential",
    "River",
    "SeaLake",
]

MODEL_TARGET_CLASS = "Industrial"
MODEL_TARGET_SIZE = (64, 64)
SAVE_SIZE = (256, 256)

thread_local = threading.local()


class model:
    def __init__(self):
        # Load the model
        self.interpreter = tflite.Interpreter(model_path="class.tflite", num_threads=1)
        self.interpreter.allocate_tensors()
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()

    # Function to predict the class of an image
    def predict_image(self, img, class_labels):
        print(img.shape, img.dtype)
        img_array = np.expand_dims(img, axis=0)  # Create a batch of 1
        # convert from uint8 to np.float32
        img_array = img_array.astype(np.float32) / 255.0
        # img_array /= 255.0  # Rescale as during training

        self.interpreter.set_tensor(self.input_details[0]["index"], img_array)
        self.interpreter.invoke()
        predictions = self.interpreter.get_tensor(self.output_details[0]["index"])
        predicted_class = class_labels[np.argmax(predictions)]

        return predicted_class


def load_image(img_path, bands, target_size):
    imgs = []

    for b in bands:
        path = os.path.join(img_path, f"{b}.tiff")

        # load image and resize it to target size
        img = Image.open(path)
        # img = img.convert("RGB")
        img = img.resize(target_size)
        img_array = np.array(img)
        # print(f"band {b}: {img_array.shape}, {img_array.dtype}")

        imgs.append(img_array)

    return np.dstack(imgs)


def fn(
    lat: float,
    lon: float,
    alt: float,
    clouds: float,
    sunlit: bool,
    in_path: str,
    out_writer: typing.BinaryIO,
) -> None:
    # load the image in image_path
    try:
        img = load_image(in_path, ["B04", "B03", "B02"], MODEL_TARGET_SIZE)
    except Exception as e:
        print(f"failed to load image: {e}")
        traceback.print_exc()
        raise e

    # check that there is a model local to this thread
    if not hasattr(thread_local, "model"):
        thread_local.model = model()

    try:
        predicted_class = thread_local.model.predict_image(img, class_labels)
    except Exception as e:
        print(f"inference failed: {e}")
        traceback.print_exc()
        raise e

    print(f"predicted: {predicted_class}")

    if not predicted_class == MODEL_TARGET_CLASS:
        print(f"skipping: {predicted_class}")
        return

    print("saving image")
    # https://amt.copernicus.org/articles/14/2771/2021/
    # adding bands 11 and 12 to monitor methane output
    img = load_image(in_path, ["B02", "B03", "B04", "B11", "B12"], SAVE_SIZE)
    np.save(out_writer, img)
