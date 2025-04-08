#!/usr/bin/env python3

import os
import numpy as np
import tflite_runtime.interpreter as tflite
from PIL import Image
import traceback
import threading
import typing

MODEL_TARGET_SIZE = (512, 512)
MODEL_TARGET_PROB = 0.8
SAVE_SIZE = (256, 256)

thread_local = threading.local()

# This model detects boats.
# If a boat is detected with a probability above 0.8, we save the image (RGB bands) as a PNG.


class model:
    def __init__(self):
        # Load the model
        self.interpreter = tflite.Interpreter(model_path="vessel.tflite", num_threads=1)
        self.interpreter.allocate_tensors()
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()

    # Function to predict the class of an image
    def predict_image(self, img):
        print(img.shape, img.dtype)
        img_array = np.expand_dims(img, axis=0)  # Create a batch of 1
        # convert from uint8 to np.float32
        img_array = img_array.astype(np.float32) / 255.0
        # img_array /= 255.0  # Rescale as during training

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
    # vessel detection is easily confused by clouds
    if clouds > 0.01:
        print(f"skipping: {clouds} > 0.01")
        return

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
        boat_prob = thread_local.model.predict_image(img)
    except Exception as e:
        print(f"inference failed: {e}")
        traceback.print_exc()
        raise e

    print(f"boat probability: {boat_prob}")

    if not boat_prob >= MODEL_TARGET_PROB:
        print(f"skipping: {boat_prob} < {MODEL_TARGET_PROB}")
        return

    print("saving image")
    img = load_image(in_path, ["B04", "B03", "B02"], SAVE_SIZE)
    # Image.fromarray(img).save(out_writer, format="PNG")
    np.save(out_writer, img)
