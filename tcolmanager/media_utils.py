import shutil
from pathlib import Path

from tcolmanager.config import MEDIA_PATH
from tcolmanager.data_utils import (
    TColManagerArgs,
    find_media_file,
    get_primary_game_id,
    get_secondary_game_id,
)


def sync_media_for_game(
    row: dict[str, str],
    new_filename_base: str,
    args: TColManagerArgs,
):
    """
    Finds and renames/copies all associated media files for a given game.
    This encapsulates the complex logic of finding media by old name,
    primary ID, or secondary ID.
    """
    media_types = {
        "screenshots": ".png",
        "titlescreens": ".png",
        "cart-covers": ".png",
        "itch-screenshots": ".png", # Assuming itch screenshots will be png after conversion
    }
    current_game_id = get_primary_game_id(row)

    if not current_game_id:
        return

    for media_type, ext in media_types.items():
        new_media_name = new_filename_base.replace(".png", ext)
        media_dir = MEDIA_PATH / media_type
        new_media_path = media_dir / new_media_name

        found_media_path: Path | None = None
        operation: str | None = None  # 'move' or 'copy'

        # Find media by old ROM filename, then primary ID, then secondary ID
        old_media_path = find_media_file(media_dir, current_game_id)
        if old_media_path and old_media_path.exists():
            found_media_path, operation = old_media_path, "move"
        elif media_by_primary_id := find_media_file(media_dir, current_game_id):
            found_media_path, operation = media_by_primary_id, "move"
        elif secondary_id := get_secondary_game_id(row):
            if media_by_secondary_id := find_media_file(media_dir, secondary_id):
                found_media_path, operation = media_by_secondary_id, "copy"

        if found_media_path and found_media_path.resolve() != new_media_path.resolve():
            action_word = "Renaming" if operation == "move" else "Copying"
            source_name = found_media_path.name

            print(f"    -> {action_word} {media_type} for {current_game_id}: {source_name} -> {new_media_name}")
            try:
                if operation == "move":
                    _ = shutil.move(found_media_path, new_media_path)
                elif operation == "copy":
                    _ = shutil.copy(found_media_path, new_media_path)
            except Exception as e:
                print(f"    ❌ Failed to sync media file: {e}")