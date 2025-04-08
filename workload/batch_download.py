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
import pickle
import tqdm
import matplotlib.pyplot as plt
import glob

from sentinelhub import (
    bbox_to_dimensions,
    MimeType,
    MosaickingOrder,
    SentinelHubRequest,
)

import cartopy


def is_valid_tile_on_sentinelhub(bbox, resolution_m, start_date, end_date):
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

    # req_bbox = BBox(bbox=bbox, crs=CRS.WGS84)
    req_size = bbox_to_dimensions(bbox, resolution=resolution_m)

    if req_size[0] <= 0 or req_size[1] <= 0:
        print(f"bbox size is invalid: {req_size}")
        return False

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

    if len(response) == 0:
        print("Error downloading tile, empty response")
        return False

    if len(response) > 1:
        print("Error downloading tile, multiple responses")
        return False

    return response[0].any()


def download_from_sentinelhub(bbox, resolution_m, start_date, end_date):
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

    # req_bbox = BBox(bbox=bbox, crs=CRS.WGS84)
    req_size = bbox_to_dimensions(bbox, resolution=resolution_m)

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

    if len(response) == 0:
        print("Error downloading tile, empty response")
        return

    if len(response) > 1:
        print("Error downloading tile, multiple responses")

    return response[0]


def load_split(split_file):
    with open(split_file, "rb") as f:
        area_polygon = pickle.load(f)

    return area_polygon


def exists_data(tile_id, print_func):
    tile_path = os.path.join(batch_config.TILE_OUTPUT_DIR, f"data-{tile_id}.npz")

    if not os.path.exists(tile_path):
        return False

    d = np.load(tile_path)

    if d["data"].shape == (1, 1, 13):
        print_func(f"tile {tile_id} only has placeholder data")
        return False

    return True


def save_file(data, tile, tile_id):
    if data is None:
        data = np.zeros((1, 1, 13))

    np.savez_compressed(
        os.path.join(batch_config.TILE_OUTPUT_DIR, f"data-{tile_id}.npz"), data=data
    )

    with open(
        os.path.join(batch_config.TILE_OUTPUT_DIR, f"tile-{tile_id}.pickleb"), "wb"
    ) as f:
        pickle.dump(tile, f)

    if data.shape != (1, 1, 13):
        plt.imshow(
            np.clip(
                (data[:, :, [3, 2, 1]] * 3.5),
                0.0,
                1.0,
            ),
            vmin=0,
            vmax=1,
        )
    else:
        plt.text(
            0.5, 0.5, "No data", fontsize=20, ha="center", va="center", color="red"
        )

    plt.savefig(
        os.path.join(batch_config.TILE_OUTPUT_DIR, f"image-{tile_id}.png"),
        dpi=100,
        bbox_inches="tight",
        pad_inches=0.1,
    )
    plt.close()

    plot_tile(tile, os.path.join(batch_config.TILE_OUTPUT_DIR, f"bbox-{tile_id}.png"))


def plot_tile(tile, output_file):
    fig, ax = plt.subplots(
        figsize=(10, 10),
        subplot_kw={"projection": cartopy.crs.PlateCarree()},
    )

    ax.add_feature(
        cartopy.feature.BORDERS, linestyle="-", alpha=1, edgecolor=("#FFFFFF")
    )
    ax.add_feature(cartopy.feature.LAND, facecolor=("#d4d4d4"))
    ax.gridlines()

    ax.add_geometries(
        [tile.geometry],
        crs=cartopy.crs.PlateCarree(),
        facecolor="none",
        edgecolor="red",
        linewidth=2,
    )

    plt.savefig(output_file, dpi=100, bbox_inches="tight", pad_inches=0.1)
    plt.close()


# def save_proc(q):
#     while True:
#         data, tile, tile_id = q.get()

#         if data is None and tile is None and tile_id is None:
#             break

#         try:
#             save_file(data, tile, tile_id)
#         except Exception as e:
#             print(f"could not save tile: {e}")


if __name__ == "__main__":
    os.makedirs(batch_config.TILE_OUTPUT_DIR, exist_ok=True)

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

    # save_queue = mp.SimpleQueue()
    # save_p = mp.Process(target=save_proc, args=(save_queue,))
    # save_p.start()
    with tqdm.tqdm(tiles) as pbar:
        with_data = 0
        without_data = 0

        for tile_id, tile in enumerate(pbar):
            pbar.set_postfix_str(
                f"Have data: {(with_data/max(1, with_data+without_data))*100:.2f}%"
            )

            if exists_data(tile_id, pbar.write):
                continue

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
                    save_file(None, tile, tile_id)

                t2 = time.time()

                time.sleep(max(0, 2 - (t2 - t1)))

            except Exception as e:
                print(f"could not download tile {tile_id}: {e}")
