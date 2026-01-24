import shutil
from pathlib import Path

from typing import Callable

from tcolmanager.config import ROMS_PATH, CSV_DATABASE_PATH, MEDIA_PATH
from tcolmanager.csv_manager import load_csv_database
from tcolmanager.filename_utils import FileInfo, generate_filename_and_gamename
from tcolmanager.data_utils import find_media_file, get_primary_game_id, get_rom_category
from tcolmanager.gamelist_utils import generate_game_xml_entry
from tcolmanager.data_utils import TColManagerArgs
from tcolmanager.utils import log_command

@log_command
def export_collection_command(args: TColManagerArgs):
    """Copies a filtered set of ROMs and media to a specified destination."""
    print("--- Starting Collection Export ---")
    if not args.dest_path:
        return

    db = load_csv_database(CSV_DATABASE_PATH) # Load the global database

    DEST_PATH = Path(args.dest_path)
    DEST_ROMS = DEST_PATH
    DEST_SCREENS = DEST_PATH / "screenshots"
    DEST_TITLES = DEST_PATH / "titlescreens"
    DEST_COVERS = DEST_PATH / "cart-covers"
    DEST_XML = DEST_PATH / "gamelist.xml"

    # Create all destination directories
    for d in [DEST_ROMS, DEST_SCREENS, DEST_TITLES, DEST_COVERS]:
        d.mkdir(parents=True, exist_ok=True)

    unusual_cat = ["WIP", "Demoscene", "Livecoding", "Music", "Tools", "Tech"]

    # Determine the export list based on criteria
    export_criteria: dict[str, Callable[[dict[str, str]], bool | str]] = {
        "export-all": lambda r: r.get("file_sha1") != "",
        "export-almost-all": lambda r: r.get("file_sha1") != "" and (game_category := get_rom_category(r)) and (
                                         ((game_category in unusual_cat) and r.get("include_in_collection") == "T") or
                                         ((game_category not in unusual_cat) and r.get("include_in_collection", "T") != "F")
                                       ),
        "export-curated-collection": lambda r: r.get("file_sha1") != "" and (game_category := get_rom_category(r)) and (
                                                ((game_category in unusual_cat) and r.get("include_in_curated_collection") == "T") or
                                                ((game_category not in unusual_cat) and r.get("include_in_curated_collection", "T") != "F")
                                               ),
        "export-curated-distribution-safe": lambda r: r.get("file_sha1") != "" and (game_category := get_rom_category(r)) and 
                                                    r.get("distribution_license", "T") != "F"
                                                and (
                                                ((game_category in unusual_cat) and r.get("include_in_curated_collection") == "T") or
                                                ((game_category not in unusual_cat) and r.get("include_in_curated_collection", "T") != "F")
                                               ),
    }

    if args.export_all:
        filter_func = export_criteria["export-all"]
    elif args.export_almost_all:
        filter_func = export_criteria["export-almost-all"]
    elif args.export_curated_distribution_safe:
        filter_func = export_criteria["export-curated-distribution-safe"]
    else: # Default: --export-curated-collection
        filter_func = export_criteria["export-curated-collection"]

    # lambda r: r.get("file_sha1") != "" and r.get("export") == "TRUE" 

    games_to_export = [r for r in db.values() if filter_func(r)]
    print(f"Found {len(games_to_export)} games to export.")

    # We must calculate the new SINGLE FOLDER FILENAME for the export
    exported_db: dict[str, dict[str, str]] = {}

    for row in games_to_export:
        game_id = get_primary_game_id(row)
        if not game_id:
            continue

        game_category = get_rom_category(row)

        # Generate filename as it exists in the source collection
        old_fileinfo = generate_filename_and_gamename(
            row, args.use_custom_filenames, args.use_custom_gamenames,
            args.filename_category_parenthesis, args.filename_case,
            args.rom_folder_organization
        )

        old_filename = old_fileinfo.rom_filename

        # Regenerate filename with single-folder rules for export
        new_fileinfo = generate_filename_and_gamename(
            row,
            use_custom_filenames=args.use_custom_filenames,
            use_custom_gamenames=args.use_custom_gamenames,
            filename_category_parenthesis=True,  # Always true for export
            filename_case=args.filename_case,
            rom_folder_organization="single"  # Always single for export
        )

        game_name = new_fileinfo.gamename
        new_filename = new_fileinfo.rom_filename

        # 1. Copy ROM
        rom_source_dir = ROMS_PATH / game_category if args.rom_folder_organization == "multiple" else ROMS_PATH
        old_filepath = rom_source_dir / old_filename
        new_filepath = DEST_ROMS / new_filename

        if old_filepath.exists():
            try:
                _ = shutil.copy2(old_filepath, new_filepath)
                print(f"    -> Exported ROM {game_id}: {old_filename} -> {new_filename}")

                # Update row's Filename and GameName for the exported XML
                export_row = row.copy()
                exported_db[game_id] = export_row

            except Exception as e:
                print(f"    ❌ Failed to copy ROM: {e}")

        # 2. Copy Media (Screenshots, Titlescreens, Covers)
        media_map = {
            "screenshots": (MEDIA_PATH / "screenshots", DEST_SCREENS, ".png"),
            "titlescreens": (MEDIA_PATH / "titlescreens", DEST_TITLES, ".png"),
            "cart-covers": (MEDIA_PATH / "cart-covers", DEST_COVERS, ".png"),
        }

        for media_type, (source_dir, dest_dir, ext) in media_map.items():
            old_media_path = find_media_file(source_dir, game_id)
            new_media_name = new_fileinfo.image_filename
            new_media_path = dest_dir / new_media_name

            if old_media_path:
                try:
                    _ = shutil.copy2(old_media_path, new_media_path)
                except Exception as e:
                    print(f"    ⚠️ Failed to copy {media_type}: {e}")

    # 3. Export gamelist.xml
    export_xml_content = ['<?xml version="1.0"?>', '<gameList>']

    # valid_games = [row for row in db.values() if row.get("file_sha1")]
    sorted_db = sorted(games_to_export, key=lambda r: (r.get("name_overwrite", "") or r.get("name_original_reference", "") or r.get("itch_titlename", "") or "").lower().strip())

    for row in sorted_db:
        # Regenerate filename and gamename for the export destination (single folder)
        new_fileinfo = generate_filename_and_gamename(
            row,
            use_custom_filenames=args.use_custom_filenames,
            use_custom_gamenames=args.use_custom_gamenames,
            filename_category_parenthesis=True,
            filename_case=args.filename_case,
            rom_folder_organization="single"
        )

        game_name = new_fileinfo.gamename
        new_filename = new_fileinfo.rom_filename

        game_entry = generate_game_xml_entry(
            row,
            new_filename,
            game_name,
            new_fileinfo.image_filename,
            "./screenshots"  # Image path for export is inside screenshots
        )
        if game_entry:
            export_xml_content.append(game_entry)


    export_xml_content.append('</gameList>')

    with open(DEST_XML, "w", encoding="utf-8") as f:
        _ = f.write("\n".join(export_xml_content))

    print(f"--- Collection Export Complete to {DEST_PATH} ---")