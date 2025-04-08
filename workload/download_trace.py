#!/usr/bin/env python3

import multiprocessing
import time
import zipfile
import batch_config
import PIL
import os
import glob
import numpy as np
import math
from shapely.geometry import Polygon
import matplotlib.pyplot as plt
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


def download_from_sentinelhub(bbox, req_size, start_date, end_date):
    evalscript = """
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


def get_random_night_image(g, image_shape):
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


def get_random_sea_tile(g, image_shape):
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


def get_image(g, swath_width_m):
    image_shape = (
        swath_width_m // batch_config.RESOLUTION_M,
        swath_width_m // batch_config.RESOLUTION_M,
        13,
    )

    if not is_sunlit(g):
        # print(f"getting night image for {g}")
        print(f"night {g}")
        if DEBUG:
            return None
        return get_random_night_image(g, image_shape)

    image_polygon = Polygon(
        [
            add_m_to_lon_lat(g[0], g[1], -swath_width_m / 2, -swath_width_m / 2),
            add_m_to_lon_lat(g[0], g[1], swath_width_m / 2, -swath_width_m / 2),
            add_m_to_lon_lat(g[0], g[1], swath_width_m / 2, swath_width_m / 2),
            add_m_to_lon_lat(g[0], g[1], -swath_width_m / 2, swath_width_m / 2),
        ]
    )

    area_gdf = gpd.GeoDataFrame(index=[0], crs="EPSG:4326", geometry=[image_polygon])

    full_geometry = Geometry(area_gdf.geometry.values[0], crs=CRS.WGS84)

    bbox = full_geometry.bbox

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
            print(f"extended {g}")
            if DEBUG:
                return None

            return download_from_sentinelhub(
                bbox,
                (image_shape[0], image_shape[1]),
                batch_config.DATA_START_DATE_EXTENDED,
                batch_config.DATA_END_DATE,
            )

        print(f"ocean {g}")
        if DEBUG:
            return None
        return get_random_sea_tile(g, image_shape)

    print(f"normal {g}")
    if DEBUG:
        return None

    return download_from_sentinelhub(
        bbox,
        (image_shape[0], image_shape[1]),
        batch_config.DATA_START_DATE_NORMAL,
        batch_config.DATA_END_DATE,
    )


def save_image(image, name, trace_output_dir):
    # image = get_image(g, swath_width_m)

    if image is None:
        return

    print(f"saving {name}")

    bands = [
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
        "CLD",
    ]

    tmp = "tmp.tiff"
    with zipfile.ZipFile(os.path.join(trace_output_dir, f"{name}.zip"), "x") as z:
        for i in range(len(bands)):
            i_name = f"{name}_{bands[i]}.tiff"
            with open(tmp, "wb") as f:
                PIL.Image.fromarray(
                    image[:, :, i],
                ).save(
                    f,
                    format="TIFF",
                )

            z.write(tmp, i_name)

    plt.imshow(image[:, :, [3, 2, 1]] / 255.0 * 2.5)

    plt.savefig(
        os.path.join(trace_output_dir, f"{name}.png"),
        dpi=100,
        bbox_inches="tight",
        pad_inches=0.1,
    )
    plt.close()

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


if __name__ == "__main__":
    # load trace
    gnd_points = read_input_trace(batch_config.INPUT_TRACE_WITH_SL, batch_config.MAX_S)

    os.makedirs(batch_config.TRACE_OUTPUT_DIR, exist_ok=True)

    image_queue = multiprocessing.Queue()

    # start a process to save the images
    save_procs = []
    for i in range(NUM_SAVE_PROCS):
        p = multiprocessing.Process(
            target=save_queue, args=(image_queue, batch_config.TRACE_OUTPUT_DIR)
        )
        p.start()
        save_procs.append(p)

    # go through the trace
    with open(batch_config.TRACE_LOG, "w") as f:
        f.write("t_ms,lon,lat,alt\n")

        last_point = None
        for g in tqdm.tqdm(gnd_points):
            # for g in gnd_points:
            if distance_m(last_point, g) < batch_config.SWATH_WIDTH_M:
                continue

            image_name = g[3]

            # check if the file exists
            if not os.path.exists(
                os.path.join(batch_config.TRACE_OUTPUT_DIR, f"{image_name}.zip")
            ):
                try:
                    image = get_image(
                        g,
                        batch_config.SWATH_WIDTH_M,
                    )

                    print(f"image shape: {image.shape}")
                    print(f"image dtype: {image.dtype}")

                except Exception as e:
                    print(f"could not download image {image_name}: {e}")
                    # in almost all cases, download failing is because we hit the quota
                    # just restart the script with new parameters
                    traceback.print_exc()
                    break

                # save_image(image)
                image_queue.put((image, image_name))

                for p in save_procs:
                    if not p.is_alive():
                        print("save process died")
                        break

            f.write(f"{g[3]},{g[0]},{g[1]},{g[4]}\n")

            last_point = g

    for p in save_procs:
        image_queue.put((None, None))

    for p in save_procs:
        p.join()
