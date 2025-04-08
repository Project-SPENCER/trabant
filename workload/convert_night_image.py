#!/usr/bin/env python3

import batch_config


def scale_array(in_data_m10, in_data_m11, in_data_cld, out_arr):
    # index 10 is s2 band 11, which is 1610nm
    # also convert from 16-bit to 8-bit
    out_arr[..., 10] = in_data_m10 // (65535 // 256)

    # index 11 is s2 band 12 (2190nm)
    out_arr[..., 11] = in_data_m11 // (65535 // 256)

    # index 12 is cld data, which is 1 if cloudy
    # 01 = Probably Clear (0-33% probability of clouds)
    # 10 = Probably Cloudy (34-66% probability of clouds)
    # 11 = Confidently Cloudy (67-100% probability of clouds)
    # convert to percentages
    # insane bit manipulation
    # 0bXY_00_000_0
    out_arr[..., 12] = (in_data_cld & 0b11000000) / 192 * 100
    # print(out_arr[..., 12])
    # print((in_data_cld & 0b11000000))


if __name__ == "__main__":
    import h5py
    import numpy as np

    with h5py.File(batch_config.VIIRS_NIGHT_DATA, "r") as f:
        # see https://ladsweb.modaps.eosdis.nasa.gov/api/v2/content/archives/Document%20Archive/Science%20Data%20Product%20Documentation/VIIRS_Black_Marble_UG_v1.3_Sep_2022.pdf
        in_data_m10 = np.array(
            f["HDFEOS/GRIDS/VNP_Grid_DNB/Data Fields/Radiance_M10"]
        )  # 1610nm
        in_data_m11 = np.array(
            f["HDFEOS/GRIDS/VNP_Grid_DNB/Data Fields/Radiance_M11"]
        )  # 2250nm
        in_data_cld = np.array(
            f["HDFEOS/GRIDS/VNP_Grid_DNB/Data Fields/QF_Cloud_Mask"]
        )  # cloud mask, bit 6&7 are cloud flags

    input_shape = in_data_m10.shape
    print(f"input shape: {input_shape}")

    output_shape = (
        input_shape[0],
        input_shape[1],
        13,
    )
    print(f"output shape: {output_shape}")

    out_data = np.zeros(output_shape, dtype=np.uint8)

    print("creating output array")
    scale_array(in_data_m10, in_data_m11, in_data_cld, out_data)

    np.savez_compressed(batch_config.NIGHT_DATA, data=out_data)
