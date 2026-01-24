import json
from pathlib import Path

from tcolmanager.config import CSV_DATABASE_PATH
from tcolmanager.csv_manager import load_csv_database, save_csv_database
from tcolmanager.data_utils import TColManagerArgs
from tcolmanager.utils import log_command

AI_OUTPUT_PATH = Path("./output-ai-assistant")

@log_command
def import_json_command(_: TColManagerArgs):
    """Imports AI-generated data from JSON files into the CSV."""
    if not AI_OUTPUT_PATH.exists() or not AI_OUTPUT_PATH.is_dir():
        print(f"Error: AI output directory not found at {AI_OUTPUT_PATH}")
        return

    print(f"--- Starting JSON data import from {AI_OUTPUT_PATH} ---")

    # 1. Load all JSON data into a dict keyed by game ID
    json_data = {}
    json_files = list(AI_OUTPUT_PATH.glob("*.json"))
    for json_file in json_files:
        game_id = json_file.stem  # Get filename without extension
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Prepare data for import, mapping keys
                mapped_data = {}
                if 'description' in data:
                    mapped_data['overwrite_description'] = data['description']
                if 'genre' in data:
                    mapped_data['overwrite_genre'] = data['genre']
                if 'num_player' in data:
                    mapped_data['num_players'] = data['num_player']
                
                if mapped_data:
                    json_data[game_id] = mapped_data
        except json.JSONDecodeError:
            print(f"    [!] Warning: Could not parse {json_file}, skipping.")
        except Exception as e:
            print(f"    [!] Error reading {json_file}: {e}")
    
    print(f"    -> Found data for {len(json_data)} games in {len(json_files)} JSON files.")

    # 2. Load CSV and update rows
    db = load_csv_database(CSV_DATABASE_PATH)
    updated_rows = 0
    
    for game_id, data_to_update in json_data.items():
        if game_id in db:
            db[game_id].update(data_to_update)
            updated_rows += 1
        else:
            print(f"    [i] No matching entry in database for JSON file with ID: {game_id}")

    print(f"    -> Updated {updated_rows} rows in the database.")

    # 3. Save updated CSV
    save_csv_database(CSV_DATABASE_PATH, db)
    print("--- JSON data import complete. Database saved. ---")