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
import time
import numpy as np
import tqdm
import matplotlib.pyplot as plt
import math

import geopandas as gpd
from shapely.geometry import Polygon
from sentinelhub import (
    MimeType,
    MosaickingOrder,
    SentinelHubRequest,
    BBoxSplitter,
    CRS,
    Geometry,
    bbox_to_dimensions,
)


def is_valid_tile_on_sentinelhub(bbox, resolution_m, start_date, end_date):
    evalscript_true_color = """
    //VERSION=3
    function setup() {
        return {
            input: ["dataMask"],
            output: {
                bands: 1,
                sampleType: "UINT8"
            }
        };
    }

    function evaluatePixel(sample) {
        return [sample.dataMask];
    }
    """

    # req_bbox = BBox(bbox=bbox, crs=CRS.WGS84)
    req_size = bbox_to_dimensions(bbox, resolution=resolution_m)

    if req_size[0] <= 0 or req_size[1] <= 0:
        print(f"bbox size is invalid: {req_size}")
        return False

    sentinelhub_request = SentinelHubRequest(
        evalscript=evalscript_true_color,
        input_data=[
            SentinelHubRequest.input_data(
                batch_config.DATA_COLLECTION,
                time_interval=(
                    start_date,
                    end_date,
                ),
                mosaicking_order=MosaickingOrder.MOST_RECENT,
                maxcc=1.0,
            )
        ],
        responses=[
            SentinelHubRequest.output_response("default", MimeType.TIFF),
        ],
        bbox=bbox,
        size=req_size,
        config=config,
    )

    response = sentinelhub_request.get_data()

    if len(response) == 0:
        print("Error downloading tile, empty response")
        return False

    if len(response) > 1:
        print("Error downloading tile, multiple responses")
        return False

    return response[0].any()


def download_from_sentinelhub(bbox, resolution_m, start_date, end_date):
    evalscript_true_color = """
    //VERSION=3
    // Retrieve all bands and cloud coverage
    // See https://docs.sentinel-hub.com/api/latest/evalscript/v3/ for more details
    function setup() {
        return {
            input: [{
                bands: ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B09", "B11", "B12", "CLD"],
            }],
            output: {
                bands: 13,
                sampleType: "UINT8"
            }
        };
    }

    function evaluatePixel(sample) {
        return [
            sample.B01 * 255,
            sample.B02 * 255,
            sample.B03 * 255,
            sample.B04 * 255,
            sample.B05 * 255,
            sample.B06 * 255,
            sample.B07 * 255,
            sample.B08 * 255,
            sample.B8A * 255,
            sample.B09 * 255,
            sample.B11 * 255,
            sample.B12 * 255,
            sample.CLD
        ];
    }
    """

    # req_bbox = BBox(bbox=bbox, crs=CRS.WGS84)
    req_size = bbox_to_dimensions(bbox, resolution=resolution_m)

    sentinelhub_request = SentinelHubRequest(
        evalscript=evalscript_true_color,
        input_data=[
            SentinelHubRequest.input_data(
                batch_config.DATA_COLLECTION,
                time_interval=(
                    start_date,
                    end_date,
                ),
                mosaicking_order=MosaickingOrder.MOST_RECENT,
                maxcc=1.0,
            )
        ],
        responses=[
            SentinelHubRequest.output_response("default", MimeType.TIFF),
        ],
        bbox=bbox,
        size=req_size,
        config=config,
    )

    response = sentinelhub_request.get_data()

    if len(response) == 0:
        print("Error downloading tile, empty response")
        return

    if len(response) > 1:
        print("Error downloading tile, multiple responses")

    return response[0]


def save_file(data, tile, tile_id):
    np.savez_compressed(
        os.path.join(batch_config.OCEAN_TILE_OUTPUT_DIR, f"data-{tile_id}.npz"),
        data=data,
    )

    plt.imshow(
        data[:, :, [3, 2, 1]] / 255 * 3.5,
    )

    plt.savefig(
        os.path.join(batch_config.OCEAN_TILE_OUTPUT_DIR, f"image-{tile_id}.png"),
        dpi=100,
        bbox_inches="tight",
        pad_inches=0.1,
    )
    plt.close()


def split_ocean_polygon(bbox, resolution_m):
    polygon = Polygon(bbox)

    area_gdf = gpd.GeoDataFrame(index=[0], crs="EPSG:4326", geometry=[polygon])

    full_geometry = Geometry(area_gdf.geometry.values[0], crs=CRS.WGS84)

    earth_circle_m = 40075000
    earth_circle_deg = 360

    bbox = full_geometry.bbox

    deg_per_m = earth_circle_deg / earth_circle_m
    max_download_px = 2500
    max_m = max_download_px * resolution_m
    max_deg = (max_m * deg_per_m) * 0.95  # 0.95 to be safe

    max_shape_lat = math.ceil(abs(bbox.max_y - bbox.min_y) / max_deg)
    max_shape_lon = math.ceil(abs(bbox.max_x - bbox.min_x) / max_deg)

    max_shape = (max_shape_lat, max_shape_lon)

    bbox_splitter_reduced = BBoxSplitter(
        [full_geometry], CRS.WGS84, split_shape=max_shape, reduce_bbox_sizes=True
    )

    bboxes = bbox_splitter_reduced.get_bbox_list()
    print(f"split into {len(bboxes)} bboxes")

    # go through them and split them if they are too big
    all_ok = False
    while not all_ok:
        new_bboxes = []
        all_ok = True
        for bbox in bboxes:
            if bbox.min_y < -80:
                if bbox.min_y < -80:
                    # this bbox is entirely out of range
                    continue
                bbox.min_y = -80
            if bbox.max_y > 84:
                if bbox.max_y > 84:
                    continue
                bbox.max_y = 84

            bbox_size = bbox_to_dimensions(bbox, resolution=resolution_m)

            if bbox_size[0] > max_download_px or bbox_size[1] > max_download_px:
                all_ok = False
                # split
                horizontal_split_count = math.ceil(bbox_size[0] / max_download_px)
                vertical_split_count = math.ceil(bbox_size[1] / max_download_px)

                new_bbox = BBoxSplitter(
                    [bbox.geometry],
                    CRS.WGS84,
                    split_shape=[horizontal_split_count, vertical_split_count],
                    reduce_bbox_sizes=True,
                )

                new_bboxes.extend(new_bbox.get_bbox_list())

            else:
                # print(f"bbox size {bbox_size} is smaller than {max_download_px}")
                new_bboxes.append(bbox)

        bboxes = new_bboxes
        print(f"split into {len(bboxes)} bboxes")

    return new_bboxes


if __name__ == "__main__":
    os.makedirs(batch_config.OCEAN_TILE_OUTPUT_DIR, exist_ok=True)

    # step 1: go through the split files
    tiles = split_ocean_polygon(batch_config.OCEAN_BBOX, batch_config.RESOLUTION_M)

    with tqdm.tqdm(tiles) as pbar:
        with_data = 0
        without_data = 0

        for tile_id, tile in enumerate(pbar):
            tile_size = bbox_to_dimensions(tile, resolution=batch_config.RESOLUTION_M)
            pbar.write(f"tile {tile_id}, size {tile_size}")
            if tile_size[0] > 2500 or tile_size[1] > 2500:
                pbar.write(f"tile {tile_id} is too big, skipping")
                break

            pbar.set_postfix_str(
                f"Have data: {(with_data/max(1, with_data+without_data))*100:.2f}%"
            )

            try:
                t1 = time.time()
                if is_valid_tile_on_sentinelhub(
                    tile,
                    batch_config.CHECK_RESOLUTION_M,
                    batch_config.DATA_START_DATE_NORMAL,
                    batch_config.DATA_END_DATE,
                ):
                    pbar.write(f"tile {tile_id} contains data! downloading")
                    data = download_from_sentinelhub(
                        tile,
                        batch_config.RESOLUTION_M,
                        batch_config.DATA_START_DATE_NORMAL,
                        batch_config.DATA_END_DATE,
                    )
                    if data is None:
                        pbar.write(f"failed to download {tile_id}")
                        continue

                    with_data += 1
                    save_file(data, tile, tile_id)

                elif is_valid_tile_on_sentinelhub(
                    tile,
                    batch_config.CHECK_RESOLUTION_M,
                    batch_config.DATA_START_DATE_EXTENDED,
                    batch_config.DATA_END_DATE,
                ):
                    pbar.write(
                        f"tile {tile_id} contains data in extended time frame! downloading"
                    )
                    data = download_from_sentinelhub(
                        tile,
                        batch_config.RESOLUTION_M,
                        batch_config.DATA_START_DATE_EXTENDED,
                        batch_config.DATA_END_DATE,
                    )
                    if data is None:
                        pbar.write(f"failed to download {tile_id}")
                        continue

                    with_data += 1
                    save_file(data, tile, tile_id)
                else:
                    pbar.write(f"tile {tile_id} does not contain any data, skipping")
                    without_data += 1

                t2 = time.time()

                time.sleep(max(0, 2 - (t2 - t1)))

            except Exception as e:
                print(f"could not download tile {tile_id}: {e}")
