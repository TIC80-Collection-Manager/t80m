from tcolmanager.config import CSV_DATABASE_PATH, DEFAULT_FIELDNAMES
from tcolmanager.csv_manager import load_csv_database, save_csv_database
from tcolmanager.itch_api_client import scrape_itch_games
from tcolmanager.data_utils import TColManagerArgs
from tcolmanager.utils import log_command

@log_command
def update_itch_csv_command(_: TColManagerArgs):
    """Fetches data from Itch.io and updates the local CSV database."""
    print("--- Starting CSV Database Update (Itch.io) ---")

    db = load_csv_database(CSV_DATABASE_PATH)
    
    # Create a quick lookup map for existing itch_id
    itch_id_to_db_id = {row.get('itch_id'): id for id, row in db.items() if row.get('itch_id')}
    
    new_entries = 0
    updated_entries = 0

    for game_data in scrape_itch_games():
        itch_id = game_data['itch_id']
        
        if itch_id not in itch_id_to_db_id:
            # New entry
            row = {field: "" for field in DEFAULT_FIELDNAMES}
            row.update(game_data)
            row['id'] = itch_id # Set primary ID
            row['name_original_reference'] = row['itch_titlename']
            row['rom_category'] = 'Itch'
            row['source_with_bestversion'] = 'itch'
            
            db[itch_id] = row
            itch_id_to_db_id[itch_id] = itch_id # Add to lookup
            
            print(f"    -> Added new Itch entry {itch_id}: {game_data['itch_titlename']}")
            new_entries += 1

        else:
            # Existing entry
            db_id = itch_id_to_db_id[itch_id]
            row = db[db_id]
            
            try:
                previous_upd = int(float(row.get('itch_upd_timestamp', "0")))
            except Exception:
                previous_upd = 0
            
            # Update fields from scrape
            row.update(game_data)

            # print(f"{game_data['itch_titlename']} previous: {previous_upd}, current: {game_data['itch_upd_timestamp']}")
            
            if previous_upd < int(float(game_data['itch_upd_timestamp'])):
                # There is an update, but we don't know if it is just the page description or the actual cart.
                # Clear last modified date to signal re-download check
                row['itch_lastmodified_date'] = ''
                row['itch_lastmodified_timestamp'] = ''
                print(f"    -> Possible update available for Itch entry {itch_id}: {game_data['itch_titlename']}")
            
            # print(f"    -> Updated existing Itch entry {itch_id}: {game_data['itch_titlename']}")
            updated_entries += 1

    print(f"\n--- Itch.io Update Summary ---\nNew: {new_entries}, Updated: {updated_entries}")
    save_csv_database(CSV_DATABASE_PATH, db)
    print("--- Itch.io CSV Database Update Complete ---")