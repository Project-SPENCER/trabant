#!/usr/bin/env python3

import batch_config
import zipfile
import PIL
import os
import numpy as np
import matplotlib.pyplot as plt
import tqdm


if __name__ == "__main__":
    FIX_OUTPUT_DIR = "traces_fixed"

    with open("fix_fixed.log", "r") as f:
        fixed_images = [x.strip().split(",") for x in f]

    with open("image_log.csv") as f:
        important_images = set([x.strip().split(",")[0] for x in f])

    for image_type, fixed_image in tqdm.tqdm(fixed_images):
        if fixed_image not in important_images:
            print(f"skipping {fixed_image}")
            continue

        if image_type == "night" or image_type == "ocean":
            # just replace the image
            name = fixed_image
            print(f"saving {name}")

            image = np.load(os.path.join(FIX_OUTPUT_DIR, f"{name}.npz"))["data"]

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
            with zipfile.ZipFile(
                os.path.join(batch_config.TRACE_OUTPUT_DIR, f"{name}.zip"), "w"
            ) as z:
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
                os.path.join(batch_config.TRACE_OUTPUT_DIR, f"{name}.png"),
                dpi=100,
                bbox_inches="tight",
                pad_inches=0.1,
            )
            plt.close()

        elif image_type == "normal" or image_type == "extended":
            # replace the cld band
            name = fixed_image

            # check that this image actually exists
            if not os.path.exists(os.path.join(FIX_OUTPUT_DIR, f"{name}.npz")):
                print(f"skipping {name}")
                continue

            print(f"saving {name}")

            bands = [
                "CLD",
            ]

            # open the existing zip file in trace output dir
            tmp = "tmp.tiff"

            with zipfile.ZipFile(
                os.path.join(batch_config.TRACE_OUTPUT_DIR, f"{name}.zip"), "r"
            ) as z_orig:
                with zipfile.ZipFile(
                    os.path.join(batch_config.TRACE_OUTPUT_DIR, f"{name}-fixed.zip"),
                    "x",
                ) as z_fixed:
                    # copy everything except the cld band
                    for i in z_orig.namelist():
                        if i.endswith("CLD.tiff"):
                            continue

                        z_fixed.write(z_orig.extract(i), i)

                    # add the fixed cld band
                    i_name = f"{name}_CLD.tiff"
                    with open(tmp, "wb") as f:
                        image = np.load(os.path.join(FIX_OUTPUT_DIR, f"{name}.npz"))[
                            "data"
                        ]
                        PIL.Image.fromarray(
                            image,
                        ).save(
                            f,
                            format="TIFF",
                        )

                    z_fixed.write(tmp, i_name)

            # replace the original zip file with the fixed one
            os.rename(
                os.path.join(batch_config.TRACE_OUTPUT_DIR, f"{name}-fixed.zip"),
                os.path.join(batch_config.TRACE_OUTPUT_DIR, f"{name}.zip"),
            )

        else:
            raise ValueError(f"Unknown image type: {image_type}")
