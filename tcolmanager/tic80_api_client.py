import io
import re
import zlib
import requests
import shutil
import subprocess
from pathlib import Path
from bs4 import BeautifulSoup, Tag
from PIL import Image
import os
from email.utils import parsedate_to_datetime


from tcolmanager.config import HEADERS
from tcolmanager.data_utils import ts_to_parts # Importing ts_to_parts

def api_response_to_list(text: str) -> list[dict[str, str]]:
    """Parses the non-standard TIC-80 API response."""
    match = re.search(r"files\s*=\s*\{([\s\S]*)\}", text)
    if not match:
        print("--- Regex match for 'files =' FAILED. ---")
        return []

    # The match is greedy, so we get the whole block, but it includes the final closing brace.
    # We remove it by finding the last brace and slicing the string.
    files_content = match.group(1)

    # Regex to capture name, hash, id, and filename
    entries: list[str] = re.findall(r"\{\s*name\s*=\s*\"([\s\S]*?)\",\s*hash\s*=\s*\"(.*?)\",\s*id\s*=\s*(\d+),\s*filename\s*=\s*\"(.*?)\"\s*\}", files_content)

    parsed_list: list[dict[str, str]] = []
    for name, md5hash, id_str, filename in entries:
        parsed_list.append({
            "name": name,
            "tic_md5": md5hash,
            "id": id_str,
            "filename": filename
        })
    return parsed_list

def parse_playpage(html: str) -> dict[str, str]:
    """Extract metadata (Author, Uploader, Timestamps, Descriptions) from a TIC-80 play page."""
    soup: BeautifulSoup = BeautifulSoup(html, "html.parser")
    metadata = {}

    # Author/Uploader info
    metadata["tic_author_name"] = ""
    metadata["tic_uploader_name"] = ""
    metadata["tic_uploader_id"] = ""

    author_node = soup.find(string=lambda t: isinstance(t, str) and "made by" in t)
    if author_node:
        metadata["tic_author_name"] = str(author_node).replace("made by", "").strip()

    a_devs = soup.find_all("a", href=True)
    for a in a_devs:
        if isinstance(a, Tag):
            href = a.get("href")
            if href and isinstance(href, str) and "dev?id=" in href:
                metadata["tic_uploader_name"] = a.get_text(strip=True)
                m = re.search(r"dev\?id=(\d+)", href)
                if m:
                    metadata["tic_uploader_id"] = m.group(1)
                break

    # Creation + Updated timestamps
    creation_ts, updated_ts = "", ""
    for div in soup.find_all("div", class_="text-muted"):
        if not isinstance(div, Tag):
            continue
        txt = div.get_text(" ", strip=True).lower()
        span_tag = div.find("span", {"class": "date"})
        if not isinstance(span_tag, Tag):
            continue
        val = span_tag.get("value", "")
        if isinstance(val, str):
            if "added:" in txt:
                try:
                    creation_ts = str(int(val) // 1000)
                except (ValueError, TypeError):
                    pass
            if "updated:" in txt:
                try:
                    updated_ts = str(int(val) // 1000)
                except (ValueError, TypeError):
                    pass

    if not creation_ts:
        span = soup.find("span", class_="date")
        if isinstance(span, Tag) and (val := span.get("value")) and isinstance(val, str):
            try:
                creation_ts = str(int(val) // 1000)
            except (ValueError, TypeError):
                pass

    if not updated_ts:
        updated_ts = creation_ts

    metadata["tic_pub_timestamp"] = creation_ts
    metadata["tic_upd_timestamp"] = updated_ts

    c_date, _ = ts_to_parts(creation_ts)
    u_date, _ = ts_to_parts(updated_ts)

    metadata["tic_pub_date"] = c_date
    metadata["tic_upd_date"] = u_date

    # Descriptions
    metadata["tic_description"] = ""
    metadata["tic_description_extra"] = ""

    # Try to get description from meta tag first, as it's more reliable
    desc_meta = soup.find("meta", attrs={"name": "description"})
    if isinstance(desc_meta, Tag) and isinstance(desc_meta.get("content"), str):
        metadata["tic_description"] = str(desc_meta.get("content", ""))

    # The main content is in a specific 'container' div.
    # We can find it by looking for the one containing the game's title in an <h1> tag.
    h1 = soup.find("h1") # Returns Tag | NavigableString | None
    container: Tag | None = None
    if isinstance(h1, Tag):
        # find_parent can return a Tag or None.
        parent = h1.find_parent("div", class_="container")
        if isinstance(parent, Tag):
            container = parent

    if container:
        # Fallback for tic_description if meta tag was not found
        if not metadata["tic_description"]:
            first_hr = container.find("hr")
            if isinstance(first_hr, Tag):
                description_div = first_hr.find_next_sibling("div")
                if isinstance(description_div, Tag):
                    metadata["tic_description"] = description_div.get_text(strip=True)

        # For tic_description_extra
        all_hr = container.find_all("hr")
        if len(all_hr) > 1:
            # The extra description <p> tag is after the second <hr>
            second_hr = all_hr[1] # This is a Tag
            if isinstance(second_hr, Tag):
                extra_p = second_hr.find_next_sibling("p")
                if isinstance(extra_p, Tag):
                    # Replace <br> tags with newline characters for proper formatting
                    for br in extra_p.find_all("br"):
                        _ = br.replace_with("\\n")
                    metadata["tic_description_extra"] = extra_p.get_text()

    return metadata


def download_file(url: str, filepath: Path, session: requests.Session) -> float | None:
    """Downloads a file to the specified path."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = session.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()

        last_modified_str = r.headers.get('Last-Modified')
        last_modified_ts: float | None = None

        if last_modified_str:
            try:
                last_modified_dt = parsedate_to_datetime(last_modified_str)
                last_modified_ts = last_modified_dt.timestamp()
            except Exception as e:
                last_modified_ts = 0
                print(f"    Could not get Last-Modified: {e}")
        else:
            last_modified_ts = 0

        content_type = r.headers.get("Content-Type", "").lower()

        if "html" in content_type:
            # Handle HTML page with embedded cartridge data
            print("    -> HTML response detected, attempting to extract cartridge...")
            html = r.text
            match = re.search(r"var\s+cartridge\s*=\s*\[([0-9,\s]+)\]", html)
            if not match:
                print("    [!] Cartridge data not found in the page.")
                return None

            array_data: str = match.group(1)
            bytes_list = [int(x) for x in re.findall(r"\d+", array_data)]
            print(f"    [+] Extracted {len(bytes_list)} bytes (compressed)")

            compressed_bytes = bytes(bytes_list)
            try:
                decompressed_content = zlib.decompress(compressed_bytes)
                print(f"    [+] Decompressed to {len(decompressed_content)} bytes")
            except zlib.error as e:
                print(f"    [!] Zlib decompression failed: {e}")
                return None

            with open(filepath, "wb") as f:
                _ = f.write(decompressed_content)
            return last_modified_ts

        else:
            # Handle direct file download
            if len(r.content) < 100:
                print(f"    ⚠️ Downloaded file is suspiciously small ({len(r.content)} bytes). Skipping write.")
                return None

            with open(filepath, "wb") as f:
                _ = f.write(r.content)
            return last_modified_ts

    except Exception as e:
        print(f"    ❌ Download failed from {url}: {e}")
        return None

def download_and_convert_gif_to_png(url: str, filepath: Path, session: requests.Session) -> bool:
    """
    Downloads a GIF/PNG, converts it to PNG, and saves it.
    Handles scaled pixel art (240x136 multiples) and bordered images (256x144 multiples).
    For animated GIFs, only the first frame is saved.
    Requires the 'Pillow' library.
    """
    TARGET_SIZE = (240, 136)
    BORDERED_SIZE = (256, 144)

    filepath.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = session.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        if len(r.content) < 100:
            print(f"    ⚠️ Downloaded file is suspiciously small ({len(r.content)} bytes). Skipping write.")
            return False

        # Open image from memory
        img = Image.open(io.BytesIO(r.content))

        # For animated GIFs, use only the first frame
        if getattr(img, "is_animated", False):
            img.seek(0)

        # Convert palette mode to RGBA for proper handling
        if img.mode == "P":
            img = img.convert("RGBA")

        width, height = img.size

        # Check if it's a pixel-perfect multiple of TARGET_SIZE (240x136)
        if width % TARGET_SIZE[0] == 0 and height % TARGET_SIZE[1] == 0:
            scale_w = width // TARGET_SIZE[0]
            scale_h = height // TARGET_SIZE[1]
            if scale_w == scale_h and scale_w >= 1:
                if scale_w > 1:
                    img = img.resize(TARGET_SIZE, Image.Resampling.NEAREST)

        # Check if it's a pixel-perfect multiple of BORDERED_SIZE (256x144)
        if width % BORDERED_SIZE[0] == 0 and height % BORDERED_SIZE[1] == 0:
            scale_w = width // BORDERED_SIZE[0]
            scale_h = height // BORDERED_SIZE[1]
            if scale_w == scale_h and scale_w >= 1:
                if scale_w > 1:
                    img = img.resize(BORDERED_SIZE, Image.Resampling.NEAREST)
                # Crop border: 8px left/right, 4px top/bottom
                img = img.crop((8, 4, BORDERED_SIZE[0] - 8, BORDERED_SIZE[1] - 4))

        # Don't do any change in case it doesn't fit criteria.

        # Finally, we save the image
        img.save(filepath, "PNG")

        # try to optimize / compress image by using oxipng #quite slow
        # if shutil.which("oxipng"):
        #     try:
        #         _ = subprocess.run(["oxipng", "-o6", "-Z", "--strip", "safe", str(filepath)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        #     except subprocess.CalledProcessError:
        #         print(f"    ⚠️ oxipng optimization failed for {filepath.name}")

        return True

    except Exception as e:
        print(f"    ❌ Download/Conversion failed from {url}: {e}")
        return False
