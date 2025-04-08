#!/usr/bin/python3
import pandas as pd

import warnings

warnings.filterwarnings("ignore")

# Set Input Path
path = "telemetry_all.csv"
source_df = pd.read_csv(path)

START_DATE = "2023-05-01 00:00:00Z"  # UTC
END_DATE = "2023-05-01 06:00:00Z"  # UTC

# actually we figured out we need to start a bit later to get proper alignment

# START_DATE = "2023-05-01 05:10:00Z"  # UTC
# END_DATE = "2023-05-01 11:10:00Z"  # UTC

START_DATE = "2023-04-30 22:50:00Z"
END_DATE = "2023-05-01 04:50:00Z"

# actually we figured out we need to start a bit earlier to get proper alignment

df = source_df[(source_df["Time"] >= START_DATE) & (source_df["Time"] <= END_DATE)]

df["TIME"] = pd.to_datetime(df["Time"]).apply(lambda x: int(pd.Timestamp.timestamp(x)))

df = df.reset_index(drop=True)
df = df.dropna()

# following the fig 12/13 code
# not sure what UV_I is, but it is also added to comms energy in fig 12/13 code
df["solar_harvested_energy_w"] = (
    df["MPPT1_Iout"] / 1000 * df["Total_U"] / 1000
    + df["MPPT2_Iout"] / 1000 * df["Total_U"] / 1000
) * 1.1
df["payload_energy_w"] = (
    df["I_Atlas200DK-A"] * 12.1 + df["I_Atlas200DK-B"] * 12.1 + df["I_Pi-A"] * 5.1
) / 1000
df["comms_energy_w"] = (
    df["POBC_I_5V"] / 1000 * 5
    + df["XMIT_A_12V"] / 1000 * 12
    + df["XMIT_B_12V"] / 1000 * 12
    + df["UV_I"] / 1000 * 3.3
)

df["total_energy_w"] = (
    (df["Total_I"] / 1000 * df["Total_U"] / 1000) * 0.9
    - df["comms_energy_w"]
    - df["payload_energy_w"]
)

df["TIME"] = (df["TIME"] - df["TIME"].iloc[0]) / 60

save_df = df[["TIME", "solar_harvested_energy_w", "total_energy_w"]]

save_df.dropna(inplace=True)
save_df["time_s"] = (save_df["TIME"] * 60).astype(int)
save_df = save_df[["time_s", "solar_harvested_energy_w", "total_energy_w"]]

# now make sure we have all the data we need by joining against a range of 0 to the max time
# this will fill in any missing data points
save_df_new = pd.DataFrame({"time_s": range(save_df["time_s"].max() + 1)})
save_df = save_df_new.merge(save_df, on="time_s", how="left")
save_df.fillna(method="ffill", inplace=True)

save_df.to_csv("solar_harvested_energy.csv", index=False)

mean_J_per_second = (
    save_df["solar_harvested_energy_w"].sum() - save_df["total_energy_w"].sum()
) / len(save_df)
print(f"Mean energy per second: {mean_J_per_second:.2f} J/s")
