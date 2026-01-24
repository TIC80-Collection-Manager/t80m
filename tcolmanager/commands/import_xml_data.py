import xml.etree.ElementTree as ET
import re
from pathlib import Path

from tcolmanager.config import CSV_DATABASE_PATH
from tcolmanager.csv_manager import load_csv_database, save_csv_database
from tcolmanager.data_utils import TColManagerArgs
from tcolmanager.utils import log_command

def extract_id_from_path(path_str: str) -> str | None:
    """Extracts game ID from a filename path like ... - 1234 (...).tic"""
    match = re.search(r' - (\d+) \(', path_str)
    if match:
        return match.group(1)
    return None

@log_command
def import_xml_data_command(args: TColManagerArgs):
    """Imports additional metadata from an external XML file into the CSV."""
    if not args.xml_file:
        print("Error: No XML file path provided.")
        return

    xml_path = Path(args.xml_file)
    if not xml_path.exists():
        print(f"Error: XML file not found at {xml_path}")
        return

    print(f"--- Starting XML data import from {xml_path} ---")

    # 1. Parse XML and store data in a dict keyed by game ID
    xml_data = {}
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        for game_elem in root.findall('game'):
            path_elem = game_elem.find('path')
            if path_elem is not None and path_elem.text:
                game_id = extract_id_from_path(path_elem.text)
                if game_id:
                    data = {}
                    # sscrp_id2 from <game id="...">
                    sscrp_id2 = game_elem.get('id')
                    if sscrp_id2:
                        data['sscrp_id2'] = sscrp_id2
                    
                    # sscrp_description from <desc>
                    desc_elem = game_elem.find('desc')
                    if desc_elem is not None and desc_elem.text:
                        data['sscrp_description'] = desc_elem.text.strip().replace('\n', '\\n')
                    
                    # sccrp_genre from <genre>
                    genre_elem = game_elem.find('genre')
                    if genre_elem is not None and genre_elem.text:
                        data['sccrp_genre'] = genre_elem.text.strip()

                    # num_players from <players>
                    players_elem = game_elem.find('players')
                    if players_elem is not None and players_elem.text:
                        data['num_players'] = players_elem.text.strip()
                    
                    if data:
                        xml_data[game_id] = data
    except ET.ParseError as e:
        print(f"Error parsing XML file: {e}")
        return
    
    print(f"    -> Found data for {len(xml_data)} games in the XML file.")

    # 2. Load CSV and update rows
    db = load_csv_database(CSV_DATABASE_PATH)
    updated_rows = 0
    # Create a list of items to iterate over to allow modification of the db dict
    for row_id, row in list(db.items()):
        game_id_from_csv = row.get('id')
        if game_id_from_csv and game_id_from_csv in xml_data:
            db[row_id].update(xml_data[game_id_from_csv])
            updated_rows += 1
            
    print(f"    -> Updated {updated_rows} rows in the database.")

    # 3. Save updated CSV
    save_csv_database(CSV_DATABASE_PATH, db)
    print("--- XML data import complete. Database saved. ---")