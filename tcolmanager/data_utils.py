import argparse
import os
import re
from typing import Callable, Literal
import zlib
import hashlib
from datetime import datetime, timezone
from pathlib import Path

# pyright: reportUninitializedInstanceVariable=false

# Define a single, comprehensive Namespace for type hinting all possible argparse arguments.
# Command-specific arguments are marked as Optional.
class TColManagerArgs(argparse.Namespace):
    # Global arguments
    command: str = ""
    rom_folder_organization: Literal["single", "multiple"]
    filename_category_parenthesis: bool
    use_custom_filenames: bool
    use_custom_gamenames: bool
    filename_case: Literal["unchanged", "uppercase", "lowercase"]
    func: Callable[..., None] | None = None

    # Command-specific arguments
    source: Literal["tic80com", "itch", "ipfs"] | None = None
    download_all: bool
    download_almost_all: bool
    image_path: str
    dest_path: str | None = None
    export_all: bool | None = None
    export_almost_all: bool | None = None
    export_curated_distribution_safe: bool | None = None
    xml_file: str | None = None
    force: bool

def ts_to_parts(ts: str) -> tuple[str, str]:
    """Return YYYY-MM-DD and HH:MM (UTC) from a seconds timestamp string."""
    if not ts:
        return "", ""
    try:
        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
    except Exception:
        return "", ""

def get_hashes(filepath: Path) -> tuple[str, str, str]:
    """Calculate MD5, SHA1, and CRC32 for a file."""
    h_sha1 = hashlib.sha1()
    h_md5 = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            data = f.read()
            h_sha1.update(data)
            h_md5.update(data)
            h_crc = zlib.crc32(data) & 0xFFFFFFFF
        return h_md5.hexdigest(), h_sha1.hexdigest(), f"{h_crc:08X}"
    except Exception:
        return "", "", ""

def normalize_id(id_str: str) -> str:
    """
    Normalizes an ID string by attempting to convert it to a clean integer string.

    Handles the following cases:
    - Float-like strings ("329.0") are converted to integer strings ("329").
    - Empty strings ("") are returned as is.
    - IDs with letters but no decimal are returned as is.
    """
    if not id_str:
        return id_str  # Handle empty strings

    id_str = id_str.strip()  # Remove any surrounding whitespace
    try:
        # Attempt to convert to float, then to integer, then to string
        clean_id = str(int(float(id_str)))
        return clean_id
    except (ValueError, TypeError):
        # If conversion fails (e.g., for a non-numeric ID), return the original string.
        return id_str

def get_primary_game_id(row: dict[str, str]) -> str | None:
    """
    Determines the primary game ID from a row based on `source_with_bestversion`.

    The selection logic is:
    - If source is 'tic80com' or empty, prefer 'tic_id'.
    - If source is 'itch', prefer 'itch_id'.
    - For any other source, prefer 'id'.

    If the preferred ID field is empty, it falls back to the other ID fields
    in the order: tic_id -> itch_id -> id, to ensure an entry is not lost
    if any identifier exists.
    """
    source = row.get("source_with_bestversion", "").strip().lower()
    
    tic_id = row.get("tic_id", "")
    itch_id = row.get("itch_id", "")
    id_val = row.get("id", "")
    
    preferred_id = None
    if source == "tic80com" or not source:
        preferred_id = tic_id
    elif source == "itch":
        preferred_id = itch_id
    else: # For custom sources, 'id' is the primary identifier
        preferred_id = id_val

    if preferred_id:
        return preferred_id

    # Fallback if preferred ID is missing, to avoid losing rows.
    return tic_id or itch_id or id_val

def get_secondary_game_id(row: dict[str, str]) -> str | None:
    """
    Determines the secondary game ID (tic_id or itch_id) based on the primary.
    This is used to find associated media if the primary ID media is missing.
    """
    primary_id = get_primary_game_id(row)
    tic_id = row.get("tic_id")
    itch_id = row.get("itch_id")

    # If primary is tic_id, secondary is itch_id (if it exists and is different)
    if primary_id == tic_id and itch_id and tic_id != itch_id:
        return itch_id
    # If primary is itch_id, secondary is tic_id (if it exists and is different)
    if primary_id == itch_id and tic_id and tic_id != itch_id:
        return tic_id
    
    return None

def get_rom_category(row: dict[str, str]) -> str:
    rom_source = row.get("source_with_bestversion", "tic80com") or "tic80com"
    return row.get("rom_category") or (
        'Itch' if rom_source == 'itch' else (
        row.get("tic_category", "Games") if rom_source == "tic80com" else "Unclassified"))

def find_game_file(roms_path: Path, game_id: str, rom_folder_organization: str) -> Path | None:
    """Search for a ROM file containing the game_id in its filename."""
    if not game_id:
        return None
    patterns = [f"- {game_id} ("] # Search for - {id} ( in filename

    if rom_folder_organization == "multiple":
        # Scan all subdirectories, not just the known API ones.
        search_dirs = [d for d in roms_path.iterdir() if d.is_dir()]
    else:
        search_dirs = [roms_path]

    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        # Search for .tic or .png files containing the ID pattern
        for ext in ["*.tic", "*.png"]:
            for path in search_dir.glob(ext):
                if any(p in path.name for p in patterns):
                    return path
    return None

def set_mtime(file_path: Path, mtime_timestamp: float) -> bool:
    """Set the modification time of a file."""
    try:
        os.utime(file_path, (mtime_timestamp, mtime_timestamp))
        print(f"    -> Set mtime to {datetime.fromtimestamp(mtime_timestamp).strftime('%Y-%m-%d %H:%M:%S')}")
        return True
    except Exception as e:
        print(f"    ⚠️ Could not set mtime: {e}")
        return False

def find_media_file(media_dir: Path, game_id: str) -> Path | None:
    """Search for a media file (.png) containing the game_id in its filename."""
    if not game_id or not media_dir.is_dir():
        return None
    
    # Updated pattern:
    # It now matches " - {game_id}.png", " - {game_id} (YYYY-MM-DD).png",
    # or " - {game_id} ().png".
    # The `(\s\(\d{{4}}-\d{{2}}-\d{{2}}\)|\s\(\))` part handles both dated and blank parentheses.
    # The outer `?` makes this entire date/blank-date part optional.
    pattern = rf" - {game_id}(\s\(\d{{4}}-\d{{2}}-\d{{2}}\)|\s\(\))?\.png$"

    for path in media_dir.glob("*.png"):
        if re.search(pattern, path.name):
            return path
            
    return None

def parse_raw_headers(raw_headers_str: str) -> dict[str, str]:
    """Parses a raw HTTP headers string into a dictionary."""
    headers: dict[str, str] = {}
    if not raw_headers_str.strip():
        return headers
    for line in raw_headers_str.strip().split('\n'):
        if line.strip().startswith("#"):
            continue
        if ':' in line:
            key, value = line.split(':', 1)
            headers[key.strip()] = value.strip()
    return headers
