import argparse
import signal
import sys


# Import configurations
from tcolmanager.config import (
    CONFIG_FILE_PATH, CSV_DATABASE_PATH, ROMS_PATH, MEDIA_PATH, ALL_TYPES_FOLDERS
)

# Import CSV manager for global DB and signal handling
from tcolmanager.csv_manager import signal_handler

# Import command functions
from tcolmanager.commands import (
    update_csv_dispatcher, get_roms_dispatcher, sync_filenames_command,
    get_coverarts_command, update_gamelistxml_command, recalculate_hashes_command,
    export_collection_command, import_xml_data_command, ai_assistant_command,
    import_json_command, init_command
)
from tcolmanager.data_utils import TColManagerArgs
from tcolmanager.utils.cli_completion import export_carapace_spec


def main():
    
    parser = argparse.ArgumentParser(
        description="TIC-80 Collection Manager CLI",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=f"""
Configuration file: {CONFIG_FILE_PATH}
ROMs: {ROMS_PATH}
Database: {CSV_DATABASE_PATH}
Media: {MEDIA_PATH}"""
    )

    # Register signal handler for graceful shutdown
    _ = signal.signal(signal.SIGINT, signal_handler)
    _ = signal.signal(signal.SIGTERM, signal_handler)

    # --- Global/Shared Arguments ---
    rom_folder_organization_default = "single"
    if ROMS_PATH.is_dir():
        # Check for existence of any of the category subfolders
        if any((ROMS_PATH / folder).is_dir() for folder in ALL_TYPES_FOLDERS):
            rom_folder_organization_default = "multiple"

    _ = parser.add_argument(
        "--rom-folder-organization",
        choices=["single", "multiple"],
        default=rom_folder_organization_default,
        help="Organize ROMs in 'single' (root) or 'multiple' (subfolders like Games, WIP)."
    )

    _ = parser.add_argument(
        "--filename-category-parenthesis",
        type=lambda x: x.lower() == 'true',
        default=True,
        help="Add category in parenthesis (Tool, WIP, etc.) to filenames. Default: True."
    )
    _ = parser.add_argument(
        "--use-custom-filenames",
        type=lambda x: x.lower() == 'true',
        default=True,
        help="Use 'name_overwrite' for filenames when available. Default: True."
    )
    _ = parser.add_argument(
        "--use-custom-gamenames",
        type=lambda x: x.lower() == 'true',
        default=True,
        help="Use 'name_overwrite' for GameName metadata. Default: True."
    )
    _ = parser.add_argument(
        "--filename-case",
        choices=["unchanged", "uppercase", "lowercase"],
        default="uppercase",
        help="Set the case for the main part of the filename. Default: uppercase."
    )

    # --- Subcommands ---
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # updatecsv command
    update_parser = subparsers.add_parser("updatecsv", help="Update the local games_info.csv from a source.")
    _ = update_parser.add_argument("source", choices=["tic80com", "itch"], help="The source to update from.")
    update_parser.set_defaults(func=update_csv_dispatcher)

    # get-roms command
    get_roms_parser = subparsers.add_parser("get-roms", help="Download missing or updated ROMs and media.")
    _ = get_roms_parser.add_argument("source", choices=["tic80com", "itch", "ipfs"], help="The source to download from.")
    group_download = get_roms_parser.add_mutually_exclusive_group()
    _ = group_download.add_argument("--download-all", action="store_true", help="Download all games with missing sha1 (ignores filters).")
    _ = group_download.add_argument("--download-almost-all", action="store_true", help="Download Games (T/blank in collection) and WIP (T in collection).")
    get_roms_parser.set_defaults(func=get_roms_dispatcher)

    # sync-filenames command
    sync_parser = subparsers.add_parser("sync-filenames", help="Rename ROMs and media files based on current CSV data.")
    sync_parser.set_defaults(func=sync_filenames_command)

    # get-coverarts command
    covers_parser = subparsers.add_parser("get-coverarts", help="Download missing cover arts.")
    covers_parser.set_defaults(func=get_coverarts_command)

    # update-gamelistxml command
    xml_parser = subparsers.add_parser("update-gamelistxml", help="Generate or update the gamelist.xml file.")
    _ = xml_parser.add_argument("--image-path", default="./images", help="Set the <image> path prefix in gamelist.xml. Default: ./images.")
    xml_parser.set_defaults(func=update_gamelistxml_command)

    # recalculate-hashes command
    recalc_parser = subparsers.add_parser("recalculate-hashes", help="Recalculate MD5, SHA1, and CRC for all local ROMs and update the CSV.")
    recalc_parser.set_defaults(func=recalculate_hashes_command)

    # export-collection command
    export_parser = subparsers.add_parser("export-collection", help="Export a subset of the collection to a new folder.")
    _ = export_parser.add_argument("--dest-path", required=True, help="Destination path for the exported collection (e.g., ./exported-collection).")
    group_export = export_parser.add_mutually_exclusive_group()
    _ = group_export.add_argument("--export-all", action="store_true", help="Export all downloaded games (ignores filters).")
    _ = group_export.add_argument("--export-almost-all", action="store_true", help="Export Games (T/blank in collection) and WIP (T in collection).")
    _ = group_export.add_argument("--export-curated-distribution-safe", action="store_true", help="Export games excluding unsafe distribution license. Ideal for sharing.")
    export_parser.set_defaults(func=export_collection_command)

    # import-xml-data command
    import_xml_parser = subparsers.add_parser("import-xml-data", help="Import additional metadata from an external XML file.")
    _ = import_xml_parser.add_argument("xml_file", help="Path to the XML file to import data from.")
    import_xml_parser.set_defaults(func=import_xml_data_command)

    # ai-assistant command
    ai_parser = subparsers.add_parser("ai-assistant", help="Use an AI to generate game descriptions and genres.")
    _ = ai_parser.add_argument("--force", action="store_true", help="Re-process entries even if output files already exist.")
    ai_parser.set_defaults(func=ai_assistant_command)

    # import-json command
    import_json_parser = subparsers.add_parser("import-json", help="Import AI-generated data from JSON files into the CSV.")
    import_json_parser.set_defaults(func=import_json_command)

    # init command
    init_parser = subparsers.add_parser("init", help="Initialize collection from InitPack.")
    init_parser.set_defaults(func=init_command)

    if '_carapace' in sys.argv:
        print(export_carapace_spec(parser))
        sys.exit(0)

    # Hidden internal option for carapace completion
    # Use parse_known_args() to avoid error on unrecognized flags
    args, unknown = parser.parse_known_args(namespace=TColManagerArgs())

    # If not in completion mode, a command is required.
    # if args.command is None:
    #     parser.error("the following arguments are required: command")

    # Also, if not in completion mode, unknown arguments are an error.
    if unknown:
        parser.error(f"unrecognized arguments: {' '.join(unknown)}")

    if hasattr(args, 'func') and args.func is not None:
        args.func(args)
    else:
        # No command provided, show usage and hint
        parser.print_usage()
        print(parser.epilog)
        print("\nUse --help for extended usage information.\n")
        sys.exit(0)

if __name__ == "__main__":
    main()