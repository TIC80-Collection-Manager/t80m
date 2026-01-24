from tcolmanager.data_utils import TColManagerArgs


def update_csv_dispatcher(args: TColManagerArgs):
    """Dispatches the updatecsv command to the correct function based on source."""
    if args.source == "tic80com":
        from .update_tic80_csv import update_tic_csv_command
        update_tic_csv_command(args)
    elif args.source == "itch":
        from .update_itch_csv import update_itch_csv_command
        update_itch_csv_command(args)
    else:
        print(f"Unknown source for updatecsv: {args.source}")

def get_roms_dispatcher(args: TColManagerArgs):
    """Dispatches the get-roms command to the correct function based on source."""
    if args.source == "tic80com":
        from .get_tic80_roms import get_tic_roms_command
        get_tic_roms_command(args)
    elif args.source == "itch":
        from .get_itch_roms import get_itch_roms_command
        get_itch_roms_command(args)
    elif args.source == "ipfs":
        from .get_ipfs_roms import get_ipfs_roms_command
        get_ipfs_roms_command(args)
    else:
        print(f"Unknown source for get-roms: {args.source}")