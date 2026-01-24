from dataclasses import dataclass
import datetime

from tcolmanager.config import FORBIDDEN_CHARS
from tcolmanager.data_utils import get_primary_game_id, get_rom_category


@dataclass
class FileInfo:
    """File Info"""
    pre_filename: str
    gamename: str
    rom_filename: str
    image_filename: str

def sanitize_game_title_name(name: str) -> str:
    """
    Sanitizes the game title from the API.
    - Remove '.tic'
    - Replace '_' with ' '
    - Decode HTML entities (&amp;, &#34;, &#39;)
    - Capitalize the first upcasable character found.
    """
    if name.lower().endswith(".tic"):
        name = name[:-4]
    name = name.replace("_", " ")
    name = name.replace("&amp;", "&").replace("&#34;", "'").replace("&#39;", "'").replace('"', "'")

    # Collapse multiple spaces into one
    name = ' '.join(name.split())

    name_list = list(name)
    for i, char in enumerate(name_list):
        if char.isalpha():
            name_list[i] = char.upper()
            break

    return "".join(name_list)

def create_safe_filename(name: str) -> str:
    """Removes forbidden characters for filenames."""
    name = "".join(c for c in name if c not in FORBIDDEN_CHARS)
    # Collapse multiple spaces into one
    return ' '.join(name.split())

def generate_filename_and_gamename(
    row: dict[str, str],
    use_custom_filenames: bool,
    use_custom_gamenames: bool,
    filename_category_parenthesis: bool,
    filename_case: str,
    rom_folder_organization: str) -> FileInfo:
    """
    Generates the pre-filename, final filename, and GameName for a CSV row
    based on configuration.

    Returns: (pre_filename, GameName, filename)
    """
    game_id = get_primary_game_id(row)
    orig_name = row.get("name_original_reference", "") or row.get("itch_titlename", "")
    overwrite_name = row.get("name_overwrite", "").strip()
    game_category = get_rom_category(row)
    update_date = ""

    upd_ts_str = row.get("overwrite_upd_timestamp")
    upd_ts = None
    if upd_ts_str:
        try:
            upd_ts = float(upd_ts_str)
        except (ValueError, TypeError):
            pass
        if upd_ts:
            update_date = datetime.datetime.fromtimestamp(upd_ts).strftime('%Y-%m-%d')

    if update_date == "" and row.get("source_with_bestversion", "tic80com") == "tic80com":
        update_date = row.get("tic_upd_date") or row.get("tic_pub_date", "")

    if update_date == "":
        lastmod_ts_str = row.get("itch_lastmodified_timestamp")
        upd_ts_str = row.get("itch_upd_timestamp")

        lastmod_ts = None
        if lastmod_ts_str:
            try:
                lastmod_ts = float(lastmod_ts_str)
            except (ValueError, TypeError):
                pass

        upd_ts = None
        if upd_ts_str:
            try:
                upd_ts = float(upd_ts_str)
            except (ValueError, TypeError):
                pass

        selected_ts = None
        if upd_ts and lastmod_ts:
            # use oldest date between update and lastmodified
            selected_ts = min(upd_ts, lastmod_ts)
        elif upd_ts:
            selected_ts = upd_ts
        elif lastmod_ts:
            selected_ts = lastmod_ts
        else:
            pub_ts_str = row.get("itch_pub_timestamp")
            if pub_ts_str:
                try:
                    selected_ts = float(pub_ts_str)
                except (ValueError, TypeError):
                    pass
        
        if selected_ts:
            update_date = datetime.datetime.fromtimestamp(selected_ts).strftime('%Y-%m-%d')
        else:
            update_date = row.get("tic_upd_date") or row.get("tic_pub_date", "")


    # 1. Determine the Base Name (for filename and GameName)
    base_filename_name = overwrite_name if use_custom_filenames and overwrite_name else orig_name
    game_name = overwrite_name if use_custom_gamenames and overwrite_name else orig_name

    # 2. Apply tic_category Parenthesis for pre-filename
    category_suffix = ""
    if rom_folder_organization == "single" and filename_category_parenthesis and game_category != "Games":
        suffix_name = game_category
        if game_category == "Tools": # Special case for Tools -> Tool
             suffix_name = "Tool"
        elif game_category != "Demoscene" and game_category.endswith('s'): # For other plurals
            suffix_name = game_category[:-1]

        category_suffix = f" ({suffix_name})"

    # 3. Create pre-filename (the name part before - {id} ({date}))
    pre_filename = f"{base_filename_name}{category_suffix}"

    # 4. Apply Case
    if filename_case == "uppercase":
        pre_filename = pre_filename.upper()
        base_filename_name = base_filename_name.upper()
    elif filename_case == "lowercase":
        pre_filename = pre_filename.lower()
        base_filename_name = base_filename_name.lower()

    # 5. Sanitize for forbidden characters
    base_filename_name = create_safe_filename(base_filename_name)
    pre_filename = create_safe_filename(pre_filename)
    game_name = create_safe_filename(game_name)

    # 6. Final Filename
    final_filename = f"{pre_filename} - {game_id} ({update_date}).tic"

    image_filename = f"{base_filename_name} - {game_id}.png"

    #return pre_filename, game_name, final_filename
    return FileInfo(
        pre_filename=pre_filename,
        gamename=game_name,
        rom_filename=final_filename,
        image_filename=image_filename
    )