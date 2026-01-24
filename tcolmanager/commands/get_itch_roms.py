import requests
from datetime import timezone
import os
import shutil
from email.utils import parsedate_to_datetime

from tcolmanager import config
from tcolmanager.config import CSV_DATABASE_PATH, ROMS_PATH, MEDIA_PATH
from tcolmanager.csv_manager import load_csv_database, save_csv_database
from tcolmanager.itch_api_client import download_itch_rom, parse_rfc2822_to_dt
from tcolmanager.data_utils import find_game_file, get_hashes, parse_raw_headers
from tcolmanager.tic80_api_client import download_and_convert_gif_to_png
from tcolmanager.filename_utils import generate_filename_and_gamename
from tcolmanager.data_utils import TColManagerArgs
from tcolmanager.utils import log_command

@log_command
def get_itch_roms_command(args: TColManagerArgs):
    """Downloads ROMs for Itch.io games that need an update."""
    print("--- Starting ROM Download (Itch.io) ---")
    db = load_csv_database(CSV_DATABASE_PATH)
    session = requests.Session()

    if config.ITCH_REQUEST_HEADER_PATH.exists():
        headers_str = config.ITCH_REQUEST_HEADER_PATH.read_text(encoding="utf-8")
        session.headers.update(parse_raw_headers(headers_str))

    ITCH_SCREENSHOT_DIR = MEDIA_PATH / "itch-screenshots"
    ITCH_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR = MEDIA_PATH / "screenshots"
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    
    #games_to_check = [row for row in db.values() if row.get('itch_id') and int(row.get('itch_id')) > 10000 and not row.get('itch_description_extra')]
    games_to_check = [row for row in db.values() if row.get('source_with_bestversion') == 'itch' and not row.get('itch_lastmodified_date')]

    print(f"Found {len(games_to_check)} Itch.io games to check for downloads.")
    
    for row in games_to_check:
        itch_page = row.get('itch_page')
        if not itch_page:
            continue
            
        filename_info = generate_filename_and_gamename(
            row, args.use_custom_filenames, args.use_custom_gamenames,
            args.filename_category_parenthesis, args.filename_case,
            args.rom_folder_organization
        )

        game_name = filename_info.gamename
        new_filename = filename_info.rom_filename

        print(f"\n[+] Processing {row['id']} ({game_name})")
        
        rom_target_dir = ROMS_PATH / "Itch" if args.rom_folder_organization == "multiple" else ROMS_PATH
        rom_target_dir.mkdir(parents=True, exist_ok=True)
        
        # We use pre-filename for download to avoid date in filename yet
        pre_filename = new_filename.split(' - ')[0]

        # Search for existing file
        old_filepath = find_game_file(ROMS_PATH, row['itch_id'], args.rom_folder_organization)

        download_result = download_itch_rom(row, session, itch_page, rom_target_dir, pre_filename)
        
        if download_result:
            filepath = download_result.filepath
            # content = download_result.content
            last_mod_str = download_result.last_modified
            screenshot_urls = download_result.screenshot_urls
            
            # Calculate hashes
            md5, sha1, crc = get_hashes(filepath)
            row['file_md5'] = md5
            row['file_sha1'] = sha1
            row['file_CRC'] = crc
            
            # Update last modified date and timestamp
            if last_mod_str:
                last_mod_dt = parse_rfc2822_to_dt(last_mod_str)
                if last_mod_dt:
                    row['itch_lastmodified_date'] = last_mod_dt.strftime("%Y-%m-%d")
                    # Make sure it's timezone-aware for timestamp()
                    if last_mod_dt.tzinfo is None:
                        last_mod_dt = last_mod_dt.replace(tzinfo=timezone.utc)
                    row['itch_lastmodified_timestamp'] = str(int(last_mod_dt.timestamp()))

            # Now that we might have a date, regenerate final filename and rename
            filename_info = generate_filename_and_gamename(
                row,
                use_custom_filenames=args.use_custom_filenames,
                use_custom_gamenames=args.use_custom_gamenames,
                filename_category_parenthesis=args.filename_category_parenthesis,
                filename_case=args.filename_case,
                rom_folder_organization=args.rom_folder_organization
            )

            final_filename = filename_info.rom_filename
            final_filepath = rom_target_dir / final_filename

            # removes old rom
            if old_filepath and old_filepath.exists():
                _ = old_filepath.unlink()

            if filepath.resolve() != final_filepath.resolve():
                _ = filepath.rename(final_filepath)
            
            # Set mtime from Last-Modified header
            if last_mod_str:
                try:
                    last_modified_dt = parsedate_to_datetime(last_mod_str)
                    mtime_timestamp = last_modified_dt.timestamp()
                    os.utime(final_filepath, (mtime_timestamp, mtime_timestamp))
                    print(f"    -> Set mtime to {last_modified_dt.strftime('%Y-%m-%d %H:%M:%S')}")
                except Exception as e:
                    print(f"    ⚠️ Could not set mtime: {e}")

            print(f"    ✅ Download successful. Hashes and metadata updated.")

            # Download screenshots
            if screenshot_urls:
                print(f"    -> Found {len(screenshot_urls)} screenshots to download.")
                base_name_no_ext = filename_info.image_filename.removesuffix(".png")
                for i, image_url in enumerate(screenshot_urls):
                    sequence = i + 1
                    target_filename = f"{base_name_no_ext} ({sequence}).png"
                    target_path = ITCH_SCREENSHOT_DIR / target_filename

                    if target_path.exists():
                        continue # Already downloaded

                    if download_and_convert_gif_to_png(image_url, target_path, session):
                        print(f"        ✅ Downloaded screenshot {sequence} to {target_filename}")
                        # Fallback for the first image if no curated screenshot exists
                        if sequence == 1:
                            curated_screenshot_name = filename_info.image_filename
                            curated_screenshot_path = SCREENSHOT_DIR / curated_screenshot_name
                            if not curated_screenshot_path.exists():
                                _ = shutil.copy(target_path, curated_screenshot_path)
                                print(f"        -> Copied to screenshots (fallback): {curated_screenshot_name}")

        # else:
        #     # Mark as checked by setting a placeholder date
        #     row['itch_lastmodified_date'] = ''

    save_csv_database(CSV_DATABASE_PATH, db)
    print("--- Itch.io ROM Download Complete ---")