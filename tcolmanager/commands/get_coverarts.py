import requests
import shutil

from tcolmanager.config import CSV_DATABASE_PATH, MEDIA_PATH, HEADERS
from tcolmanager.csv_manager import load_csv_database
from tcolmanager.filename_utils import generate_filename_and_gamename
from tcolmanager.data_utils import get_primary_game_id
from tcolmanager.data_utils import TColManagerArgs
from tcolmanager.tic80_api_client import download_and_convert_gif_to_png
from tcolmanager.utils import log_command

@log_command
def get_coverarts_command(args: TColManagerArgs):
    """Downloads missing cover arts based on the md5hash in the CSV."""
    print("--- Starting Cover Art Download ---")
    db = load_csv_database(CSV_DATABASE_PATH) # Load the global database
    session = requests.Session()
    session.headers.update(HEADERS)

    COVER_DIR = MEDIA_PATH / "cart-covers"
    COVER_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR = MEDIA_PATH / "screenshots"
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    downloaded_count = 0

    for row in db.values():
        game_id = get_primary_game_id(row)
        md5 = row.get("tic_md5")

        if not game_id or not md5:
            continue

        filename_info = generate_filename_and_gamename(
            row, args.use_custom_filenames, args.use_custom_gamenames,
            args.filename_category_parenthesis, args.filename_case,
            args.rom_folder_organization
        )

        game_name = filename_info.gamename
        # filename = filename_info.rom_filename
        

        cover_name = filename_info.image_filename
        cover_path = COVER_DIR / cover_name

        if cover_path.exists() and cover_path.stat().st_size >= 30:
            continue # Already exists and is valid size

        gif_url = f"https://tic80.com/cart/{md5}/cover.gif"

        print(f"[+] Downloading cover for {game_id} ({game_name})")
        if download_and_convert_gif_to_png(gif_url, cover_path, session):
            downloaded_count += 1
            print(f"    ✅ Downloaded cover to {cover_name}")

            # Fallback: If no curated screenshot exists, copy this cover art there.
            screenshot_path = SCREENSHOT_DIR / cover_name
            if not screenshot_path.exists():
                try:
                    _ = shutil.copy(cover_path, screenshot_path)
                    print(f"    -> Copied to screenshots (fallback): {cover_name}")
                except Exception as e:
                    print(f"    ❌ Failed to copy cover to screenshots: {e}")
        else:
            print(f"    ⚠️ No cover found or download failed for {game_id}")

    print(f"--- Cover Art Download Complete: {downloaded_count} new covers ---")