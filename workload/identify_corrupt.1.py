import tqdm as tqdm

if __name__ == "__main__":
    corrupt_images = []
    with open("corrupt_images.txt", "r") as f:
        for x in f:
            image, error = x.strip().split(",")
            image = image.strip().split(".zip")[0][len("../pkg/model/images/") :]
            corrupt_images.append((image, error))

    image_types = {}
    with open("fix_fixed.log", "r") as f:
        for x in f:
            image_type, image_name = x.strip().split(",")
            image_types[image_name] = image_type

    for image, error in corrupt_images:
        if image in image_types:
            print(f"{image_types[image]},{image}")
        else:
            print(f"unknown,{image}")
