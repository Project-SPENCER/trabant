#!/usr/bin/env python3

from dataclasses import dataclass
import subprocess
import numpy as np
import os
import tqdm
import time
import shutil
import datetime

BASELINE_LENGTH = 60  # one minute baseline length
REPEATS = 3  # how often to repeat experiment
N = 500  # number of images to process
SUT_SSH = "spencer@192.168.2.2"
RNG_SEED = 42
LOG_OUT_DIR = "logs"
RESULT_DIR = "eval-results"
# FNS = ["wildfire"]
FNS = ["wildfire", "segment", "vessel", "class", "multiclass", "noop"]


@dataclass
class experiment:
    fn: str
    repeat: int
    n: int
    seed: int


if __name__ == "__main__":
    rng = np.random.default_rng(RNG_SEED)

    os.makedirs(RESULT_DIR, exist_ok=True)

    # get all the fns
    # fns = FNS
    # fns = ["noop"]

    # make a list of experiments
    experiments = [
        experiment(fn=fn, repeat=r + 1, n=N, seed=rng.integers(0, 1000))
        for fn in FNS
        for r in range(REPEATS)
    ]

    # randomize the experiments
    rng.shuffle(experiments)

    # run the experiments
    with tqdm.tqdm(experiments) as pbar:
        for e in pbar:
            pbar.set_description(f"Running {e.fn} {e.repeat}")
            pbar.write(f"start time: {datetime.datetime.now()}")

            result_dir = os.path.join(
                RESULT_DIR, f"{e.fn}-r{e.repeat}-n{e.n}-s{e.seed}"
            )
            # if the result dir exists, skip
            if os.path.exists(result_dir):
                pbar.write(f"skipping experiment {e.fn} {e.repeat}")
                continue
            os.makedirs(result_dir, exist_ok=True)

            time.sleep(10)
            # reboot the devices
            pbar.write("rebooting devices")
            try:
                subprocess.run(
                    ["./reboot.sh"], check=True, capture_output=True, timeout=120
                )
            except Exception as e:
                print(f"error rebooting devices {e}")
                shutil.rmtree(result_dir)
                break

            time.sleep(1)

            pbar.write(f"running experiment {e.fn} {e.repeat}")
            # run the experiment
            try:
                with open(os.path.join(result_dir, "measurement.log"), "wb") as f:
                    p = subprocess.run(
                        [
                            "./eval-fn.sh",
                            e.fn,
                            str(e.seed),
                            str(BASELINE_LENGTH),
                            str(e.n),
                        ],
                        stdout=f,
                        stderr=f,
                        check=True,
                        timeout=60 * 40,
                    )

            except subprocess.CalledProcessError:
                pbar.write(f"error running experiment {e.fn} {e.repeat}")
                with open(os.path.join(result_dir, "measurement.log"), "r") as f:
                    lines = f.readlines()
                    # just print the last 10 lines
                    pbar.write("".join(lines[-10:]))
                # remove the result directory
                shutil.rmtree(result_dir)
                continue

            except subprocess.TimeoutExpired:
                pbar.write(f"timeout running experiment {e.fn} {e.repeat}")
                with open(os.path.join(result_dir, "measurement.log"), "r") as f:
                    lines = f.readlines()
                    # just print the last 10 lines
                    pbar.write("".join(lines[-10:]))
                shutil.rmtree(result_dir)
                break

            pbar.write(f"experiment {e.fn} {e.repeat} done")
            # copy all the log files
            os.rename(
                os.path.join(LOG_OUT_DIR, "eval.log"),
                os.path.join(result_dir, "eval.log"),
            )
            os.rename(
                os.path.join(LOG_OUT_DIR, "tfaas-fn.log"),
                os.path.join(result_dir, "tfaas-fn.log"),
            )
            os.rename(
                os.path.join(LOG_OUT_DIR, "tfaas.log"),
                os.path.join(result_dir, "tfaas.log"),
            )
