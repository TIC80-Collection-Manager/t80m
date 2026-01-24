import hashlib
import tarfile
import re
import shutil
from typing import cast
import requests
import tomllib
from pathlib import Path
from git import Repo

from tcolmanager.config import (
    DATABASE_PATH,
    INIT_PACK_PATH,
    REPO_DB,
    REPO_MEDIA,
    ROMS_PATH, MEDIA_PATH, CSV_DATABASE_PATH, HEADERS
)
from tcolmanager.csv_manager import load_csv_database
from tcolmanager.filename_utils import generate_filename_and_gamename
from tcolmanager.data_utils import TColManagerArgs, get_rom_category
from tcolmanager.utils import log_command

def _load_initpack_config() -> tuple[list[str], str]:
    """Load InitPack configuration from pyproject.toml"""
    pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
    
    with open(pyproject_path, "rb") as f:
        config = tomllib.load(f)
    
    tool_config = cast(dict[str, dict[str, dict[str, dict[str, str | list[str]]]]], config.get("tool", {}))
    initpack_config = tool_config.get("t80m", {}).get("initpack", {})
    
    urls = initpack_config.get("urls")
    sha256 = initpack_config.get("sha256")
    
    if not isinstance(urls, list) or not urls or not isinstance(sha256, str) or not sha256:
        raise ValueError("InitPack configuration missing or invalid in pyproject.toml")
    
    return urls, sha256

def _is_only_empty_folders(path: Path) -> bool:
    """Check if a directory contains only empty folders (no files)"""
    for item in path.rglob("*"):
        if item.is_file():
            return False
    return True

@log_command
def init_command(args: TColManagerArgs):
    """
    Checks for InitPack, downloads if missing, verifies integrity,
    and extracts ROMs/Media to their respective locations.
    """
    print("--- Starting Initialization ---")
    
    # Clone database repository
    print("Cloning database repository...")
    try:
        if DATABASE_PATH.exists():
            print(f"Database directory already exists at {DATABASE_PATH}")

            # If the csv db already exist we keep it for safety
            if (DATABASE_PATH / "games_info.csv").exists():
                pass
            
            # Check if it's a valid git repository
            elif (DATABASE_PATH / ".git").exists():
                print("Pulling latest changes...")
                repo = Repo(DATABASE_PATH)
                # Fetch latest changes
                _ = repo.remotes.origin.fetch()
                # Reset to remote branch
                try:
                    repo.git.reset('--hard', 'origin/main')
                except Exception:
                    # Try 'master' if 'main' doesn't exist
                    repo.git.reset('--hard', 'origin/master')
            elif _is_only_empty_folders(DATABASE_PATH):
                print("Directory contains only empty folders. Removing and cloning fresh...")
                shutil.rmtree(DATABASE_PATH)
                DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
                _ = Repo.clone_from(REPO_DB, DATABASE_PATH)
            else:
                print("❌ Error: Database directory exists with files but is not a git repository.")
                print("Please manually remove or backup the directory and try again.")
                return
        else:
            DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
            _ = Repo.clone_from(REPO_DB, DATABASE_PATH)
        print("Database repository ready. ✅")
    except Exception as e:
        print(f"❌ Error cloning/updating database repository: {e}")
        return
    
    # Clone media repository
    print("Cloning media repository...")
    try:
        if MEDIA_PATH.exists():
            print(f"Media directory already exists at {MEDIA_PATH}")
            
            # Check if it's a valid git repository
            if (MEDIA_PATH / ".git").exists():
                print("Pulling latest changes...")
                repo = Repo(MEDIA_PATH)
                _ = repo.remotes.origin.pull()
            elif _is_only_empty_folders(MEDIA_PATH):
                print("Directory contains only empty folders. Removing and cloning fresh...")
                shutil.rmtree(MEDIA_PATH)
                MEDIA_PATH.parent.mkdir(parents=True, exist_ok=True)
                _ = Repo.clone_from(REPO_MEDIA, MEDIA_PATH)
            else:
                print("❌ Error: Media directory exists with files but is not a git repository.")
                print("Please manually remove or backup the directory and try again.")
                return
        else:
            MEDIA_PATH.parent.mkdir(parents=True, exist_ok=True)
            _ = Repo.clone_from(REPO_MEDIA, MEDIA_PATH)
        print("Media repository ready. ✅")
    except Exception as e:
        print(f"❌ Error cloning/updating media repository: {e}")
        return

    
    # Load config from pyproject.toml

    try:
        INIT_PACK_URLS, INIT_PACK_SHA256 = _load_initpack_config()
    except Exception as e:
        print(f"❌ Error loading InitPack configuration: {e}")
        return

    # 1. Check/Download InitPack
    if INIT_PACK_PATH.exists():
        print(f"Checking integrity of {INIT_PACK_PATH}...")
        sha256_hash = hashlib.sha256()
        try:
            with open(INIT_PACK_PATH, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            
            if sha256_hash.hexdigest() != INIT_PACK_SHA256:
                print(f"❌ Error: {INIT_PACK_PATH} SHA256 mismatch.")
                print(f"Expected: {INIT_PACK_SHA256}")
                print(f"Got:      {sha256_hash.hexdigest()}")
                return
            print("Integrity check passed. ✅")
        except Exception as e:
            print(f"❌ Error reading {INIT_PACK_PATH}: {e}")
            return
    else:
        # Try each mirror URL until one succeeds
        download_success = False
        for idx, url in enumerate(INIT_PACK_URLS):
            mirror_msg = f" (mirror {idx + 1}/{len(INIT_PACK_URLS)})" if len(INIT_PACK_URLS) > 1 else ""
            print(f"Downloading InitPack from {url}{mirror_msg}...")
            try:
                INIT_PACK_PATH.parent.mkdir(parents=True, exist_ok=True)
                with requests.get(url, headers=HEADERS, stream=True) as r:
                    r.raise_for_status()
                    with open(INIT_PACK_PATH, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192): 
                            _ = f.write(chunk)
                print("Download complete. ✅")
                
                # Verify after download
                print("Verifying downloaded file...")
                sha256_hash = hashlib.sha256()
                with open(INIT_PACK_PATH, "rb") as f:
                    for byte_block in iter(lambda: f.read(4096), b""):
                        sha256_hash.update(byte_block)
                if sha256_hash.hexdigest() != INIT_PACK_SHA256:
                    print(f"❌ Error: Downloaded file SHA256 mismatch.")
                    INIT_PACK_PATH.unlink(missing_ok=True)  # Remove bad download
                    continue  # Try next mirror
                print("Integrity check passed. ✅")
                download_success = True
                break  # Success, exit loop

            except Exception as e:
                print(f"❌ Download failed: {e}")
                INIT_PACK_PATH.unlink(missing_ok=True)  # Clean up partial download
                if idx < len(INIT_PACK_URLS) - 1:
                    print("Trying next mirror...")
                continue
        
        if not download_success:
            print("❌ All download mirrors failed.")
            return

    # 2. Load Database
    db = load_csv_database(CSV_DATABASE_PATH)
    if not db:
        print("❌ Database is empty or could not be loaded.")
        return

    # 3. Extract and Process
    print("Extracting and organizing files...")
    
    # Regex to extract ID from filename. 
    # Matches " - {id}.png", " - {id} (YYYY-MM-DD).png", " - {id} ().png"
    # Also handles .tic extension for ROMs.
    # The ID is captured in group 1.
    id_pattern = re.compile(r" - (\d+)(?:\s\(\d{4}-\d{2}-\d{2}\)|\s\(\))?\.(png|tic)$")

    try:
        with tarfile.open(INIT_PACK_PATH, "r:xz") as tar:
            members = tar.getmembers()
            count = 0
            for member in members:
                if not member.isfile():
                    continue

                # Extract ID
                match = id_pattern.search(member.name)
                if not match:
                    continue
                
                game_id = match.group(1)
                
                # Get row by column 'id'
                row = db[game_id]

                # If it fails, tries secondary ids
                if not row:
                    for entry in db.values():
                        if entry.get('tic_id') == game_id:
                            row = entry
                            break
                        elif entry.get('itch_id') == game_id:
                            row = entry
                            break
                
                if not row:
                    print(f"Entry for {game_id} not found in database. Skipping")
                    continue
                
                # Generate filenames
                filename_info = generate_filename_and_gamename(
                    row, args.use_custom_filenames, args.use_custom_gamenames,
                    args.filename_category_parenthesis, args.filename_case,
                    args.rom_folder_organization
                )

                target_path = None
                
                # Normalize member name to handle ./ prefix
                name = member.name
                if name.startswith("./"):
                    name = name[2:]
                
                if name.startswith("screenshots/"):
                    # target_path = MEDIA_PATH / "screenshots" / filename_info.image_filename
                    continue
                elif name.startswith("cart-covers/"):
                    target_path = MEDIA_PATH / "cart-covers" / filename_info.image_filename
                    # continue
                elif name.startswith("titlescreens/"):
                    # target_path = MEDIA_PATH / "titlescreens" / filename_info.image_filename
                    continue
                elif "/" not in name:
                    # Root file -> ROM
                    rom_filename = filename_info.rom_filename
                    
                    if args.rom_folder_organization == "multiple":
                        category = get_rom_category(row)
                        target_path = ROMS_PATH / category / rom_filename
                    else:
                        target_path = ROMS_PATH / rom_filename
                
                if target_path:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Skip if file already exists
                    if not target_path.exists():
                        source = tar.extractfile(member)
                        if source:
                            with open(target_path, "wb") as f:
                                shutil.copyfileobj(source, f)
                            count += 1
            
            print(f"Extracted and organized {count} files. ✅")

    except Exception as e:
        print(f"❌ Error during extraction: {e}")

    print("--- Initialization Complete ---")
