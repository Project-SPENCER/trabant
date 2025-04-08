import numpy as np
import tqdm as tqdm
import zipfile
import PIL.Image
import os

IMAGE_LOG = "../pkg/model/image_log_with_alt.csv"
IMAGES = "../pkg/model/images"

BAND_INDICES = {
    "B01": 0,
    "B02": 1,
    "B03": 2,
    "B04": 3,
    "B05": 4,
    "B06": 5,
    "B07": 6,
    "B08": 7,
    "B8A": 8,
    "B09": 9,
    "B11": 10,
    "B12": 11,
    "CLD": 12,
}

if __name__ == "__main__":
    # images = glob.glob(os.path.join(IMAGES, "*.zip"))
    images = []
    with open(IMAGE_LOG, "r") as f:
        for x in f:
            image = x.strip().split(",")[0]
            if image.startswith("t"):
                continue
            images.append(os.path.join(IMAGES, f"{image}.zip"))

    corrupt_images = []

    for image_path in tqdm.tqdm(images):
        try:
            with zipfile.ZipFile(image_path) as zf:
                # print(f"Reading {os.path.basename(image_path)}")
                for band in BAND_INDICES.keys():
                    with zf.open(
                        f"{os.path.basename(image_path)[:-4]}_{band}.tiff"
                    ) as f:
                        b = np.array(PIL.Image.open(f))
        except Exception as e:
            # print(f"Error reading {os.path.basename(image_path)}")
            corrupt_images.append((image_path, e))

    with open("corrupt_images.txt", "w") as f:
        for image, error in corrupt_images:
            f.write(f"{image},{str(error).strip()}\n")

    print(f"Found {len(corrupt_images)} corrupt images out of {len(images)}")
