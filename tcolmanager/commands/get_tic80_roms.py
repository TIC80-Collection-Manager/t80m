from pathlib import Path
from typing import Any, Callable, Literal


import shutil
import requests

from tcolmanager.config import ROMS_PATH, CSV_DATABASE_PATH, OLD_ROMS_PATH, MEDIA_PATH, HEADERS
from tcolmanager.csv_manager import load_csv_database, save_csv_database
from tcolmanager.data_utils import TColManagerArgs, find_media_file, set_mtime
from tcolmanager.tic80_api_client import parse_playpage, download_file, download_and_convert_gif_to_png
from tcolmanager.filename_utils import generate_filename_and_gamename
from tcolmanager.data_utils import find_game_file, get_hashes, get_primary_game_id, get_rom_category
from tcolmanager.utils import log_command

@log_command
def get_tic_roms_command(args: TColManagerArgs):
    """
    Downloads missing or updated ROMs, updates CSV with metadata, and handles
    file renaming/moving.
    """
    print("--- Starting ROM and Metadata Download (tic80.com) ---")
    db = load_csv_database(CSV_DATABASE_PATH) # Load the global database

    session = requests.Session()
    session.headers.update(HEADERS)

    unusual_cat = ["WIP", "Demoscene", "Livecoding", "Music", "Tools", "Tech"]
    
    # Determine the download list based on criteria (without sha1 check)
    download_criteria: dict[str, Callable[[dict[str, str]], bool | str]] = {
        "download-all": lambda r: True, # Process all entries
        "download-almost-all": lambda r: (game_category := get_rom_category(r)) and (
                                         ((game_category in unusual_cat) and r.get("include_in_collection", "F") == "T") or
                                         ((game_category not in unusual_cat) and r.get("include_in_collection", "T") != "F")
                                       ),
        "download-curated-collection": lambda r: (game_category := get_rom_category(r)) and (
                                                ((game_category in unusual_cat) and r.get("include_in_curated_collection", "F") == "T") or
                                                ((game_category not in unusual_cat) and r.get("include_in_curated_collection", "T") != "F")
                                               ),
    }

    if args.download_all:
        filter_func = download_criteria["download-all"]
    elif args.download_almost_all:
        filter_func = download_criteria["download-almost-all"]
    else: # Default: --download-curated-collection (implicitly)
        filter_func = download_criteria["download-curated-collection"]
    
    games_to_process: list[dict[str, str]] = [r for r in db.values() if (filter_func(r) and not r.get("file_sha1", ""))]

    # Apply source_with_bestversion filter: Only process if source is 'tic80com' or empty
    filtered_games_to_process: list[dict[str, str]] = []
    skipped_source_count = 0
    for row in games_to_process:
        source_version = row.get("source_with_bestversion", "").strip().lower()
        if source_version and source_version != "tic80com":
            filename_info = generate_filename_and_gamename(row, args.use_custom_filenames, args.use_custom_gamenames, args.filename_category_parenthesis, args.filename_case, args.rom_folder_organization)
            game_name = filename_info.gamename
            print(f"[i] Skipping download for {get_primary_game_id(row)} ({game_name}) as source_with_bestversion is '{row['source_with_bestversion']}'.")
            skipped_source_count += 1
            continue
        filtered_games_to_process.append(row)

    games_to_process = filtered_games_to_process
    print(f"Found {len(games_to_process)} games to download/update (skipped {skipped_source_count} due to source_with_bestversion).")

    for row in games_to_process:
        game_id = get_primary_game_id(row)
        api_md5 = row.get("tic_md5", "")

        # Generate what the filename should be
        filename_info = generate_filename_and_gamename(
            row, args.use_custom_filenames, args.use_custom_gamenames,
            args.filename_category_parenthesis, args.filename_case,
            args.rom_folder_organization
        )
        game_name = filename_info.gamename
        new_filename = filename_info.rom_filename

        # 1. Scrap metadata from play page (do this early to get updated date for filename)
        play_url = f"https://tic80.com/play?cart={game_id}"
        print(f"\n[+] Processing {game_id} ({game_name})")
        
        if not game_id:
            continue

        try:
            resp = session.get(play_url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            metadata = parse_playpage(resp.text)
            row.update(metadata) # Update CSV row with new metadata

            # Ensure required timestamps are set for filename generation
            if not row.get("tic_upd_timestamp") and row.get("tic_pub_timestamp"):
                row["tic_upd_timestamp"] = row["tic_pub_timestamp"]
                row["tic_upd_date"] = row["tic_pub_date"]

        except Exception as e:
            print(f"    ❌ Failed to fetch/parse play page: {e}. Skipping download.")
            continue

        # 2. Re-generate filename with potentially new date metadata
        filename_info = generate_filename_and_gamename(
            row, args.use_custom_filenames, args.use_custom_gamenames,
            args.filename_category_parenthesis, args.filename_case,
            args.rom_folder_organization
        )

        game_name = filename_info.gamename
        new_filename = filename_info.rom_filename

        # Determine the target path
        rom_target_dir = ROMS_PATH / row["tic_category"] if args.rom_folder_organization == "multiple" else ROMS_PATH
        new_filepath = rom_target_dir / new_filename

        # Search for existing file
        old_filepath = find_game_file(ROMS_PATH, game_id, args.rom_folder_organization)
        
        should_download = True
        if old_filepath and old_filepath.exists():
            file_md5, _, _ = get_hashes(old_filepath)
            if file_md5.lower() == api_md5.lower():
                print(f"    -> ROM is up-to-date (MD5 match).")
                should_download = False
                # If name is different, just rename it.
                if old_filepath.resolve() != new_filepath.resolve():
                    print(f"    -> Correcting filename: {old_filepath.name} -> {new_filename}")
                    _ = new_filepath.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        _ = shutil.move(old_filepath, new_filepath)
                    except Exception as e:
                        print(f"    ⚠️ Failed to rename ROM: {e}")
            else:
                print(f"    -> MD5 mismatch. Expected {api_md5[:7]}, got {file_md5[:7]}. Re-downloading.")

        if old_filepath and should_download:
             print(f"    -> Moving old ROM {old_filepath.name} to {OLD_ROMS_PATH.name}/...")
             OLD_ROMS_PATH.mkdir(exist_ok=True)
             try:
                 _ = shutil.move(old_filepath, OLD_ROMS_PATH / old_filepath.name)
             except Exception as e:
                 print(f"    ⚠️ Failed to move old ROM: {e}")

        # 3. Download if needed
        if should_download:
            if row.get("download_url"):
                download_url = row["download_url"]
                print(f"    -> Downloading from {download_url}...")
                try:
                    lastmod_ts = download_file(download_url, new_filepath, session)
                    if lastmod_ts is not None:
                        file_md5, file_sha1, crc = get_hashes(new_filepath)
                        if file_md5.lower() != api_md5.lower():
                             print(f"    ⚠️ MD5 Mismatch after download: Expected {api_md5[:7]}, Got {file_md5[:7]}. Keeping file.")
                        else:
                            print("    -> Download successful and MD5 matches. ✅")
                        # Update CSV with file info
                        row.update({"file_md5": file_md5, "file_sha1": file_sha1, "file_CRC": crc})

                        selected_ts = None

                        # 1. Check for overwrite timestamp first
                        overwrite_ts_str = row.get("overwrite_upd_timestamp")
                        if overwrite_ts_str:
                            try:
                                selected_ts = float(overwrite_ts_str)
                            except (ValueError, TypeError):
                                pass

                        # 2. If not found, check tic80com source
                        if not selected_ts:
                            tic_upd_ts_str = row.get("tic_upd_timestamp")
                            tic_pub_ts_str = row.get("tic_pub_timestamp")
                            
                            if tic_upd_ts_str:
                                try:
                                    selected_ts = float(tic_upd_ts_str)
                                except (ValueError, TypeError):
                                    pass
                            elif tic_pub_ts_str:
                                try:
                                    selected_ts = float(tic_pub_ts_str)
                                except (ValueError, TypeError):
                                    pass
                            if lastmod_ts > 0:
                                selected_ts = min (lastmod_ts, selected_ts) if selected_ts else lastmod_ts
                        if selected_ts is not None:
                            _ = set_mtime(new_filepath, selected_ts)

                    else:
                        print(f"    ❌ Download function failed for {download_url}")

                except requests.exceptions.RequestException as e:
                    print(f"    ❌ Download failed: {e}")
            else:
                print(f"    ❌ Download URL missing.")
        else: # not should_download
            pass # ROM is up to date, just continue to media renaming

        # 4. Rename/Move associated media and download missing covers
        media_map: dict[str, tuple[Path, str]] = {
            "screenshots": (MEDIA_PATH / "screenshots", ".png"),
            "titlescreens": (MEDIA_PATH / "titlescreens", ".png"),
            "cart-covers": (MEDIA_PATH / "cart-covers", ".png"),
        }

        # First pass: check existing media and rename if needed
        existing_media: dict[str, Path] = {}
        missing_media: dict[str, Path] = {}

        for media_type, (media_dir, ext) in media_map.items():
            old_media_path = find_media_file(media_dir, game_id)
            new_media_name = filename_info.image_filename
            new_media_path = media_dir / new_media_name

            if old_media_path:
                if old_media_path.name != new_media_path.name:
                    print(f"    -> Renaming {media_type.capitalize()} for {game_id}: {old_media_path.name} -> {new_media_name}")
                    try:
                        _ = shutil.move(old_media_path, new_media_path)
                    except Exception as e:
                        print(f"    ⚠️ Failed to rename media: {e}")
                existing_media[media_type] = new_media_path
            else:
                missing_media[media_type] = new_media_path

        # Determine cover source and handle download
        cover_source_path = None

        if should_download or "cart-covers" in missing_media:
            # Download cover art in case it is missing or if new update
            download_target: Path = (MEDIA_PATH / "cart-covers") / filename_info.image_filename
            gif_url = f"https://tic80.com/cart/{api_md5.lower()}/cover.gif"
            print(f"    -> Downloading cover for {game_id} ({game_name})")
            if download_and_convert_gif_to_png(gif_url, download_target, session):
                cover_source_path = download_target
                # Remove from missing since we just created/updated it
                if "cart-covers" in missing_media:
                    existing_media["cart-covers"] = missing_media["cart-covers"]
                    del missing_media["cart-covers"]

        if "cart-covers" in existing_media:
            cover_source_path = existing_media["cart-covers"]
        elif "titlescreens" in existing_media:
            cover_source_path = existing_media["titlescreens"]
        
        # Copy cover to missing locations
        if cover_source_path and cover_source_path.exists() and "screenshots" in missing_media:
            target_path : Path = missing_media["screenshots"]
            print(f"    -> Copying cover to screenshots for {game_id}")
            target_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                _ = shutil.copy2(cover_source_path, target_path)
            except Exception as e:
                print(f"    ⚠️ Failed to copy media: {e}")

    save_csv_database(CSV_DATABASE_PATH, db)
    print("--- ROM and Metadata Download Complete ---")