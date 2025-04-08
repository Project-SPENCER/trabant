#!/usr/bin/env python3

import os
import numpy as np
import tflite_runtime.interpreter as tflite
from PIL import Image
import traceback
import threading
import typing

classes = [
    "Complex cultivation patterns",
    "Burnt areas",
    "Port areas",
    "Coastal lagoons",
    "Land principally occupied by agriculture, with significant areas of natural vegetation",
    "Mixed forest",
    "Sclerophyllous vegetation",
    "Mineral extraction sites",
    "Water courses",
    "Sparsely vegetated areas",
    "Dump sites",
    "Industrial or commercial units",
    "Annual crops associated with permanent crops",
    "Intertidal flats",
    "Natural grassland",
    "Water bodies",
    "Continuous urban fabric",
    "Rice fields",
    "Road and rail networks and associated land",
    "Olive groves",
    "Vineyards",
    "Permanently irrigated land",
    "Transitional woodland/shrub",
    "Pastures",
    "Salines",
    "Broad-leaved forest",
    "Agro-forestry areas",
    "Peatbogs",
    "Bare rock",
    "Discontinuous urban fabric",
    "Construction sites",
    "Coniferous forest",
    "Moors and heathland",
    "Non-irrigated arable land",
    "Airports",
    "Fruit trees and berry plantations",
    "Sport and leisure facilities",
    "Inland marshes",
    "Green urban areas",
    "Sea and ocean",
    "Salt marshes",
    "Estuaries",
    "Beaches, dunes, sands",
]

target_classes = [
    "Complex cultivation patterns",
    "Land principally occupied by agriculture, with significant areas of natural vegetation",
    "Annual crops associated with permanent crops",
    "Rice fields",
    "Olive groves",
    "Vineyards",
    "Pastures",
    "Agro-forestry areas",
    "Fruit trees and berry plantations",
]

thread_local = threading.local()


class model:
    def __init__(self):
        # Load the model
        self.interpreter = tflite.Interpreter(
            model_path="multiclass.tflite", num_threads=1
        )
        self.interpreter.allocate_tensors()
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()

    # Function to predict the class of an image
    def predict_image(self, img_array):
        # print(img.shape, img.dtype)
        # img_array = np.expand_dims(img, axis=0)  # Create a batch of 1
        # convert from uint8 to np.float32
        # img_array = img_array.astype(np.float32) / 255.0
        # img_array /= 255.0  # Rescale as during training

        # print(self.input_details)

        self.interpreter.set_tensor(self.input_details[0]["index"], img_array[2])
        self.interpreter.set_tensor(self.input_details[1]["index"], img_array[0])
        self.interpreter.set_tensor(self.input_details[2]["index"], img_array[1])

        self.interpreter.invoke()
        predictions = self.interpreter.get_tensor(self.output_details[0]["index"])

        predicted_labels = (predictions > 0.5).astype(int)

        predicted_classes = [
            classes[i] for i, val in enumerate(predicted_labels[0]) if val == 1
        ]

        return predicted_classes


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

        imgs.append(img_array.astype(np.float32) / 255.0)

    return np.expand_dims(np.squeeze(np.stack(imgs, axis=-1)), axis=0)


def fn(
    lat: float,
    lon: float,
    alt: float,
    clouds: float,
    sunlit: bool,
    in_path: str,
    out_writer: typing.BinaryIO,
) -> None:
    # From the README:
    # - Dataset: The model was trained on the \textbf{BigEarth} dataset, which consists of satellite images with 12 bands representing various spectral data. The bands are structured as follows:
    #     - 2 bands of size 20x20 pixels (B01, B09)
    #     - 6 bands of size 60x60 pixels (B05, B06, B07, B8A, B11, B12)
    #     - 4 bands of size 120x120 pixels (B02, B03, B04, B08)

    # These bands provide different resolutions and spectral information,
    # making the dataset highly versatile for multilabel classification tasks.

    # - Input:
    #     - Input 1: shape=(20, 20, 2) - 2 channels for B01, B09
    #     - Input 2: shape=(60, 60, 6) - 6 channels for B05, B06, B07, B8A, B11, B12
    #     - Input 3: shape=(120, 120, 4) - 4 channels for B02, B03, B04, B08
    try:
        img = [
            load_image(
                in_path,
                [
                    "B01",
                    "B09",
                ],
                (20, 20),
            ),
            load_image(
                in_path,
                [
                    "B05",
                    "B06",
                    "B07",
                    "B8A",
                    "B11",
                    "B12",
                ],
                (60, 60),
            ),
            load_image(
                in_path,
                [
                    "B02",
                    "B03",
                    "B04",
                    "B08",
                ],
                (120, 120),
            ),
        ]

    except Exception as e:
        print(f"failed to load image: {e}")
        traceback.print_exc()
        raise e

    # check that there is a model local to this thread
    if not hasattr(thread_local, "model"):
        thread_local.model = model()

    try:
        predicted_classes = thread_local.model.predict_image(img)
    except Exception as e:
        print(f"inference failed: {e}")
        traceback.print_exc()
        raise e

    print(f"predicted classes: {predicted_classes}")

    if not len(predicted_classes) == 0 and not any(
        c in predicted_classes for c in target_classes
    ):
        print(
            f"skipping: {predicted_classes} does not contain any target classes {target_classes}"
        )
        return

    print("saving image")
    # https://www.mdpi.com/2073-4395/13/3/656
    # apparently Red Edge 3 (B07), NIR (B08), and SWIR 1 (B11) are the most important bands for soil moisture
    img = load_image(
        in_path,
        [
            "B02",
            "B03",
            "B04",
            "B07",
            "B08",
            "B11",
        ],
        (256, 256),
    )
    np.save(out_writer, img)
