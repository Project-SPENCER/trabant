#!/usr/bin/env python3

import batch_config
import os
import subprocess
import glob
import tqdm

if __name__ == "__main__":
    os.makedirs(batch_config.ZIPPED_TRACES_DIR, exist_ok=True)

    for d in tqdm.tqdm(glob.glob(os.path.join(batch_config.TRACE_OUTPUT_DIR, "*"))):
        zip_dir = os.path.join(
            batch_config.ZIPPED_TRACES_DIR, os.path.basename(d) + ".zip"
        )

        # print(f"zipping {d} to {zip_dir}")

        subprocess.run(
            [
                "zip",
                "-qr9",
                zip_dir,
                d,
            ]
        )
