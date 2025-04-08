#!/usr/bin/env python3

import batch_config

import datetime

import skyfield.api
import tqdm

ts = skyfield.api.load.timescale()
planets = skyfield.api.load("de421.bsp")  # Load the planetary ephemeris
earth, sun = planets["earth"], planets["sun"]


def is_in_sunlight(lat_deg, lon_deg, utc_timestamp):
    t = ts.utc(
        utc_timestamp.year,
        utc_timestamp.month,
        utc_timestamp.day,
        utc_timestamp.hour,
        utc_timestamp.minute,
        utc_timestamp.second,
    )

    observer = earth + skyfield.api.Topos(
        latitude_degrees=lat_deg, longitude_degrees=lon_deg
    )
    astrometric = observer.at(t).observe(sun)
    alt, az, d = astrometric.apparent().altaz()

    # The sun is above the horizon if the altitude is greater than 0
    # observer = skyfield.api.wgs84.latlon(lat_deg, lon_deg)
    # return observer.at(t).is_sunlit(planets)

    return alt.degrees > 0


if __name__ == "__main__":
    total_pnts = 0
    sunlit_pnts = 0

    start_time = None

    with open(batch_config.INPUT_TRACE, "r") as f:
        # parse time_ms_since_1682379292000 line
        line = f.readline()
        start_time = int(line.strip().split(",")[0][len("time_ms_since_") :])

    with open(batch_config.INPUT_TRACE, "r") as f:
        with open(batch_config.INPUT_TRACE_WITH_SL, "w") as f_sl:
            f_sl.write(line.strip() + ",is_sunlit\n")
            for line in tqdm.tqdm(f):
                if line.startswith("t"):
                    continue

                t, lat, lon, alt, elev = line.strip().split(",")

                if int(t) >= batch_config.MAX_S * 1000:
                    break

                ts_ms = int(t) + start_time
                lat_deg = float(lat)
                lon_deg = float(lon)

                utc_timestamp = datetime.datetime.fromtimestamp(
                    ts_ms / 1000, datetime.UTC
                )

                total_pnts += 1

                f_sl.write(line.strip() + ",")

                if is_in_sunlight(lon_deg, lat_deg, utc_timestamp):
                    f_sl.write("1")
                    sunlit_pnts += 1

                f_sl.write("\n")

    print(f"Total points: {total_pnts}, sunlit points: {sunlit_pnts}")
    print(f"Sunlit ratio: {sunlit_pnts / total_pnts}")
