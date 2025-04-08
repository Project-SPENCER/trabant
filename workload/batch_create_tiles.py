#!/usr/bin/env python3

import pickle
import batch_config

from shapely import unary_union
import os
import geopandas as gpd
import math
import matplotlib.pyplot as plt
import tqdm

from matplotlib.patches import Polygon as PltPolygon
from mpl_toolkits.basemap import (
    Basemap,
)  # Available here: https://github.com/matplotlib/basemap

from sentinelhub import BBoxSplitter, CRS, Geometry, bbox_to_dimensions

import numpy as np
from shapely.geometry import Polygon, MultiLineString, MultiPolygon


def read_input_trace(input_trace, max_s):
    # step 1: build the geometry based on our input file
    gnd_points = []
    with open(input_trace, "r") as f:
        for line in f:
            if line.startswith("t"):
                continue

            t, lat, lon, alt, elev, is_sunlit = line.strip().split(",")

            if float(t) >= max_s * 1000:
                break

            # don't care if its not sunlit
            if not is_sunlit == "1":
                continue

            # if float(t) % 1000 != 0:
            #     continue

            try:
                gnd_points.append((float(lon), float(lat)))
            except ValueError:
                print(f"Error parsing line: {line}")
                continue

    print(f"Have {len(gnd_points)} ground points")

    return gnd_points


def show_splitter(
    splitter, alpha=0.2, area_buffer=0.2, show_legend=False, save_path=None
):
    area_bbox = splitter.get_area_bbox()
    # print(area_bbox)
    minx, miny, maxx, maxy = area_bbox
    lng, lat = area_bbox.middle
    w, h = maxx - minx, maxy - miny
    minx = minx - area_buffer * w
    miny = miny - area_buffer * h
    maxx = maxx + area_buffer * w
    maxy = maxy + area_buffer * h

    fig = plt.figure(figsize=(10, 10))
    ax = fig.add_subplot(111)

    base_map = Basemap(
        projection="mill",
        lat_0=lat,
        lon_0=lng,
        llcrnrlon=minx,
        llcrnrlat=miny,
        urcrnrlon=maxx,
        urcrnrlat=maxy,
        resolution="l",
        epsg=4326,
    )
    base_map.drawcoastlines(color=(0, 0, 0, 0))

    area_shape = splitter.get_area_shape()

    if isinstance(area_shape, Polygon):
        polygon_iter = [area_shape]
        # print("polygon")
    elif isinstance(area_shape, MultiPolygon):
        polygon_iter = area_shape.geoms
        # print("multipolygon")
    else:
        raise ValueError(f"Geometry of type {type(area_shape)} is not supported")

    for polygon in polygon_iter:
        if isinstance(polygon.boundary, MultiLineString):
            # print("multilinestring")
            print(len(polygon.boundary.geoms))
            for linestring in polygon.boundary.geoms:
                ax.add_patch(
                    PltPolygon(
                        np.array(linestring.coords),
                        closed=True,
                        facecolor=(0, 0, 0, 0),
                        edgecolor="red",
                    )
                )
        else:
            # print("linestring")
            ax.add_patch(
                PltPolygon(
                    np.array(polygon.boundary.coords),
                    closed=True,
                    facecolor=(0, 0, 0, 0),
                    edgecolor="red",
                )
            )

    bbox_list = splitter.get_bbox_list()
    info_list = splitter.get_info_list()

    cm = plt.get_cmap("jet", len(bbox_list))
    legend_shapes = []
    for i, bbox in enumerate(bbox_list):
        wgs84_bbox = bbox.transform(CRS.WGS84).get_polygon()

        tile_color = tuple(list(cm(i))[:3] + [alpha])
        ax.add_patch(
            PltPolygon(
                np.array(wgs84_bbox),
                closed=True,
                facecolor=tile_color,
                edgecolor="green",
            )
        )

        if show_legend:
            legend_shapes.append(plt.Rectangle((0, 0), 1, 1, fc=cm(i)))

    if show_legend:
        legend_names = []
        for info in info_list:
            legend_name = "{},{}".format(info["index_x"], info["index_y"])

            for prop in ["grid_index", "tile"]:
                if prop in info:
                    legend_name = "{},{}".format(info[prop], legend_name)

            legend_names.append(legend_name)

        plt.legend(legend_shapes, legend_names)
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path)
    else:
        plt.show()


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


def get_polygon(gnd_points, swadth_width_m):
    shape_extent = math.sqrt(2 * (swadth_width_m**2)) / 2

    shape_polygons = [
        Polygon(
            [
                add_m_to_lon_lat(g[0], g[1], -shape_extent, -shape_extent),
                add_m_to_lon_lat(g[0], g[1], shape_extent, -shape_extent),
                add_m_to_lon_lat(g[0], g[1], shape_extent, shape_extent),
                add_m_to_lon_lat(g[0], g[1], -shape_extent, shape_extent),
            ]
        )
        for g in gnd_points
    ]

    # print(f"Have {len(shape_polygons)} polygons")

    polygon = unary_union(shape_polygons)

    # Create a convex hull around the combined polygons
    # convex_hull_polygon = polygon.convex_hull

    # Create a new GeoDataFrame to store the convex hull
    # area_gdf = gpd.GeoDataFrame(
    #     geometry=[convex_hull_polygon],
    #     crs="EPSG:4326",
    # )

    # print(f"type of polygon: {type(polygon)}")
    # print(f"area of polygon: {polygon.area}")

    return polygon


def split_points(polygon, resolution_m):
    # Create a GeoDataFrame
    area_gdf = gpd.GeoDataFrame(index=[0], crs="EPSG:4326", geometry=[polygon])

    # area_gdf.plot()
    # plt.show()
    # plt.savefig("sentinel_batch_area.png")
    full_geometry = Geometry(area_gdf.geometry.values[0], crs=CRS.WGS84)

    # tile_bbox_list = tile_splitter.get_bbox_list()
    # print(tile_bbox_list)
    earth_circle_m = 40075000
    earth_circle_deg = 360

    bbox = full_geometry.bbox

    deg_per_m = earth_circle_deg / earth_circle_m
    max_download_px = 2500
    max_m = max_download_px * resolution_m
    max_deg = (max_m * deg_per_m) * 0.95  # 0.95 to be safe

    max_shape_lat = math.ceil(abs(bbox.max_y - bbox.min_y) / max_deg)
    max_shape_lon = math.ceil(abs(bbox.max_x - bbox.min_x) / max_deg)

    # print(
    #     f"Extent of area: lateral {abs(bbox.max_y - bbox.min_y)}, lon {abs(bbox.max_x - bbox.min_x)}"
    # )

    max_shape = (max_shape_lat, max_shape_lon)

    # print(
    #     f"Max download size: {max_deg} degrees at {max_m} meters (max shape {max_shape})"
    # )

    # print("starting bbox splitter")
    # t1 = time.perf_counter()
    bbox_splitter_reduced = BBoxSplitter(
        [full_geometry], CRS.WGS84, split_shape=max_shape, reduce_bbox_sizes=True
    )

    # print(f"done bbox splitter in {time.perf_counter() - t1} seconds")
    # print(f"Have {len(bbox_splitter_reduced.get_bbox_list())} bboxes")

    # longest_tile_size = 0
    # highest_tile_size = 0

    # for t in bbox_splitter_reduced.get_bbox_list():
    #     width = abs(t.max_x - t.min_x)
    #     height = abs(t.max_y - t.min_y)
    #     if width > longest_tile_size:
    #         longest_tile_size = width

    #     if height > highest_tile_size:
    #         highest_tile_size = height

    # print(
    #     f"longest tile size: {longest_tile_size}, highest tile size: {highest_tile_size}"
    # )

    # print(SentinelHubBatch.tiling_grid(
    #         grid_id=GRID_ID, resolution=RESOLUTION_M, buffer=(50, 50)
    #     ))

    bboxes = bbox_splitter_reduced.get_bbox_list()
    new_bboxes = []

    # go through them and split them if they are too big
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
            # print(
            #     f"Splitting {bbox_size} into {horizontal_split_count}x{vertical_split_count} bboxes"
            # )

        else:
            new_bboxes.append(bbox)

    return new_bboxes


def save_split(bbox_splitter, output_file):
    # gdr = gpd.GeoDataFrame({"geometry": bbox_splitter.get_bbox_list()})

    # gdr.to_file(output_file, driver=driver)  # , crs="EPSG:4326")
    with open(output_file, "wb") as f:
        pickle.dump(bbox_splitter, f)


def save_polygon(area_polygon, output_file):
    with open(output_file, "wb") as f:
        pickle.dump(area_polygon, f)


if __name__ == "__main__":
    gnd_points = read_input_trace(
        batch_config.INPUT_TRACE_WITH_SL, max_s=batch_config.MAX_S
    )

    # step 2: build the bounding box based on the geometry
    os.makedirs(batch_config.SPLIT_OUTPUT_DIR, exist_ok=True)

    total_bboxes = 0
    total_bbox_area = 0

    for i in tqdm.trange(0, len(gnd_points), batch_config.MAX_POINTS_TO_COMBINE):
        area_polygon = get_polygon(
            gnd_points[i : i + batch_config.MAX_POINTS_TO_COMBINE],
            swadth_width_m=batch_config.SWATH_WIDTH_M,
        )

        save_polygon(
            area_polygon,
            os.path.join(
                batch_config.SPLIT_OUTPUT_DIR,
                f"area-{i}.{batch_config.SPLIT_OUTPUT_EXT}",
            ),
        )

        # print(f"Processing points {i} to {i + batch_config.MAX_POINTS_TO_COMBINE}")
        bbox_splitter_reduced_list = split_points(
            area_polygon,
            resolution_m=batch_config.RESOLUTION_M,
        )

        total_bboxes += len(bbox_splitter_reduced_list)

        # print("showing splitter")
        # show_splitter(tile_splitter, show_legend=True)
        # show_splitter(
        #     bbox_splitter_reduced,
        #     show_legend=False,
        #     area_buffer=0.0,
        #     save_path=os.path.join(OUTPUT_DIR, f"split-{i}.png"),
        # )

        save_split(
            bbox_splitter_reduced_list,
            os.path.join(
                batch_config.SPLIT_OUTPUT_DIR,
                f"split-{i}.{batch_config.SPLIT_OUTPUT_EXT}",
            ),
        )

    print(f"Total bboxes: {total_bboxes}")
