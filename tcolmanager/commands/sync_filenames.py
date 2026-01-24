from datetime import datetime
import os
import shutil

from tcolmanager.config import ROMS_PATH, CSV_DATABASE_PATH
from tcolmanager.csv_manager import load_csv_database, save_csv_database
from tcolmanager.filename_utils import generate_filename_and_gamename
from tcolmanager.data_utils import find_game_file, get_primary_game_id, get_rom_category
from tcolmanager.data_utils import TColManagerArgs
from tcolmanager.media_utils import sync_media_for_game
from tcolmanager.utils import log_command

@log_command
def sync_filenames_command(args: TColManagerArgs):
    """
    Uses the latest CSV data to rename ROMs and media files on disk.
    This is run when a user updates `name_overwrite` manually in the CSV.
    """
    print("--- Starting Filename Synchronization ---")
    db = load_csv_database(CSV_DATABASE_PATH) # Load the global database

    for _, row in db.items():
        if not row.get("file_sha1"): # Can't sync if we never downloaded it
            continue

        current_game_id = get_primary_game_id(row)
        if not current_game_id:
            continue

        # 1. ROM Renaming
        old_filepath = find_game_file(ROMS_PATH, current_game_id, args.rom_folder_organization)

        if not old_filepath:
            continue # Skip if file not found on disk

        filename_info = generate_filename_and_gamename(
            row, args.use_custom_filenames, args.use_custom_gamenames,
            args.filename_category_parenthesis, args.filename_case,
            args.rom_folder_organization
        )

        new_filename = filename_info.rom_filename
        
        rom_target_dir = ROMS_PATH / get_rom_category(row) if args.rom_folder_organization == "multiple" else ROMS_PATH
        new_filepath = rom_target_dir / new_filename

        

        if old_filepath.resolve() != new_filepath.resolve():
            print(f"[+] Syncing ROM {current_game_id}: {old_filepath.name} -> {new_filename}")
            try:
                # Ensure target directory exists for multi-folder organization
                rom_target_dir.mkdir(parents=True, exist_ok=True)
                _ = shutil.move(old_filepath, new_filepath)
            except Exception as e:
                print(f"    ❌ Failed to sync ROM: {e}")

        # 2. Media Renaming
        sync_media_for_game(row, filename_info.image_filename, args)

        # Set mtime if available
        selected_ts = None

        # 1. Check for overwrite timestamp first
        overwrite_ts_str = row.get("overwrite_upd_timestamp")
        if overwrite_ts_str:
            try:
                selected_ts = float(overwrite_ts_str)
            except (ValueError, TypeError):
                pass

        # 2. If not found, check tic80com source
        if not selected_ts and row.get("source_with_bestversion", "tic80com") == "tic80com":
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

        # 3. Otherwise, use itch timestamps
        if not selected_ts:
            itch_upd_ts_str = row.get("itch_upd_timestamp")
            itch_lastmod_ts_str = row.get("itch_lastmodified_timestamp")
            itch_pub_ts_str = row.get("itch_pub_timestamp")
            
            itch_upd_ts = None
            itch_lastmod_ts = None
            
            if itch_upd_ts_str:
                try:
                    itch_upd_ts = float(itch_upd_ts_str)
                except (ValueError, TypeError):
                    pass
            
            if itch_lastmod_ts_str:
                try:
                    itch_lastmod_ts = float(itch_lastmod_ts_str)
                except (ValueError, TypeError):
                    pass
            
            if itch_upd_ts and itch_lastmod_ts:
                selected_ts = min(itch_upd_ts, itch_lastmod_ts)
            elif itch_upd_ts:
                selected_ts = itch_upd_ts
            elif itch_lastmod_ts:
                selected_ts = itch_lastmod_ts
            elif itch_pub_ts_str:
                try:
                    selected_ts = float(itch_pub_ts_str)
                except (ValueError, TypeError):
                    pass

        if new_filepath.exists() and selected_ts:
            try:
                # Check if mtime is already set correctly
                current_mtime = os.path.getmtime(new_filepath)
                if current_mtime != selected_ts:
                    upd_dt = datetime.fromtimestamp(selected_ts)
                    os.utime(new_filepath, (selected_ts, selected_ts))
                    print(f"    -> mtime changed from {datetime.fromtimestamp(current_mtime).strftime('%Y-%m-%d %H:%M:%S')} ({current_mtime}) to {upd_dt.strftime('%Y-%m-%d %H:%M:%S')} ({selected_ts})")
            except (ValueError, TypeError) as e:
                print(f"    ⚠️ Could not set mtime for {new_filename}: Invalid timestamp. Error: {e}")
            except Exception as e:
                print(f"    ⚠️ Could not set mtime for {new_filename}: {e}")

    save_csv_database(CSV_DATABASE_PATH, db)
    print("--- Filename Synchronization Complete ---")