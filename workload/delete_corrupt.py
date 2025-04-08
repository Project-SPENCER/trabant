import tqdm as tqdm
import os

if __name__ == "__main__":
    corrupt_images = []
    with open("corrupt_images.txt", "r") as f:
        for x in f:
            image, error = x.strip().split(",")
            image = image.strip().split(".zip")[0][len("../pkg/model/images/") :]
            corrupt_images.append((image, error))

    for image, error in corrupt_images:
        # delete the image
        print(f"deleting {image}")
        try:
            os.remove(f"./bupt_traces/{image}.zip")
        except Exception:
            pass
