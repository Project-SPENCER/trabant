#!/usr/bin/env python3

import multiprocessing
import time
import batch_config
import os
import glob
import numpy as np
import math
from shapely.geometry import Polygon
import geopandas as gpd
import tqdm
import traceback

from sentinelhub import (
    MimeType,
    MosaickingOrder,
    SentinelHubRequest,
    CRS,
    Geometry,
)

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

DEBUG = False
NIGHT_DATA = np.load(batch_config.NIGHT_DATA)["data"]
LAST_DOWNLOAD = time.time()
DOWNLOAD_INTERVAL = 0.1
NUM_SAVE_PROCS = 4
RNG = np.random.default_rng(batch_config.RANDOM_SEED)


def has_data(bbox, req_size, start_date, end_date):
    evalscript = """
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
    global LAST_DOWNLOAD
    time.sleep(max(0, DOWNLOAD_INTERVAL - (time.time() - LAST_DOWNLOAD)))

    sentinelhub_request = SentinelHubRequest(
        evalscript=evalscript,
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

    try:
        response = sentinelhub_request.get_data()
    except Exception as e:
        # sorry, this is a weird edge case that happens when we get too close to the dateline
        if "exceeds the limit 1500.00 meters per pixel" in str(e):
            print(f"Error downloading tile, resolution too high: {req_size}")
            return False
        else:
            raise e
    finally:
        LAST_DOWNLOAD = time.time()

    if len(response) == 0:
        print("Error downloading tile, empty response")
        return False

    if len(response) > 1:
        print("Error downloading tile, multiple responses")
        return False

    print(f"response shape: {response[0].shape}")
    print(f"req_size: {req_size}")
    print(f"response sum: {response[0].sum()}")
    print(f"response any: {response[0].any()}")
    print(f"response all: {response[0].all()}")

    return response[0].sum() / (req_size[0] * req_size[1]) > 0.8


def get_cld_band(g, type_of_image, bbox, image_shape):
    evalscript = """
    //VERSION=3
    // Retrieve all bands and cloud coverage
    // See https://docs.sentinel-hub.com/api/latest/evalscript/v3/ for more details
    function setup() {
        return {
            input: [{
                bands: ["CLD"],
            }],
            output: {
                bands: 1,
                sampleType: "UINT8"
            }
        };
    }

    function evaluatePixel(sample) {
        return [
            sample.CLD
        ];
    }
    """

    global LAST_DOWNLOAD
    time.sleep(max(0, DOWNLOAD_INTERVAL - (time.time() - LAST_DOWNLOAD)))

    start_date = (
        batch_config.DATA_START_DATE_NORMAL
        if type_of_image == "normal"
        else batch_config.DATA_START_DATE_EXTENDED
    )

    end_date = batch_config.DATA_END_DATE

    sentinelhub_request = SentinelHubRequest(
        evalscript=evalscript,
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
        size=(image_shape[0], image_shape[1]),
        config=config,
    )

    response = sentinelhub_request.get_data()

    LAST_DOWNLOAD = time.time()

    if len(response) == 0:
        print("Error downloading tile, empty response")
        return

    if len(response) > 1:
        print("Error downloading tile, multiple responses")

    return response[0]


def read_input_trace(input_trace, max_s):
    gnd_points = []
    with open(input_trace, "r") as f:
        for line in f:
            if line.startswith("t"):
                continue

            t, lat, lon, alt, elev, is_sunlit = line.strip().split(",")

            if float(t) >= max_s * 1000:
                break

            try:
                gnd_points.append(
                    (float(lon), float(lat), is_sunlit == "1", t, float(alt))
                )
            except ValueError:
                print(f"Error parsing line: {line}")
                continue

    print(f"Have {len(gnd_points)} ground points")

    return gnd_points


def is_sunlit(g):
    return g[2]


def get_random_night_image(g, bbox, image_shape):
    x = RNG.integers(
        0,
        NIGHT_DATA.shape[1]
        - (
            image_shape[1]
            // (batch_config.VIIRS_RESOLUTION_M // batch_config.RESOLUTION_M)
        )
        + 1,
    )

    y = RNG.integers(
        0,
        NIGHT_DATA.shape[0]
        - (
            image_shape[0]
            // (batch_config.VIIRS_RESOLUTION_M // batch_config.RESOLUTION_M)
        )
        + 1,
    )

    print(f"random night image at {x}, {y}")
    print(f"original dimensions: {(
                    math.ceil(image_shape[0]
                    / (
                        batch_config.VIIRS_RESOLUTION_M
                        // batch_config.RESOLUTION_M
                    ))
                )} x {(
                    math.ceil(image_shape[1]
                    / (
                        batch_config.VIIRS_RESOLUTION_M
                        // batch_config.RESOLUTION_M
                    ))
                )}")

    image = np.repeat(
        np.repeat(
            NIGHT_DATA[
                y : y
                + math.ceil(
                    image_shape[0]
                    / (batch_config.VIIRS_RESOLUTION_M // batch_config.RESOLUTION_M)
                ),
                x : x
                + math.ceil(
                    image_shape[1]
                    / (batch_config.VIIRS_RESOLUTION_M // batch_config.RESOLUTION_M)
                ),
            ],
            batch_config.VIIRS_RESOLUTION_M // batch_config.RESOLUTION_M,
            axis=0,
        ),
        batch_config.VIIRS_RESOLUTION_M // batch_config.RESOLUTION_M,
        axis=1,
    )[0 : image_shape[0], 0 : image_shape[1]]

    print(f"new image dimensions: {image.shape}")

    return image


def add_m_to_lon_lat(lon, lat, dx, dy):
    r_earth = 6371000
    latitude = lat + (dy / r_earth) * (180 / math.pi)
    longitude = lon + (dx / r_earth) * (180 / math.pi) / math.cos(lat * math.pi / 180)

    if longitude > 180:
        # print(f"Longitude {longitude} > 180")
        longitude -= 360
        # print(f"Longitude {longitude}")

    if longitude < -180:
        # print(f"Longitude {longitude} < -180")
        longitude += 360
        # print(f"Longitude {longitude}")

    if latitude > 90:
        # print(f"Latitude {latitude} > 90")
        latitude = 90

    if latitude < -90:
        # print(f"Latitude {latitude} < -90")
        latitude = -90

    return longitude, latitude


def distance_m(p1, p2):
    if p1 is None or p2 is None:
        return np.inf

    # radius of Earth in meters
    R = 6371e3

    # Convert degrees to radians
    lon1 = np.radians(p1[0])
    lat1 = np.radians(p1[1])
    lon2 = np.radians(p2[0])
    lat2 = np.radians(p2[1])

    # Difference in coordinates
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    # Haversine formula
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

    # Distance in meters
    distance = R * c

    return distance


def get_random_sea_tile(g, bbox, image_shape):
    available_tiles = glob.glob(
        os.path.join(batch_config.OCEAN_TILE_OUTPUT_DIR, "data-*.npz")
    )

    if len(available_tiles) == 0:
        raise Exception("No ocean tiles available")

    width = image_shape[0]
    height = image_shape[1]

    tile = np.zeros((width, height, 13), dtype=np.uint8)

    tile_height_filled = 0

    while tile_height_filled < height:
        tile_width_filled = 0

        while tile_width_filled < width:
            tile_data = np.load(RNG.choice(available_tiles))["data"]

            tile_width = tile_data.shape[0]
            tile_height = tile_data.shape[1]

            tile[
                tile_width_filled : tile_width_filled + tile_width,
                tile_height_filled : tile_height_filled + tile_height,
            ] = tile_data[
                : min(tile_width, width - tile_width_filled),
                : min(tile_height, height - tile_height_filled),
            ]

            tile_width_filled += tile_width

        tile_height_filled += tile_height

    return tile


def save_image(image, name, trace_output_dir):
    if image is None:
        return

    print(f"saving {name}")

    np.savez_compressed(os.path.join(trace_output_dir, f"{name}.npz"), data=image)

    return


def save_queue(image_queue, trace_output_dir):
    while True:
        image, name = image_queue.get()

        if image is None and name is None:
            print("save process done")
            break
        try:
            save_image(image, name, trace_output_dir)
        except Exception as e:
            print(f"could not save image {name}: {e}")
            traceback.print_exc()
            raise e

    return


def read_download_log(download_log):
    log = {}
    with open(download_log, "r") as f:
        for line in f:
            image_type = (
                "ocean"
                if line.startswith("ocean")
                else "night"
                if line.startswith("night")
                else "normal"
                if line.startswith("normal")
                else "extended"
                if line.startswith("extended")
                else None
            )

            if image_type is None:
                continue

            image_id = line.strip().split("'")[1]

            log[image_id] = image_type

    return log


def get_bbox_and_image_shape(g):
    image_shape = (
        batch_config.SWATH_WIDTH_M // batch_config.RESOLUTION_M,
        batch_config.SWATH_WIDTH_M // batch_config.RESOLUTION_M,
        13,
    )

    image_polygon = Polygon(
        [
            add_m_to_lon_lat(
                g[0],
                g[1],
                -batch_config.SWATH_WIDTH_M / 2,
                -batch_config.SWATH_WIDTH_M / 2,
            ),
            add_m_to_lon_lat(
                g[0],
                g[1],
                batch_config.SWATH_WIDTH_M / 2,
                -batch_config.SWATH_WIDTH_M / 2,
            ),
            add_m_to_lon_lat(
                g[0],
                g[1],
                batch_config.SWATH_WIDTH_M / 2,
                batch_config.SWATH_WIDTH_M / 2,
            ),
            add_m_to_lon_lat(
                g[0],
                g[1],
                -batch_config.SWATH_WIDTH_M / 2,
                batch_config.SWATH_WIDTH_M / 2,
            ),
        ]
    )

    area_gdf = gpd.GeoDataFrame(index=[0], crs="EPSG:4326", geometry=[image_polygon])

    full_geometry = Geometry(area_gdf.geometry.values[0], crs=CRS.WGS84)

    bbox = full_geometry.bbox

    return bbox, image_shape


def get_type_of_image(image_name, download_log, bbox, image_shape):
    if image_name in download_log:
        return download_log[image_name]

    # have to do manual check
    print(f"manual check for {image_name}")

    if not is_sunlit(g):
        return "night"

    if not has_data(
        bbox,
        (image_shape[0], image_shape[1]),
        batch_config.DATA_START_DATE_NORMAL,
        batch_config.DATA_END_DATE,
    ):
        if has_data(
            bbox,
            (image_shape[0], image_shape[1]),
            batch_config.DATA_START_DATE_EXTENDED,
            batch_config.DATA_END_DATE,
        ):
            return "extended"

        return "ocean"

    return "normal"


if __name__ == "__main__":
    FIX_OUTPUT_DIR = "traces_fixed"

    # load trace
    gnd_points = read_input_trace(batch_config.INPUT_TRACE_WITH_SL, batch_config.MAX_S)

    # load download log
    download_log = read_download_log("download.log")

    os.makedirs(FIX_OUTPUT_DIR, exist_ok=True)

    image_queue = multiprocessing.Queue()

    # start a process to save the images
    save_procs = []
    for i in range(NUM_SAVE_PROCS):
        p = multiprocessing.Process(
            target=save_queue, args=(image_queue, FIX_OUTPUT_DIR)
        )
        p.start()
        save_procs.append(p)

    # go through the trace
    last_point = None
    with open("fix_log.csv", "a") as f:
        for g in tqdm.tqdm(gnd_points):
            if distance_m(last_point, g) < batch_config.SWATH_WIDTH_M:
                continue

            last_point = g

            # figure out if we need to change something
            # if it is in the download log as night, re-read the image
            # if it is in the download log as ocean, re-read the image
            # if it is in the download log as normal and id is smaller than 11088400, re-read the cld band
            # if it is not in the download log, figure out what it is based on normal request
            image_name = g[3]

            # if we have a fixed version of this already, skip
            if os.path.exists(os.path.join(FIX_OUTPUT_DIR, f"{image_name}.npz")):
                continue

            bbox, image_shape = get_bbox_and_image_shape(g)

            type_of_image = get_type_of_image(
                image_name, download_log, bbox, image_shape
            )

            print(f"{image_name} {type_of_image}")

            if type_of_image == "night":
                # re-read the image
                image = get_random_night_image(g, bbox, image_shape)
                f.write(f"night,{image_name}\n")
            elif type_of_image == "ocean":
                # re-read the cld band
                image = get_random_sea_tile(g, bbox, image_shape)
                f.write(f"ocean,{image_name}\n")
            elif type_of_image == "normal" or type_of_image == "extended":
                if int(g[3]) > 11088400:
                    # this is actually a usable image!
                    continue

                try:
                    # re-read the cld band
                    image = get_cld_band(g, type_of_image, bbox, image_shape)
                    f.write(f"{type_of_image},{image_name}\n")
                except Exception as e:
                    print(f"could not download image {image_name}: {e}")
                    # in almost all cases, download failing is because we hit the quota
                    # just restart the script with new parameters
                    traceback.print_exc()
                    break

            else:
                raise ValueError(f"Unknown type of image: {type_of_image}")

            # save_image(image)
            image_queue.put((image, image_name))

            for p in save_procs:
                if not p.is_alive():
                    print("save process died")
                    break

    # signal the save processes to stop
    for p in save_procs:
        image_queue.put((None, None))

    for p in save_procs:
        p.join()
