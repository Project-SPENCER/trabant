#!/usr/bin/env python3


if __name__ == "__main__":
    real_fix_log = "fix_log.csv"
    backup_fix_log = "fix.log"
    fixed_fix_log = "fix_fixed.log"

    with open(real_fix_log, "r") as f:
        fixed_images = {
            image_name: image_type
            for image_type, image_name in (x.strip().split(",") for x in f)
        }

    backup_images = {}
    with open(backup_fix_log, "r") as f:
        for x in f:
            if (
                "ocean" not in x
                and "night" not in x
                and "normal" not in x
                and "extended" not in x
                or "random" in x
            ):
                continue

            # print(x)
            image_name, image_type = x.strip().split()
            backup_images[image_name] = image_type

    all_images = {
        image_name: fixed_images.get(image_name, backup_images.get(image_name))
        for image_name in set(fixed_images.keys()) | set(backup_images.keys())
    }

    with open(fixed_fix_log, "w") as f:
        for image_name, image_type in all_images.items():
            f.write(f"{image_type},{image_name}\n")
