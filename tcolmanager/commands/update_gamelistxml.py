
from tcolmanager.config import CSV_DATABASE_PATH, GAMELISTXML_PATH
from tcolmanager.csv_manager import load_csv_database
from tcolmanager.filename_utils import generate_filename_and_gamename
from tcolmanager.gamelist_utils import generate_game_xml_entry
from tcolmanager.data_utils import get_primary_game_id, get_rom_category
from tcolmanager.data_utils import TColManagerArgs
from tcolmanager.utils import log_command

@log_command
def update_gamelistxml_command(args: TColManagerArgs):
    """Generates or updates the gamelist.xml file from the CSV database."""
    print("--- Starting gamelist.xml Update ---")
    db = load_csv_database(CSV_DATABASE_PATH)
    
    xml_content = ['<?xml version="1.0"?>', '<gameList>']

    # Filter and sort games to ensure a consistent order in the XML file
    valid_games = [row for row in db.values() if row.get("file_sha1")]
    sorted_games = sorted(valid_games, key=lambda r: (r.get("name_overwrite", "") or r.get("name_original_reference", "") or r.get("itch_titlename", "") or "").lower().strip())

    print(f"    -> Found {len(sorted_games)} downloaded games to include in gamelist.xml.")

    for row in sorted_games:
        filename_info = generate_filename_and_gamename(
            row, args.use_custom_filenames, args.use_custom_gamenames,
            args.filename_category_parenthesis, args.filename_case,
            args.rom_folder_organization
        )

        game_name = filename_info.gamename
        filename = filename_info.rom_filename

        # The path to the image folder is passed directly via args
        image_path_prefix = args.image_path.strip("./\\")

        game_entry = generate_game_xml_entry(
            row,
            filename,
            game_name,
            filename_info.image_filename,
            image_path_prefix
        )

        if game_entry:
            # Adjust path for multi-folder organization if needed
            if args.rom_folder_organization == "multiple" and (game_category := get_rom_category(row)):
                 game_entry = game_entry.replace(f"<path>./{filename}</path>", f"<path>./{game_category}/{filename}</path>")
            xml_content.append(game_entry)

    xml_content.append('</gameList>')

    try:
        final_xml_content = "\n".join(xml_content)
        GAMELISTXML_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(GAMELISTXML_PATH, "w", encoding="utf-8") as f:
            _ = f.write(final_xml_content)
        
        print(f"--- gamelist.xml updated successfully at {GAMELISTXML_PATH} ---")

    except Exception as e:
        print(f"    ❌ Failed to write gamelist.xml: {e}")