#!/usr/bin/env python3
import datetime

import tqdm
import numpy as np

import track

# probably the right id
SAT = 55261

# based on this image being identical with the one in the paper, specifying that this is the xingyi ground station in tongchuan
#  http://m.cyol.com/gb/articles/2023-05/10/content_KaA7qjCB7K.html
# location is from https://map.baidu.com/poi/%E4%B8%AD%E5%9B%BD%E9%93%9C%E5%B7%9D%E5%95%86%E4%B8%9A%E8%88%AA%E5%A4%A9%E5%9F%8E%E6%B5%8B%E6%8E%A7%E4%B8%AD%E5%BF%83/@12123061.710616319,4130218.8594030826,14.45z/maptype%3DB_EARTH_MAP?uid=e29e9bbff420cf796d20b903&ugc_type=3&ugc_ver=1&device_ratio=1&compat=1&pcevaname=pc4.1&querytype=detailConInfo&da_src=shareurl
# you can kind of see it from the satellite image
GST_LAT = 34.93124
GST_LON = 108.89153

# our power traces
START_DATE = "2023-04-24 23:34:52Z"
END_DATE = "2023-05-07 19:01:36Z"
# START_DATE = "2023-05-01 00:00:00Z"
# END_DATE = "2023-05-01 06:00:00Z"

RESOLUTION_MS = 1000  # milliseconds

CONTACT_ANGLE = 15  # degrees


def latlon_to_cartesian(lat, lon, h):
    lat = np.radians(lat)
    lon = np.radians(lon)

    # Radius at the surface of the Earth
    # Cartesian coordinates
    x = (track.EARTH_RADIUS_KM + h) * np.cos(lat) * np.cos(lon)
    y = (track.EARTH_RADIUS_KM + h) * np.cos(lat) * np.sin(lon)
    z = (track.EARTH_RADIUS_KM + h) * np.sin(lat)

    return np.array([x, y, z])


def elevation(sat_lat, sat_lon, sat_alt, gs_lat, gs_lon, gs_alt=0):
    # if both lat and lon are the same, the elevation angle is 90
    if gs_lat == sat_lat and gs_lon == sat_lon:
        return 90.0

    # Convert ground station and satellite positions to Cartesian coordinates
    gs_xyz = latlon_to_cartesian(gs_lat, gs_lon, gs_alt)
    sat_xyz = latlon_to_cartesian(sat_lat, sat_lon, sat_alt)

    mag_gs = np.linalg.norm(gs_xyz)
    mag_sat = np.linalg.norm(sat_xyz)

    cos_theta = np.dot(gs_xyz, sat_xyz) / (mag_gs * mag_sat)

    theta = np.arccos(cos_theta)

    a = track.EARTH_RADIUS_KM + sat_alt
    b = track.EARTH_RADIUS_KM + gs_alt
    C = theta

    c = np.sqrt(a**2 + b**2 - 2 * a * b * np.cos(C))

    A = np.arccos((b**2 + c**2 - a**2) / (2 * b * c))

    # if the angle is smaller than 90 degrees, the sat is not visible
    if np.degrees(A) <= 90:
        return 0.0

    return np.degrees(A) - 90


if __name__ == "__main__":
    tle_data = track.load_tle_data(SAT)

    start_dt = datetime.datetime.fromisoformat(START_DATE)
    end_dt = datetime.datetime.fromisoformat(END_DATE)

    i = start_dt

    total_duration = int((end_dt - start_dt).total_seconds() * 1000)

    contact = 0
    total = 0

    with tqdm.tqdm(total=total_duration) as pbar:
        while i < end_dt:
            lat, lon, alt = track.get_position(tle_data, i)

            elev = elevation(lat, lon, alt, GST_LAT, GST_LON)

            if elev > CONTACT_ANGLE:
                contact += RESOLUTION_MS

            total += RESOLUTION_MS

            i += datetime.timedelta(milliseconds=RESOLUTION_MS)

            pbar.update(RESOLUTION_MS)

    print(f"Contact: {contact} ms")
    print(f"Total: {total} ms")
