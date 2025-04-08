#!/usr/bin/env python3

import os
import typing
from PIL import Image  # type: ignore


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
    img = Image.open(os.path.join(in_path, "B03.tiff"))

    width, height = img.size

    print("image size", width, height)

    area = (0, 0, width / 2, height / 2)
    img = img.crop(area)

    print("cropped image size", img.size)

    # Saved in the same relative location
    img.save(out_writer, format="PNG")

    print("saved")
