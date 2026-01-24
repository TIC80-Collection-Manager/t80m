import requests

from tcolmanager.config import CSV_DATABASE_PATH, HEADERS, API_CATEGORIES, DEFAULT_FIELDNAMES
from tcolmanager.csv_manager import load_csv_database, save_csv_database
from tcolmanager.data_utils import TColManagerArgs
from tcolmanager.tic80_api_client import api_response_to_list
from tcolmanager.filename_utils import sanitize_game_title_name, generate_filename_and_gamename
from tcolmanager.utils import log_command

@log_command
def update_tic_csv_command(args: TColManagerArgs):
    """Fetches data from the TIC-80 API, updates the local CSV database, and saves the changes."""
    print("--- Starting CSV Database Update (tic80.com) ---")

    # Load the global database
    db = load_csv_database(CSV_DATABASE_PATH)
    session = requests.Session()
    session.headers.update(HEADERS)

    tic_id_to_db_id = {row.get('tic_id'): id for id, row in db.items() if row.get('tic_id')}

    new_entries_count = 0
    updated_md5_count = 0
    skipped_count = 0

    for game_category, api_path in API_CATEGORIES.items():
        api_url = f"https://tic80.com/api?fn=dir&path={api_path}"
        print(f"\nFetching {game_category} from {api_url}...")

        try:
            response = session.get(api_url, timeout=30)
            response.raise_for_status()
            api_list = api_response_to_list(response.text)
        except Exception as e:
            print(f"⚠️ Network error for {game_category}: {e}")
            continue

        print(f"Found {len(api_list)} entries.")

        for api_game in api_list:
            game_id = api_game["id"]
            api_md5 = api_game["tic_md5"]
            api_filename_for_url = api_game["filename"]

            sanitized_name = sanitize_game_title_name(api_game["name"])
            download_url = f"https://tic80.com/cart/{api_md5}/{api_filename_for_url}"

            if game_id not in tic_id_to_db_id:
                # New entry: Initialize with default fields and set source
                row = {field: "" for field in DEFAULT_FIELDNAMES if field not in ["id", "tic_id"]}
                row["name_original_reference"] = sanitized_name
                row["id"] = game_id
                row["tic_id"] = game_id
                row["tic_category"] = game_category
                row["tic_md5"] = api_md5
                row["download_url"] = download_url
                row["include_in_collection"] = ""
                row["include_in_curated_collection"] = ""
                row["source_with_bestversion"] = ""

                db[game_id] = row
                tic_id_to_db_id[game_id] = game_id # Add to lookup

                new_entries_count += 1
                print(f"✅ Added new entry {game_id}: {sanitized_name}")

            else:
                # Existing entry
                db_id = tic_id_to_db_id[game_id]
                row = db[db_id]
                source_version = row.get("source_with_bestversion", "").strip().lower()

                # If source_with_bestversion is set to something other than 'tic80com' and is not empty, skip update
                if source_version and source_version != "tic80com":
                    # print(f"    [i] Skipping update for {game_id} ({row.get('GameName', sanitized_name)}) as source_with_bestversion is '{row['source_with_bestversion']}'.")
                    skipped_count += 1
                    continue
                
                # Always update name, category, and URL from API, and regenerate GameName
                # This ensures local data reflects website changes even if the cart file is the same.
                row["name_original_reference"] = sanitized_name
                row["download_url"] = download_url
                row["tic_category"] = game_category # Update tic_category in case it changed on tic80.com

                if row.get("tic_md5") != api_md5:
                    updated_md5_count += 1
                    filename_info= generate_filename_and_gamename(row, args.use_custom_filenames, args.use_custom_gamenames, args.filename_category_parenthesis, args.filename_case, args.rom_folder_organization)
                    
                    game_name = filename_info.gamename

                    print(f"⚠️ Updated MD5 for {game_id} ({game_name})")

                    row["tic_md5"] = api_md5

                    # Clear fields that need re-validation/download because the file has changed
                    row["file_md5"] = ""
                    row["file_sha1"] = ""
                    row["file_CRC"] = ""
                    row["tic_upd_timestamp"] = ""
                    row["tic_upd_date"] = ""

    print(f"\n--- Update Summary ---\nNew: {new_entries_count}, Updated MD5: {updated_md5_count}, Skipped (non-tic80com source): {skipped_count}")
    save_csv_database(CSV_DATABASE_PATH, db)
    print("--- CSV Database Update Complete ---")