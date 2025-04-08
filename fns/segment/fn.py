#!/usr/bin/env python3

import os
import numpy as np
import tflite_runtime.interpreter as tflite
from PIL import Image
import traceback
import threading
import typing


class_names = ["Building", "Land", "Road", "Vegetation", "Water", "Unlabeled"]

MODEL_TARGET_SIZE = (512, 512)
MODEL_TARGET_PROB = 0.8
SAVE_SIZE = (256, 256)

CHINA_BBOX = {
    "min_lon": 72.59,
    "min_lat": 17.14,
    "max_lon": 136.05,
    "max_lat": 54.97,
}

thread_local = threading.local()


class model:
    def __init__(self):
        # Load the model
        self.interpreter = tflite.Interpreter(
            model_path="segment.tflite", num_threads=1
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
        # img_array /= 255.0  # Rescale as during training

        self.interpreter.set_tensor(self.input_details[0]["index"], img_array)
        self.interpreter.invoke()
        predictions = self.interpreter.get_tensor(self.output_details[0]["index"])

        predicted_mask = np.argmax(predictions, axis=-1)[
            0
        ]  # Get the predicted class for each pixel

        return predicted_mask


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
    # if not in China, return
    if not (
        CHINA_BBOX["min_lon"] <= lon <= CHINA_BBOX["max_lon"]
        and CHINA_BBOX["min_lat"] <= lat <= CHINA_BBOX["max_lat"]
    ):
        print("not in China")
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
        predicted_mask = thread_local.model.predict_image(img)
    except Exception as e:
        print(f"inference failed: {e}")
        traceback.print_exc()
        raise e

    unique, counts = np.unique(predicted_mask, return_counts=True)
    proportions = dict(zip(unique, counts))

    print(f"proportions: {proportions}")

    print("saving image")
    # save the RGB bands plus the predicted mask

    img = load_image(in_path, ["B04", "B03", "B02"], SAVE_SIZE)

    # add the predicted mask as the fourth channel
    # need to resize the mask to the same size as the RGB bands
    # resize from 512x512 to 256x256
    predicted_mask_resized = predicted_mask[
        :: MODEL_TARGET_SIZE[0] // SAVE_SIZE[0], :: MODEL_TARGET_SIZE[1] // SAVE_SIZE[1]
    ].astype(np.uint8)
    # .reshape(
    # (MODEL_TARGET_SIZE[0] // 2, 2, MODEL_TARGET_SIZE[1] // 2, 2)
    # ).mean(axis=(1, 3))

    img = np.dstack([img, predicted_mask_resized])

    np.save(out_writer, img)
