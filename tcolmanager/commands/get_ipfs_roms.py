import shutil
import requests

from tcolmanager.config import (
    ROMS_PATH,
    CSV_DATABASE_PATH,
    OLD_ROMS_PATH,
    MEDIA_PATH,
    HEADERS,
    IPFS_GATEWAYS,
)
from tcolmanager.csv_manager import load_csv_database, save_csv_database
from tcolmanager.filename_utils import generate_filename_and_gamename
from tcolmanager.data_utils import (
    find_game_file,
    find_media_file,
    get_hashes,
    get_primary_game_id,
    set_mtime,
    # get_rom_category,
)
from tcolmanager.data_utils import TColManagerArgs
from tcolmanager.utils import log_command

@log_command
def get_ipfs_roms_command(args: TColManagerArgs):
    """
    Downloads missing or out‑of‑date ROMs whose source is IPFS.
    Logic mirrors the TIC‑80 downloader but fetches the cartridge
    from a list of public IPFS gateways.
    """
    print("--- Starting ROM Download (IPFS) ---")
    db = load_csv_database(CSV_DATABASE_PATH)

    session = requests.Session()
    session.headers.update(HEADERS)

    # ------------------------------------------------------------------
    # Build the list of rows we should process
    # ------------------------------------------------------------------
    rows_to_process = [
        r for r in db.values()
        if (r.get("source_with_bestversion", "").strip().lower() == "ipfs")
        and r.get("ipfs_cid")
    ]

    print(f"Found {len(rows_to_process)} IPFS entries to check.")

    for row in rows_to_process:
        game_id = get_primary_game_id(row)
        if not game_id:
            continue

        cid = row["ipfs_cid"]
        filename_info = generate_filename_and_gamename(
            row,
            args.use_custom_filenames,
            args.use_custom_gamenames,
            args.filename_category_parenthesis,
            args.filename_case,
            args.rom_folder_organization,
        )
        game_name = filename_info.gamename

        print(f"\n[+] Processing {game_id} ({game_name})")

        # --------------------------------------------------------------
        # Determine target filename (may change after we fetch timestamps)
        # --------------------------------------------------------------
        # pre_fname, _gname, target_fname = generate_filename_and_gamename(
        #     row,
        #     args.use_custom_filenames,
        #     args.use_custom_gamenames,
        #     args.filename_category_parenthesis,
        #     args.filename_case,
        #     args.rom_folder_organization,
        # )

        target_fname = filename_info.rom_filename

        rom_target_dir = (
            ROMS_PATH / row["rom_category"]
            if args.rom_folder_organization == "multiple"
            else ROMS_PATH
        )
        new_filepath = rom_target_dir / target_fname

        # --------------------------------------------------------------
        # Check existing local file / hashes
        # --------------------------------------------------------------
        old_filepath = find_game_file(ROMS_PATH, game_id, args.rom_folder_organization)
        should_download = True

        if old_filepath and old_filepath.exists():
            # Compute current hashes
            file_md5, file_sha1, _ = get_hashes(old_filepath)

            # If we have a stored SHA1, compare it; otherwise fall back to MD5.
            stored_sha1 = row.get("file_sha1", "").strip()
            if stored_sha1 and file_sha1.lower() == stored_sha1.lower():
                should_download = False
                # Rename if filename changed
                if old_filepath.resolve() != new_filepath.resolve():
                    print(f"    -> Renaming file: {old_filepath.name} -> {target_fname}")
                    new_filepath.parent.mkdir(parents=True, exist_ok=True)
                    _ = shutil.move(old_filepath, new_filepath)
                else:
                    print("    -> ROM already up‑to‑date.")
            else:
                # Mismatch – move the old file to the backup folder
                print("    -> Existing ROM differs (hash mismatch). Moving to backup.")
                OLD_ROMS_PATH.mkdir(exist_ok=True)
                try:
                    _ = shutil.move(old_filepath, OLD_ROMS_PATH / old_filepath.name)
                except Exception as e:
                    print(f"    ⚠️ Failed to move old ROM: {e}")

        # --------------------------------------------------------------
        # Download from IPFS gateways if needed
        # --------------------------------------------------------------
        if should_download:
            success = False
            for gw in IPFS_GATEWAYS:
                url = f"https://{gw}/ipfs/{cid}"
                print(f"    -> Trying gateway {gw} ...")
                try:
                    # Re‑use the generic download_file helper (handles mtime)
                    from tcolmanager.tic80_api_client import download_file

                    lastmod_ts = download_file(url, new_filepath, session)

                    if lastmod_ts is not None:
                        success = True
                        print(f"    ✅ Download succeeded via {gw}")

                        selected_ts = None

                        # 1. Check for overwrite timestamp first
                        overwrite_ts_str = row.get("overwrite_upd_timestamp")
                        if overwrite_ts_str:
                            try:
                                selected_ts = float(overwrite_ts_str)
                            except (ValueError, TypeError):
                                pass

                        # 2. Otherwise, use itch timestamps
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
                            
                        if selected_ts:
                            _ = set_mtime(new_filepath, selected_ts)
                        break
                except Exception as e:
                    print(f"    ❌ Error with gateway {gw}: {e}")

            if not success:
                print(f"    ❌ All gateways failed for CID {cid}. Skipping.")
                continue

            # ----------------------------------------------------------
            # Update CSV with new hashes
            # ----------------------------------------------------------
            file_md5, file_sha1, crc = get_hashes(new_filepath)
            row.update({"file_md5": file_md5, "file_sha1": file_sha1, "file_CRC": crc})

        # --------------------------------------------------------------
        # Rename / move associated media (screenshots, titlescreens, covers)
        # --------------------------------------------------------------
        media_map = {
            "screenshots": (MEDIA_PATH / "screenshots", ".png"),
            "titlescreens": (MEDIA_PATH / "titlescreens", ".png"),
            "cart-covers": (MEDIA_PATH / "cart-covers", ".png"),
        }
        for media_type, (media_dir, ext) in media_map.items():
            old_media_path = find_media_file(media_dir, game_id)
            if old_media_path:
                new_media_name = filename_info.image_filename
                new_media_path = media_dir / new_media_name
                if old_media_path.name != new_media_path.name:
                    print(
                        f"    -> Renaming {media_type} for {game_id}: {old_media_path.name} -> {new_media_name}"
                    )
                    try:
                        _ = shutil.move(old_media_path, new_media_path)
                    except Exception as e:
                        print(f"    ⚠️ Failed to rename media: {e}")

    # --------------------------------------------------------------
    # Persist changes
    # --------------------------------------------------------------
    save_csv_database(CSV_DATABASE_PATH, db)
    print("--- IPFS ROM Download Complete ---")