def escape_xml(text: str) -> str:
    """Escapes only < and > characters for XML."""
    return (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def get_description(row: dict[str, str]) -> str:
    """Gets the best available description from a CSV row."""
    description = (
        row.get("overwrite_description", "") or
        row.get("sscrp_description", "") or
        row.get("tic_description", "") or
        row.get("itch_description", "") or
        ""
    ).strip()
    return escape_xml(description)

def get_author(row: dict[str, str]) -> str:
    """Gets the best available author/developer from a CSV row."""
    return escape_xml(
        row.get("overwrite_author", "") or
        row.get("tic_author_name", "") or
        row.get("itch_author_name", "") or
        ""
    ).strip()

def generate_game_xml_entry(
    row: dict[str, str],
    filename: str,
    gamename: str,
    image_filename: str,
    image_path_prefix: str = "./screenshots"
) -> str | None:
    """Generates a <game> XML entry as a string."""
    
    # Use file_md5 if available, otherwise fall back to tic_md5
    md5 = row.get("file_md5") or row.get("tic_md5", "")
    if not md5:
        return None # Don't generate entry if no MD5 is available

    game_xml: list[str] = []
    game_xml.append(f'\t<game>')
    game_xml.append(f'\t\t<path>./{escape_xml(filename)}</path>')
    game_xml.append(f'\t\t<sortname>{escape_xml(row.get("sortname") or gamename)}</sortname>')
    game_xml.append(f'\t\t<name>{escape_xml(gamename)}</name>')

    description = get_description(row)
    if description:
        game_xml.append(f'\t\t<desc>{description}</desc>')

    image_path = f"{image_path_prefix}/{image_filename}"
    game_xml.append(f'\t\t<image>{escape_xml(image_path)}</image>')
    game_xml.append(f'\t\t<screenshot>{escape_xml(image_path)}</screenshot>')
    game_xml.append(f'\t\t<titleshot>./titlescreens/{escape_xml(image_filename)}</titleshot>')
    

    # Dates: prefer tic_pub_date, fallback to itch_pub_date
    release_date_str = row.get("tic_pub_date") or row.get("itch_pub_date")
    if release_date_str:
        release_date = release_date_str.replace("-", "")
        game_xml.append(f'\t\t<releasedate>{release_date}T000000</releasedate>')

    author = get_author(row)
    if author:
        game_xml.append(f'\t\t<developer>{author}</developer>')

    game_xml.append(f'\t\t<md5>{md5}</md5>')

    lang = row.get("lang")
    if lang:
        game_xml.append(f'\t\t<lang>{lang}</lang>')

    region = row.get("region")
    if region:
        game_xml.append(f'\t\t<region>{region}</region>')

    genre = row.get("overwrite_genre") or row.get("sccrp_genre") or row.get("itch_genre") or ""
    if genre:
        game_xml.append(f'\t\t<genre>{escape_xml(genre)}</genre>')

    num_players = row.get("num_players", "").strip()
    if num_players:
        game_xml.append(f'\t\t<players>{escape_xml(num_players)}</players>')

    esde_controller = row.get("esde_controller", "").strip()
    if esde_controller:
        game_xml.append(f'\t\t<controller>{escape_xml(esde_controller)}</controller>')

    game_xml.append(f'\t</game>')

    return "\n".join(game_xml)
