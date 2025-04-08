#!/usr/bin/env python3
import datetime

import skyfield.api
import pandas as pd
import seaborn as sns
import cartopy
import cartopy.crs as ccrs
import matplotlib.pyplot as plt

# SATS = [55257, 55261]  # 55257 and 55261
# START = "2023-05-03 02:02:52Z"  # UTC
# END = "2023-05-03 03:37:30Z"  # UTC
# RESOLUTION = 0.1  # seconds

EARTH_RADIUS_KM = 6371.0  # km
# STD_GRAVITATIONAL_PARAMATER_EARTH = 3.986004418e14
# EARTH_DAY_S = 86400  # seconds

TS = skyfield.api.load.timescale()


def load_tle_data(sat):
    tle_data = []

    # get the txt file
    with open(f"sat0000{sat}.txt", "r") as f:
        lines = f.readlines()

        for i in range(0, len(lines), 2):
            epoch_yr = 2000 + int(lines[i][18:20])
            epoch_day = float(lines[i][20:32])

            # print(int(lines[i][18:20]), float(lines[i][20:32]))

            epoch_datetime = datetime.datetime(
                year=epoch_yr, month=1, day=1, tzinfo=datetime.timezone.utc
            ) + datetime.timedelta(days=epoch_day - 1)

            TLE_1 = lines[i]
            TLE_2 = lines[i + 1]

            tle_data.append((epoch_datetime, skyfield.api.EarthSatellite(TLE_1, TLE_2)))

    if len(tle_data) == 0:
        print("No TLE data found.")
        exit(1)

    return tle_data


def get_position(tle_data, date):
    if date < tle_data[0][0] or date > tle_data[-1][0]:
        print(f"Date {date} is out of range {tle_data[0][0]} - {tle_data[-1][0]}.")
        return None

    tle = None

    for i in tle_data:
        if date > i[0]:
            tle = i
            break

    if tle is None:
        print("Error in TLE data.")
        return None

    sat = tle[1]

    date_ts = TS.from_datetime(date)

    # print(date, tle[0], date_ts.utc_datetime())

    geocentric = sat.at(date_ts)

    pos = skyfield.api.wgs84.geographic_position_of(geocentric)

    return pos.latitude.degrees, pos.longitude.degrees, pos.elevation.km


def plot_samples(samples, output):
    fig, ax = plt.subplots(
        figsize=(10, 10),
        subplot_kw={"projection": cartopy.crs.Robinson(central_longitude=180)},
    )

    ax.add_feature(
        cartopy.feature.BORDERS, linestyle="-", alpha=1, edgecolor=("#FFFFFF")
    )

    ax.add_feature(cartopy.feature.LAND, facecolor=("#d4d4d4"))
    ax.gridlines()

    df = pd.DataFrame(samples, columns=["c", "lat", "lng", "alt"])

    cmap = sns.color_palette("viridis", as_cmap=True)

    sns.scatterplot(
        ax=ax,
        data=df,
        x="lng",
        y="lat",
        transform=ccrs.PlateCarree(),
        zorder=10,
        linewidth=0.5,
        alpha=0.8,
        hue="c",
        marker="x",
        size=0.1,
        palette=cmap,
    )

    norm = plt.Normalize(max(df["c"]), min(df["c"]))
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    ax.get_legend().remove()
    cbar = ax.figure.colorbar(
        sm,
        location="bottom",
        shrink=0.1,
        pad=-0.15,
        aspect=10,
        anchor=(0, -0),
        ax=ax,
    )

    plt.savefig(output)


# if __name__ == "__main__":
#     for sat in SATS:
#         tle_data = load_tle_data(sat)

#         positions = []

#         i = datetime.datetime.fromisoformat(START)

#         total_duration = (
#             datetime.datetime.fromisoformat(END)
#             - datetime.datetime.fromisoformat(START)
#         ).total_seconds()

#         with tqdm.tqdm(total=total_duration) as pbar:
#             while i < datetime.datetime.fromisoformat(END):
#                 lat, lon, alt = get_position(tle_data, i)

#                 positions.append([i.timestamp(), lat, lon, alt])

#                 i += datetime.timedelta(seconds=RESOLUTION)

#                 pbar.update(RESOLUTION)

#         plot_samples(positions, f"sat{sat}_samples.png")
