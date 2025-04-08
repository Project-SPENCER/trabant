# Trabant: A Serverless Architecture for Multi-Tenant Orbital Edge Computing

Trabant is a serverless architecture for multi-tenant orbital edge computing based on tinyFaaS.
This repository contains the artifacts used to produce our paper.
If you use this software in a publication, please cite it as:

**Text**: T. Pfandzelter, N. Bauer, A. Leis, C. Perdrizet, F. Trautwein, T. Schirmer, O. Abboud, and D. Bermbach, **Trabant: A Serverless Architecture for Multi-Tenant Orbital Edge Computing**, 2025.

**Bibtex**:

```bibtex
@article{pfandzelter2025trabant,
    author = "Pfandzelter, Tobias and Bauer, Nikita and Leis, Alexander and Perdrizet, Corentin and Trautwein, Felix and Schirmer, Trever and Abboud, Osama and Bermbach, David",
    title = "Trabant: A Serverless Architecture for Multi-Tenant Orbital Edge Computing",
    year = 2025,
}
```

## Instructions

Replicating the experiments in our paper requires four steps:

1. Downloading and pre-processing the data set from Sentinel and VIIRS
1. Setting up the hardware
1. Running experiments
1. Running analysis

### Dataset

Dataset files depend on the trajectory and data from the BUPT-1 satellite.
You can download the `telemetry_all.csv` file from the [BUPT-1 dataset](https://github.com/TiansuanConstellation/MobiCom24-SatelliteCOTS/blob/main/CommonData-Telemetries/telemetry_all.csv.zip) and place it in the `satellite` directory.

You can use the scripts in the `workload` directory to download the sunlit and ocean data from [Sentinel Hub](https://www.sentinel-hub.com/index.html).
You will need a paid account (free ESA accounts have insufficient quotas), we paid ~35EUR for this data.
You will also need a dark image file from the [VIIRS data set](https://search.earthdata.nasa.gov/search/granules?p=C1897815356-LAADS&pg[0][v]=f&pg[0][gsk]=-start_date&q=night&hdr=500%2Bto%2B1000%2Bmeters!1%2Bto%2B10%2Bkm!250%2Bto%2B500%2Bmeters&fi=VIIRS&as[instrument][0]=VIIRS&tl=1535525228.89!5!!&lat=23.484375&long=-122.203125).

### Hardware

The hardware we use are two Raspberry Pi 4Bs with Raspberry Pi OS.
Additionally, we use [TinkerForge](https://www.tinkerforge.com/en/) hardware to connect temperature and energy sensors:

- [HAT Brick](https://www.tinkerforge.com/en/shop/hat-brick.html)
- [Temperature IR Bricklet 2.0](https://www.tinkerforge.com/en/shop/temperature-ir-v2-bricklet.html)
- [Voltage/Current Bricklet 2.0](https://www.tinkerforge.com/en/shop/voltage-current-v2-bricklet.html)

Note that you must modify the code and scripts in this repository for the correct IP addresses, SSH usernames, and TinkerForge Device UUIDs.

### Running experiments

Compile everything using `make`.
A recent (~1.23) Go toolchain is required.

Experiments are controlled using the shell scripts in the root of this repository.

The serverless functions used in this prototype use pre-trained TensorFlow models from our [image_recognition_spencer](https://github.com/Project-SPENCER/image_recognition_spencer) project.

### Analysis

For analysis, use the Jupyter notebooks in the `analysis` directory.
