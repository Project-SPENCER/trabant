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

    img = img.resize((width // 2, height // 2))

    img.save(out_writer, format="PNG")
