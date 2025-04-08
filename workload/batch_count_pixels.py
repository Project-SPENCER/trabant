#!/usr/bin/env python3

import batch_config

from sentinelhub import SHConfig

config = SHConfig()

config.sh_client_id = batch_config.CLIENT_ID
config.sh_client_secret = batch_config.CLIENT_SECRET
config.sh_base_url = batch_config.CLIENT_SENTINEL_BASE_URL
config.sh_token_url = batch_config.CLIENT_SENTINEL_TOKEN_URL

if not config.sh_client_id or not config.sh_client_secret:
    print(
        "Warning! To use Process API, please provide the credentials (OAuth client ID and client secret)."
    )

import os
import pickle
import tqdm
import glob

from sentinelhub import (
    bbox_to_dimensions,
)


def count_pixels(bbox, resolution_m):
    req_size = bbox_to_dimensions(bbox, resolution=resolution_m)

    return req_size[0] * req_size[1]


def load_split(split_file):
    with open(split_file, "rb") as f:
        area_polygon = pickle.load(f)

    return area_polygon


if __name__ == "__main__":
    # step 1: go through the split files
    tiles = []
    for split_file in glob.glob(
        os.path.join(
            batch_config.SPLIT_OUTPUT_DIR, f"split-*.{batch_config.SPLIT_OUTPUT_EXT}"
        )
    ):
        if not split_file.endswith(batch_config.SPLIT_OUTPUT_EXT):
            continue

        split_polygons = load_split(split_file)

        # print(split_polygons)

        # elif isinstance(split_polygons, MultiPolygon):
        #     tiles.extend(split_polygons)
        #     continue
        # else:
        #     raise ValueError("Unknown geometry type")
        # # go through the polygons, download the data
        tiles.extend(split_polygons)

    total_pixels = 0

    for tile_id, tile in enumerate(tqdm.tqdm(tiles)):
        total_pixels += count_pixels(tile, batch_config.RESOLUTION_M)

    print(f"Total pixels: {total_pixels}")
