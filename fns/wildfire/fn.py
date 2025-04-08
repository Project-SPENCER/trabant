#!/usr/bin/env python3

import os
import numpy as np
import tflite_runtime.interpreter as tflite
from PIL import Image
import traceback
import threading
import typing

MODEL_TARGET_SIZE = (350, 350)
MODEL_TARGET_PROB = 0.6
SAVE_SIZE = (256, 256)

thread_local = threading.local()

# This model takes the RGB bands.
# If the wildfire probability is above 0.8, we save the entire image using all 12 bands.


class model:
    def __init__(self):
        # Load the model
        self.interpreter = tflite.Interpreter(
            model_path="wildfire.tflite", num_threads=1
        )
        self.interpreter.allocate_tensors()
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()

    # Function to predict the class of an image
    def predict_image(self, img):
        print(img.shape, img.dtype)
        img_array = np.expand_dims(img, axis=0)  # Create a batch of 1
        # convert from uint8 to np.float32
        img_array = img_array.astype(np.float32) / 255.0

        self.interpreter.set_tensor(self.input_details[0]["index"], img_array)
        self.interpreter.invoke()
        predictions = self.interpreter.get_tensor(self.output_details[0]["index"])
        return predictions[0][0]


def load_image(img_path, bands, target_size):
    imgs = []

    for b in bands:
        path = os.path.join(img_path, f"{b}.tiff")

        # load image and resize it to target size
        img = Image.open(path)
        img = img.resize(target_size)
        img_array = np.array(img)

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
        wildfire_prob = thread_local.model.predict_image(img)
    except Exception as e:
        print(f"inference failed: {e}")
        traceback.print_exc()
        raise e

    print(f"wildfire probability: {wildfire_prob}")

    if not wildfire_prob >= MODEL_TARGET_PROB:
        print(f"skipping: {wildfire_prob} < {MODEL_TARGET_PROB}")
        return

    print("saving image")
    img = load_image(
        in_path,
        [
            "B01",
            "B02",
            "B03",
            "B04",
            "B05",
            "B06",
            "B07",
            "B08",
            "B8A",
            "B09",
            "B11",
            "B12",
        ],
        SAVE_SIZE,
    )
    # Image.fromarray(img).save(out_writer, format="TIFF")
    np.save(out_writer, img)
