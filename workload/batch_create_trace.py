#!/usr/bin/env python3

import PIL
import batch_config

import os
import glob
import pickle
import numpy as np
import math
from shapely.geometry import Polygon
import geopandas as gpd
import matplotlib.pyplot as plt
import tqdm


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


NIGHT_DATA = np.load(batch_config.NIGHT_DATA)["data"]


def get_random_night_image(g, image_shape):
    x = int(g[0] * g[1]) % (
        NIGHT_DATA.shape[1]
        - (
            image_shape[1]
            // (batch_config.VIIRS_RESOLUTION_M // batch_config.RESOLUTION_M)
        )
    )

    y = int(g[0] * g[2]) % (
        NIGHT_DATA.shape[0]
        - (
            image_shape[0]
            // (batch_config.VIIRS_RESOLUTION_M // batch_config.RESOLUTION_M)
        )
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


def find_intersecting_polygons_optimized(gdf, target_polygon):
    # Create bounding box for quick filtering
    possible_matches_index = list(gdf.sindex.intersection(target_polygon.bounds))
    possible_matches = gdf.iloc[possible_matches_index]

    # Now filter the possible matches with actual intersection check
    intersecting_polygons = possible_matches[
        possible_matches.geometry.intersects(target_polygon)
    ]

    return intersecting_polygons


def get_random_sea_tile(width, height):
    available_tiles = glob.glob(
        os.path.join(batch_config.OCEAN_TILE_OUTPUT_DIR, "data-*.npz")
    )

    if len(available_tiles) == 0:
        raise Exception("No ocean tiles available")

    tile = np.zeros((width, height, 13))

    tile_height_filled = 0

    while tile_height_filled < height:
        tile_width_filled = 0

        while tile_width_filled < width:
            tile_id = (width + height + tile_width_filled + tile_height_filled) % len(
                available_tiles
            )

            tile_data = np.load(available_tiles[tile_id])["data"]

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


def load_tile(tile_id, tile):
    t_path = os.path.join(batch_config.TILE_OUTPUT_DIR, f"data-{tile_id}.npz")

    data = np.load(t_path)["data"]

    if data.shape == (1, 1, 13):
        # print(f"tile {tile_id} only has placeholder data")
        width = int(
            distance_m(
                (tile["geometry"].bounds[0], tile["geometry"].bounds[1]),
                (tile["geometry"].bounds[0], tile["geometry"].bounds[3]),
            )
            // batch_config.RESOLUTION_M
        )
        height = int(
            distance_m(
                (tile["geometry"].bounds[0], tile["geometry"].bounds[1]),
                (tile["geometry"].bounds[2], tile["geometry"].bounds[1]),
            )
            // batch_config.RESOLUTION_M
        )

        data = get_random_sea_tile(width, height)

    return data


def plot_tiles(tiles, image, output_file):
    fig, ax = plt.subplots(
        figsize=(10, 10),
    )

    print(f"plotting {len(tiles)} tiles")

    def _plot_box(box, color, text):
        plt.plot(
            [box[0], box[2]],
            [box[1], box[1]],
            color=color,
        )
        plt.plot(
            [box[0], box[2]],
            [box[3], box[3]],
            color=color,
        )
        plt.plot(
            [box[0], box[0]],
            [box[1], box[3]],
            color=color,
        )
        plt.plot(
            [box[2], box[2]],
            [box[1], box[3]],
            color=color,
        )
        plt.text(
            box[0] + (box[2] - box[0]) / 2,
            box[1] + (box[3] - box[1]) / 2,
            text,
            fontsize=20,
            ha="center",
            va="center",
            color=color,
        )

    for tile_id, tile in tiles:
        _plot_box(tile.geometry.bounds, "red", tile_id)

    print("plotting image")
    _plot_box(image.bounds, "blue", "image")

    plt.savefig(output_file, dpi=100, bbox_inches="tight", pad_inches=0.1)
    plt.close()


def world_to_pixel(coords, bbox, shape):
    xmin, ymin, xmax, ymax = bbox
    col = (coords[0] - xmin) / (xmax - xmin)
    row = (ymax - coords[1]) / (ymax - ymin)

    print(
        f"in tile with bbox {bbox}, pixel {coords} is at {row}, {col} ({round(row * shape[0])}, {round(col * shape[1])})"
    )

    return round(col * shape[1]), round(row * shape[0])


def get_image(g, swath_width_m, source_tiles):
    image = None

    image_shape = (
        swath_width_m // batch_config.RESOLUTION_M,
        swath_width_m // batch_config.RESOLUTION_M,
        13,
    )

    if not is_sunlit(g):
        # print(f"getting night image for {g}")
        return get_random_night_image(g, image_shape)

    image_polygon = Polygon(
        [
            add_m_to_lon_lat(g[0], g[1], -swath_width_m / 2, -swath_width_m / 2),
            add_m_to_lon_lat(g[0], g[1], swath_width_m / 2, -swath_width_m / 2),
            add_m_to_lon_lat(g[0], g[1], swath_width_m / 2, swath_width_m / 2),
            add_m_to_lon_lat(g[0], g[1], -swath_width_m / 2, swath_width_m / 2),
        ]
    )

    needed_tiles = find_intersecting_polygons_optimized(source_tiles, image_polygon)

    image = np.zeros(image_shape)

    for tile_id, tile in needed_tiles.iterrows():
        tile_data = load_tile(tile_id, tile)

        # get the bounding box of the intersection
        intersection = tile["geometry"].intersection(image_polygon)

        print(f"image: {image_polygon.bounds}")
        print("tile: ", tile["geometry"].bounds)
        print(f"intersection: {intersection.bounds}")

        print(
            f"intersection width {distance_m((intersection.bounds[0], intersection.bounds[1]), (intersection.bounds[2], intersection.bounds[1]))}"
        )
        print(
            f"intersection height {distance_m((intersection.bounds[0], intersection.bounds[1]), (intersection.bounds[0], intersection.bounds[3]))}"
        )
        print(
            f"tile resolution vertical = {distance_m((tile["geometry"].bounds[0], tile['geometry'].bounds[1]), (tile['geometry'].bounds[0], tile['geometry'].bounds[3])) / tile_data.shape[0]}"
        )
        print(
            f"tile resolution horizontal = {distance_m((tile["geometry"].bounds[0], tile['geometry'].bounds[1]), (tile['geometry'].bounds[2], tile['geometry'].bounds[1])) / tile_data.shape[1]}"
        )

        print(f"tile shape {tile_data.shape}")

        area_tile = (
            world_to_pixel(
                (intersection.bounds[0], intersection.bounds[1]),
                tile["geometry"].bounds,
                tile_data.shape,
            ),
            world_to_pixel(
                (intersection.bounds[2], intersection.bounds[3]),
                tile["geometry"].bounds,
                tile_data.shape,
            ),
        )

        area_image = (
            world_to_pixel(
                (intersection.bounds[0], intersection.bounds[1]),
                image_polygon.bounds,
                image.shape,
            ),
            world_to_pixel(
                (intersection.bounds[2], intersection.bounds[3]),
                image_polygon.bounds,
                image.shape,
            ),
        )

        t_x_start = min((area_tile[0][0], area_tile[1][0]))
        t_x_end = max((area_tile[0][0], area_tile[1][0]))
        t_y_start = min((area_tile[0][1], area_tile[1][1]))
        t_y_end = max((area_tile[0][1], area_tile[1][1]))

        i_x_start = min((area_image[0][0], area_image[1][0]))
        i_x_end = min(i_x_start + (t_x_end - t_x_start), image_shape[1])
        i_y_start = min((area_image[0][1], area_image[1][1]))
        i_y_end = min(i_y_start + (t_y_end - t_y_start), image_shape[0])

        if t_x_end - t_x_start > i_x_end - i_x_start:
            print(
                f"{t_x_end - t_x_start} > {i_x_end - i_x_start}, reducing by {t_x_end - t_x_start - i_x_end + i_x_start}"
            )
            t_x_end -= t_x_end - t_x_start - i_x_end + i_x_start

        if t_y_end - t_y_start > i_y_end - i_y_start:
            print(
                f"{t_y_end - t_y_start} > {i_y_end - i_y_start}, reducing by {t_y_end - t_y_start - i_y_end + i_y_start}"
            )
            t_y_end -= t_y_end - t_y_start - i_y_end + i_y_start

        print(f"image: {i_x_start}, {i_x_end}, {i_y_start}, {i_y_end}, {image.shape}")
        print(
            f"tile: {t_x_start}, {t_x_end}, {t_y_start}, {t_y_end}, {tile_data.shape}"
        )

        image[
            i_y_start:i_y_end,
            i_x_start:i_x_end,
        ] = tile_data[
            t_y_start:t_y_end,
            t_x_start:t_x_end,
        ]

        print(tile_id)

    # plot_tiles(
    #     list(needed_tiles.iterrows()),
    #     image_polygon,
    #     os.path.join(batch_config.TRACE_OUTPUT_DIR, f"bbox-{g[3]}.png"),
    # )

    return image


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


def load_tiles(tile_output_dir):
    tiles = {}

    for split_file in glob.glob(os.path.join(tile_output_dir, "tile-*")):
        tile_id = os.path.basename(split_file).split("-")[1]
        with open(split_file, "rb") as f:
            t = pickle.load(f)
            # print(t.geometry)
            tiles[tile_id] = {
                "geometry": t.geometry,
                "tile_id": tile_id,
            }

    gdf_tiles = gpd.GeoDataFrame(tiles.values())
    gdf_tiles.set_geometry("geometry", inplace=True)
    gdf_tiles.index

    return gdf_tiles


def create_image(g, swath_width_m, source_tiles, trace_output_dir):
    image = get_image(g, swath_width_m, source_tiles)

    if image is None:
        return None

    image_name = f"{g[3]}.png"
    # np.savez_compressed(os.path.join(trace_output_dir, data_name), data=image)
    # Image.fromarray(image * 255).save(os.path.join(trace_output_dir, image_name))
    os.makedirs(os.path.join(trace_output_dir, g[3]), exist_ok=True)

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

    for i in range(len(bands)):
        PIL.Image.fromarray(
            np.clip(
                image[:, :, i] * 255,
                0,
                255,
            ).astype(np.uint8)
        ).save(
            os.path.join(trace_output_dir, g[3], f"{g[3]}_{bands[i]}.tiff"),
            format="TIFF",
        )

    # plt.imshow(
    #     np.clip(
    #         (image[:, :, [3, 2, 1]] * 3.5),
    #         0.0,
    #         1.0,
    #     ),
    #     vmin=0,
    #     vmax=1,
    # )

    # plt.savefig(
    #     os.path.join(trace_output_dir, image_name),
    #     dpi=100,
    #     bbox_inches="tight",
    #     pad_inches=0.1,
    # )
    # plt.close()

    return image_name


if __name__ == "__main__":
    # load trace
    gnd_points = read_input_trace(batch_config.INPUT_TRACE_WITH_SL, batch_config.MAX_S)

    # load source tiles
    source_tiles = load_tiles(batch_config.TILE_OUTPUT_DIR)

    os.makedirs(batch_config.TRACE_OUTPUT_DIR, exist_ok=True)

    # go through the trace
    with open(batch_config.TRACE_LOG, "w") as f:
        f.write("t_ms,lon,lat,alt\n")

        last_point = None
        for g in tqdm.tqdm(gnd_points):
            if distance_m(last_point, g) < batch_config.SWATH_WIDTH_M:
                continue

            image_name = create_image(
                g,
                batch_config.SWATH_WIDTH_M,
                source_tiles,
                batch_config.TRACE_OUTPUT_DIR,
            )

            f.write(f"{g[3]},{g[0]},{g[1]},{g[4]}\n")

            last_point = g
