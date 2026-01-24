from pathlib import Path
import os
from re import L
import tomllib
import tomli_w
from platformdirs import PlatformDirs
from typing import TypedDict, cast, Any

# --- Platform Directories ---
dirs = PlatformDirs("t80m", None)

USER_DATA_DIR = Path(dirs.user_data_dir)
USER_CONFIG_DIR = Path(dirs.user_config_dir)
USER_RUNTIME_DIR = Path(dirs.user_runtime_dir)
USER_LOG_DIR = Path(dirs.user_log_dir)

CONFIG_FILE_PATH = USER_CONFIG_DIR / "config.toml"

# --- Type Definitions ---
class PathsConfig(TypedDict):
    roms: str
    database_dir: str
    database_csv: str
    media: str
    gamelistxml: str
    itch_request_header: str
    backuped_roms: str
    init_pack: str
    logs: str

class ReposConfig(TypedDict):
    database: str
    media: str

class NetworkConfig(TypedDict):
    repos: ReposConfig
    ipfs_gateways: list[str]

class Config(TypedDict):
    paths: PathsConfig
    network: NetworkConfig

# --- Path Interpolation ---
def _interpolate_path(path_str: str) -> Path:
    """Interpolate placeholders like {user_data_dir} in path strings."""
    placeholders = {
        "user_data_dir": str(USER_DATA_DIR),
        "user_config_dir": str(USER_CONFIG_DIR),
        "user_runtime_dir": str(USER_RUNTIME_DIR),
        "user_log_dir": str(USER_LOG_DIR),
    }
    for key, value in placeholders.items():
        path_str = path_str.replace(f"{{{key}}}", value)
    return Path(path_str)

# --- Default Values ---
_DEFAULTS: Config = {
    "paths": {
        "roms": os.path.join("{user_data_dir}","roms"),
        "database_dir": os.path.join("{user_data_dir}","database"),
        "database_csv": os.path.join("{user_data_dir}","database","games_info.csv"),
        "media": os.path.join("{user_data_dir}","media"),
        "gamelistxml": os.path.join("{user_data_dir}","gamelist.xml"),
        "itch_request_header": os.path.join("{user_runtime_dir}","itch_request_header.txt"),
        "backuped_roms": os.path.join("{user_data_dir}","backuped-roms"),
        "init_pack": os.path.join("{user_data_dir}","TIC80-InitPack.tar.xz"),
        "logs": "{user_log_dir}",
    },
    "network": {
        "repos": {
            "database": "https://github.com/TIC80-Collection-Manager/t80m-db.git",
            "media": "https://github.com/TIC80-Collection-Manager/t80m-media.git",
        },
        "ipfs_gateways": [
            "gateway.ipfs.io",
            "ipfs.io",
            "gateway.pinata.cloud",
            "dweb.link",
            "cf-ipfs.com",
        ],
    },
}


def save_default_config() -> None:
    """Save the default configuration to the config file."""
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE_PATH, "wb") as f:
        tomli_w.dump(_DEFAULTS, f)

def _load_config() -> Config:
    """Load config from TOML file, merging with defaults."""
    config: Config = {
        "paths": _DEFAULTS["paths"].copy(),
        "network": _DEFAULTS.get("network", {"ipfs_gateways": []}).copy(),
    }
    
    if CONFIG_FILE_PATH.exists():
        with open(CONFIG_FILE_PATH, "rb") as f:
            user_config: dict[str, Any] = tomllib.load(f)
        
        # Deep merge user config into defaults
        if "paths" in user_config:
            paths_update = cast(PathsConfig, user_config["paths"])
            config["paths"] = {**config["paths"], **paths_update}
        if "network" in user_config:
            network_data = user_config["network"]
            if isinstance(network_data, dict) and "repos" in network_data:
                config["network"]["repos"] = cast(ReposConfig, network_data["repos"])
            if isinstance(network_data, dict) and "ipfs_gateways" in network_data:
                config["network"]["ipfs_gateways"] = cast(list[str], network_data["ipfs_gateways"])
    else:
        save_default_config()
    
    return config


_config = _load_config()

ROMS_PATH = _interpolate_path(_config["paths"]["roms"])
DATABASE_PATH = _interpolate_path(_config["paths"]["database_dir"])
CSV_DATABASE_PATH = _interpolate_path(_config["paths"]["database_csv"])
MEDIA_PATH = _interpolate_path(_config["paths"]["media"])
GAMELISTXML_PATH = _interpolate_path(_config["paths"]["gamelistxml"])
ITCH_REQUEST_HEADER_PATH = _interpolate_path(_config["paths"]["itch_request_header"])
OLD_ROMS_PATH = _interpolate_path(_config["paths"]["backuped_roms"])
INIT_PACK_PATH = _interpolate_path(_config["paths"]["init_pack"])
LOGS_PATH = _interpolate_path(_config["paths"]["logs"])

REPO_DB = _config.get("network", {}).get("repos", {}).get("database", _DEFAULTS["network"]["repos"]["database"])
REPO_MEDIA = _config.get("network", {}).get("repos", {}).get("media", _DEFAULTS["network"]["repos"]["media"])

IPFS_GATEWAYS = _config.get("network", {}).get("ipfs_gateways", _DEFAULTS["network"]["ipfs_gateways"])

USER_EDITOR = os.environ.get("EDITOR")

HEADERS = {
    "User-Agent": "TIC80-Collection-Manager/1.0 (+https://github.com/TIC80-Collection-Manager/t80m)",
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate",
}

# Define the folders for multi-folder organization and their corresponding API paths
API_CATEGORIES = {
    "Games": "play/Games",
    "WIP": "play/WIP",
    "Demoscene": "play/Demoscene",
    "Livecoding": "play/Livecoding",
    "Music": "play/Music",
    "Tech": "play/Tech",
    "Tools": "play/Tools",
}
# All possible folders for multi-folder organization detection
ALL_TYPES_FOLDERS = list(API_CATEGORIES.keys()) + ["Itch", "ItchM"]

FOLDERS_MULTI = list(API_CATEGORIES.keys())

# Default Fieldnames - These define the expected order for core fields.
# Only used when creating a new CSV file.
DEFAULT_FIELDNAMES = [
    "name_original_reference", "itch_titlename", "name_overwrite", "sortname",
    "lang", "region", "id", "tic_id",
    "itch_id", "source_with_bestversion", "notes", "sscrp_id", "sscrp_id2",
    "sscrp_note1", "sscrp_note2", "NOT_GAME",
    "include_in_collection", "include_in_curated_collection", "distribution_license",
    "rom_category", "tic_category",
    "overwrite_author", "tic_author_name", "tic_uploader_name", "itch_author_name",
    "itch_author_slug", "itch_author_id", "tic_uploader_id",
    "tic_pub_date", "tic_upd_date", "itch_pub_date",
    "itch_upd_date", "itch_lastmodified_date",
    "overwrite_pub_timestamp", "overwrite_upd_timestamp",
    "tic_pub_timestamp", "tic_upd_timestamp", "itch_pub_timestamp",
    "itch_upd_timestamp", "itch_lastmodified_timestamp",
    "download_url", "itch_page",
    "overwrite_genre", "sccrp_genre", "itch_genre", "num_players",
    "esde_controller", "match_type",
    "tic_md5", "file_md5", "file_sha1", "file_CRC", "ipfs_cid",
    "overwrite_description", "sscrp_description", "tic_description",
    "tic_description_extra", "itch_description", "itch_description_extra",
    "match_type"
]

FORBIDDEN_CHARS = '<>:"/\\|?*'
