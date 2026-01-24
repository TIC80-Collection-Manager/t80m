from tcolmanager.config import ROMS_PATH, CSV_DATABASE_PATH
from tcolmanager.csv_manager import load_csv_database, save_csv_database
from tcolmanager.data_utils import get_hashes, get_primary_game_id, find_game_file
from tcolmanager.data_utils import TColManagerArgs
from tcolmanager.utils import log_command

@log_command
def recalculate_hashes_command(args: TColManagerArgs):
    """Recalculates hashes for local ROM files based on 'source_with_bestversion' and updates the CSV."""
    print("--- Starting Hash Recalculation ---")
    db = load_csv_database(CSV_DATABASE_PATH)
    updated_count = 0
    files_processed_count = 0

    print(f"Processing {len(db)} entries from the database.")

    # Iterate over each entry in the database
    for _, row in db.items():
        primary_game_id = get_primary_game_id(row)

        if not primary_game_id:
            # This case can be logged if necessary.
            continue
        
        # Find the game file corresponding to the primary ID
        filepath = find_game_file(ROMS_PATH, primary_game_id, args.rom_folder_organization)

        if not filepath:
            # This case can be logged if necessary, e.g., when a ROM is not downloaded yet.
            continue

        files_processed_count += 1
        md5_new, sha1_new, crc_new = get_hashes(filepath)

        if (row.get("file_md5") != md5_new or
            row.get("file_sha1") != sha1_new or
                row.get("file_CRC") != crc_new):

            print(f"[+] Updating hashes for {primary_game_id} ({filepath.name})")
            row["file_md5"] = md5_new
            row["file_sha1"] = sha1_new
            row["file_CRC"] = crc_new
            updated_count += 1
    
    print(f"Processed {files_processed_count} ROM files.")

    if updated_count > 0:
        save_csv_database(CSV_DATABASE_PATH, db)
        print(f"--- Hash Recalculation Complete: {updated_count} entries updated ---")
    else:
        print("No hash updates were needed.")
        print("--- Hash Recalculation Complete ---")