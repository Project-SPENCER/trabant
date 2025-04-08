from sentinelhub import DataCollection

# sentinelhub
CLIENT_ID = "secret-client-id"
CLIENT_SECRET = "secret-client-secret"

CLIENT_SENTINEL_BASE_URL = "https://services.sentinel-hub.com"
CLIENT_SENTINEL_TOKEN_URL = (
    "https://services.sentinel-hub.com/auth/realms/main/protocol/openid-connect/token"
)

DATA_COLLECTION = (
    DataCollection.SENTINEL2_L2A
    if CLIENT_SENTINEL_BASE_URL == "https://services.sentinel-hub.com"
    else DataCollection.SENTINEL2_L2A.define_from(
        "sentinel-2-l2a", service_url=CLIENT_SENTINEL_BASE_URL
    )
)

RESOLUTION_M = 10
CHECK_RESOLUTION_M = 100
SWATH_WIDTH_M = 2560

OCEAN_BBOX = [
    [-28.44635, 37.402892],
    [-27.15271, 37.402892],
    [-27.15271, 38.315801],
    [-28.44635, 38.315801],
    [-28.44635, 37.402892],
]

INPUT_TRACE = "bupt_trajectory.csv"
INPUT_TRACE_WITH_SL = "bupt_trajectory_sl.csv"
MAX_S = 60 * 60 * 6  # 6 hours

DATA_START_DATE_NORMAL = "2023-04-20"
DATA_START_DATE_EXTENDED = "2022-11-01"
DATA_END_DATE = "2023-05-02"

MAX_POINTS_TO_COMBINE = 5_000
SPLIT_OUTPUT_DIR = "bupt_splits"
TILE_OUTPUT_DIR = "bupt_tiles"
OCEAN_TILE_OUTPUT_DIR = "ocean_tiles"

SPLIT_OUTPUT_EXT = "pickleb"
# SPLIT_OUTPUT_DRIVER = "GeoJSON"

TRACE_OUTPUT_DIR = "bupt_traces"
TRACE_LOG = "image_log.csv"

NIGHT_DATA = "night_data.npz"
VIIRS_RESOLUTION_M = 500
VIIRS_NIGHT_DATA = "VNP46A1.A2024282.h10v04.001.2024283072008.h5"

ZIPPED_TRACES_DIR = "traces_zipped"

RANDOM_SEED = 42
