import re
import time
from typing import Any
import zlib
from collections.abc import Generator
import typing
from dataclasses import dataclass, field
import subprocess
from datetime import datetime
from html import unescape
from urllib.parse import urlparse, urljoin
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag
import xml.etree.ElementTree as ET

from tcolmanager import config
from tcolmanager.filename_utils import sanitize_game_title_name
from tcolmanager.utils.logger import log_error
from tcolmanager.data_utils import parse_raw_headers


@dataclass
class CartData:
    """Represents the data of a downloaded TIC-80 cart."""
    filepath: Path
    content: bytes
    last_modified: str | None = None
    screenshot_urls: list[str] = field(default_factory=list)

def extract_essential_headers(headers_str: str) -> tuple[str | None, str | None]:
    """Extract User-Agent and cf_clearance cookie from raw headers or curl command."""
    # Case-insensitive search for User-Agent
    ua_match = re.search(r'user-agent:\s*([^\n\r\'"]+)', headers_str, re.IGNORECASE)
    user_agent: str | None = ua_match.group(1).strip() if ua_match else None
    
    # Search for cf_clearance cookie value
    cf_match = re.search(r'cf_clearance=([^;\s\'"]+)', headers_str)
    cf_clearance: str | None = cf_match.group(1).strip() if cf_match else None
    
    return user_agent, cf_clearance

def http_get(session: requests.Session, url: str, stream: bool = False, allow_redirects: bool = True) -> requests.Response | None:
    """Performs an HTTP GET request with a small delay."""
    time.sleep(0.3) # Be respectful to the server
    try:
        r = session.get(url, timeout=30, stream=stream, allow_redirects=allow_redirects, verify=True)
        r.raise_for_status()
        return r
    except requests.exceptions.RequestException as e:
        if hasattr(e, 'response') and e.response is not None:
            if e.response.headers.get('cf-mitigated') == 'challenge':
                print(f"[!] Cloudflare challenge for {url}. Please solve the captcha.")

                if not config.USER_EDITOR:
                    print("[!] USER_EDITOR environment variable not set. Cannot ask for new headers.")
                else:
                    header_file = config.ITCH_REQUEST_HEADER_PATH
                    instructions = f"""### Open the URL in the browser:
### {url}
###
### Solve the captcha, copy the the browser header and paste it bellow
###
### To get the header, go to Inspect Element -> Network tab ->
### Solve the captcha, or reload if already solved ->
### Right button in the plataform-web.xml -> Copy -> Copy as cURL -> Paste it
###
### If it fails, you can try to delete the cf_clearance cookie and do the captcha again.
"""
                    # Ensure parent directory exists
                    header_file.parent.mkdir(parents=True, exist_ok=True)
                    _ = header_file.write_text(instructions, encoding="utf-8")
                        
                    try:
                        _ = subprocess.run([config.USER_EDITOR, str(header_file)], check=True)
                        headers_str = header_file.read_text(encoding="utf-8")

                        user_agent, cf_clearance = extract_essential_headers(headers_str)

                        if not user_agent:
                            print("[!] Could not find the User-Agent in pasted headers.")
                            return None

                        if not cf_clearance:
                            print("[!] Could not find cf_clearance cookie in pasted headers.")
                            return None
                        
                        clean_headers = f"User-Agent: {user_agent}\n"
                        clean_headers += f"Cookie: cf_clearance={cf_clearance}\n"
                        
                        _ = header_file.write_text(instructions + "\n" + clean_headers, encoding="utf-8")

                        session.headers.update(parse_raw_headers(clean_headers))
                        print("[*] Headers updated. Retrying request...")
                        return http_get(session, url, stream, allow_redirects) # Retry
                    except Exception as sub_e:
                        print(f"[!] Failed to get new headers: {sub_e}")
        
        log_error(f"HTTP GET Error for {url}: {e}")
        print(f"[!] HTTP Error for {url}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            log_error("--- Full HTTP Headers ---")
            for key, value in e.response.headers.items():
                log_error(f"{key}: {value}")
            log_error("-------------------------")
        return None

def parse_rfc2822_to_dt(s: str) -> datetime | None:
    """Parses RFC 2822 formatted date string to a datetime object."""
    try:
        # Example: Tue, 19 Nov 2019 15:16:03 GMT
        return datetime.strptime(s, "%a, %d %b %Y %H:%M:%S %Z")
    except ValueError:
        try: # Fallback without timezone
            return datetime.strptime(s, "%a, %d %b %Y %H:%M:%S")
        except ValueError:
            return None

def parse_rss_xml(xml_text: str) -> dict[str, dict[str, str]]:
    """Return a dict mapping page URL → {'pubDate': ..., 'updateDate': ...}."""
    mapping: dict[str, dict[str, str]]= {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return mapping

    channel = root.find('channel')
    if channel is None:
        return mapping

    for item in channel.findall('item'):
        link_el = item.find('link')
        link = link_el.text.strip() if link_el is not None and link_el.text else None
        if not link:
            continue

        data = {}
        for tag in ('pubDate', 'updateDate', 'createDate'):
            el = item.find(tag)
            if el is not None and el.text:
                data[tag] = el.text.strip()
        mapping[link] = data
    return mapping

def scrape_itch_games() -> Generator[dict[str, str], None, None]:
    """
    Generator that scrapes itch.io for TIC‑80 games and yields a full
    metadata dict for each game, now also including pub/update dates.
    """
    session = requests.Session()

    if config.ITCH_REQUEST_HEADER_PATH.exists():
        headers_str = config.ITCH_REQUEST_HEADER_PATH.read_text(encoding="utf-8")
        session.headers.update(parse_raw_headers(headers_str))

    base_paths = [
        'made-with-tic-80/platform-web',
        'platform-web/tag-tic-80',
        'platform-web/tag-tic',
    ]

    # 1. Pre-fetch all XML data to build a complete date mapping.
    print("[*] Pre-fetching all XML feeds for date information...")
    full_xml_map: dict[str, dict[str, str]] = {}
    for base_path in base_paths:
        base_url = f"https://itch.io/games/{base_path}"
        page = 1
        while True:
            xml_url = f"{base_url}.xml?page={page}"
            print(f"[*]   Fetching {xml_url}")
            
            r_xml = http_get(session, xml_url)
            if not r_xml:
                print(f"[!] Failed to fetch XML for {base_path} page {page}. Skipping.")
                break

            xml_data_on_page = parse_rss_xml(r_xml.text)
            if not xml_data_on_page:
                print(f"[i No more XML items on page {page} for {base_path}. Done with this feed.")
                break
            
            full_xml_map.update(xml_data_on_page)
            page += 1
    
    print(f"[*] XML pre-fetch complete. Found date info for {len(full_xml_map)} unique games.")

    # 2. Iterate through JSON pages and use the pre-fetched XML data.
    for base_path in base_paths:
        base_url = f"https://itch.io/games/{base_path}"
        page = 1
        while True:
            json_url = f"{base_url}?page={page}&format=json"
            print(f"[*] Fetching Itch.io page {page} (JSON) -> {json_url}")

            r_json = http_get(session, json_url)
            if not r_json:  
                break

            data = typing.cast(dict[str, typing.Any], r_json.json())
            content = data.get('content', '')
            if not isinstance(content, str):
                content = ''
            if not content.strip():
                print("[i] No more content found on Itch.io. Stopping scrape.")
                break
            
            soup = BeautifulSoup(content, 'html.parser')
            game_cells = soup.find_all('div', class_='game_cell')

            if not game_cells and page > 1:
                print("[i] No game cells found on this page – assuming end of results.")
                break
                
            for cell in typing.cast(list[Tag], game_cells):
                try:
                    itch_id = cell.get('data-game_id')
                    if not itch_id or int(str(itch_id)) < 10000: #skip ids lower than 10k, those are false positive
                        continue

                    title_a = cell.select_one('.game_title a')
                    author_a = cell.select_one('.game_author a')
                    genre_el = cell.select_one('.game_genre')
                    desc_el = cell.select_one('.game_text')

                    author_href = author_a.get('href', '') if author_a else ''
                    author_slug = ''
                    if author_href:
                        host = urlparse(str(author_href)).hostname or ''
                        if host.endswith('.itch.io'):
                            author_slug = host.replace('.itch.io', '')
                    
                    author_label = author_a.get('data-label') if author_a and author_a.has_attr('data-label') else ''
                    author_id = ''
                    if author_label and isinstance(author_label, str):
                        m = re.search(r'user:(\d+)', author_label)
                        if m:
                            author_id = m.group(1)

                    # ------------------------------------------------------------------
                    # Pull pub/update dates from the XML mapping (if we have a page URL)
                    itch_page = title_a.get('href') if title_a else ''
                    xml_info = full_xml_map.get(str(itch_page), {})
                    pub_dt = parse_rfc2822_to_dt(xml_info.get('pubDate', ''))
                    upd_dt = parse_rfc2822_to_dt(xml_info.get('updateDate', ''))

                    row = {
                        'itch_id': str(itch_id),
                        'itch_titlename': sanitize_game_title_name(unescape(title_a.get_text(strip=True) if title_a else '')),
                        'itch_page': str(itch_page),
                        'itch_author_name': author_a.get_text(strip=True) if author_a else '',
                        'itch_author_slug': author_slug,
                        'itch_author_id': str(author_id),
                        'itch_description': unescape(desc_el.get_text(strip=True) if desc_el else ''),
                        'itch_genre': genre_el.get_text(strip=True) if genre_el else '',
                        'itch_pub_date': pub_dt.strftime("%Y-%m-%d") if pub_dt else '',
                        'itch_upd_date': upd_dt.strftime("%Y-%m-%d") if upd_dt else '',
                        'itch_pub_timestamp': str(int(pub_dt.timestamp())) if pub_dt else '',
                        'itch_upd_timestamp': str(int(upd_dt.timestamp())) if upd_dt else '',
                    }
                    yield row
                except Exception as e:
                    log_error(f"Error parsing an Itch.io game cell: {e}")
                    continue
            page += 1

def _find_cart_on_page(
    session: requests.Session,
    page_url: str,                # URL of the page we are inspecting
    target_dir: Path,
    base_filename: str,
) -> CartData | None:
    """
    Scan *page_url* for a TIC-80 cart using the three techniques that worked in the
    original scraper:

        1.  arguments:['cart.tic']        → direct cart URL
        2.  var cartridge = [...]         → embedded byte-array (z-lib)
        3.  fallback cart.tic             → plain file next to the page

    The function fetches the page **once**, re-uses the HTML for all three tests,
    and returns the same dictionary that the rest of the code expects:

        A `CartData` object.

    ``None`` is returned when no cart can be located.
    """
    # ------------------------------------------------------------------
    # Download the page (once) and keep the HTML text.
    resp = http_get(session, page_url)
    if not resp:
        print(f"    -> Failed to GET {page_url}")
        return None
    html = resp.text

    # ------------------------------------------------------------------
    # 1. Search for `arguments:['cart.tic']` – the classic‑HTML embed uses this.
    m_args = re.search(
        r"arguments\s*:\s*\[\s*['\"]([^'\"]+\.tic)['\"]", html, flags=re.IGNORECASE
    )
    if m_args:
        cart_filename = m_args.group(1)
        cart_url = urljoin(page_url, cart_filename)
        print(f"    -> Found cart via arguments pattern → {cart_url}")
        cart_resp = http_get(session, cart_url, stream=True)
        if cart_resp and "application" in cart_resp.headers.get("Content-Type", ""):
            return _save_cart_from_response(
                cart_resp, target_dir, f"{base_filename}.tic"
            )
        else:
            print("    ⚠️  Cart URL from arguments returned no binary content.")

    # ------------------------------------------------------------------
    # 2. Look for an embedded `var cartridge = [...]` byte‑array.
    m_cartridge = re.search(
        r"var\s+cartridge\s*=\s*\[([0-9,\s]+)\]", html, flags=re.IGNORECASE
    )
    if m_cartridge:
        print("    -> Found embedded cartridge array – extracting …")
        return _extract_and_save_embedded_cart(
            m_cartridge, resp, target_dir, base_filename
        )

    # ------------------------------------------------------------------
    # 3. Fallback: try to download a plain `cart.tic` sitting next to the page.
    cart_url = urljoin(page_url, "cart.tic")
    cart_resp = http_get(session, cart_url, stream=True)
    if cart_resp and "application" in cart_resp.headers.get("Content-Type", ""):
        return _save_cart_from_response(
            cart_resp, target_dir, f"{base_filename}.tic"
        )

    # ------------------------------------------------------------------
    # Nothing found.
    print("    ⚠️  No cart found on this page.")
    return None

def _parse_screenshot_urls(soup: BeautifulSoup) -> list[str]:
    """Parses the main page soup to find screenshot URLs."""
    urls: list[str] = []
    screenshot_list_div = soup.find("div", class_="screenshot_list")
    if not screenshot_list_div or not isinstance(screenshot_list_div, Tag):
        return []

    for link_tag in screenshot_list_div.find_all("a", attrs={"data-image_lightbox": "true"}):
        if not isinstance(link_tag, Tag):
            continue
        image_url = link_tag.get("href")
        if image_url and "/original/" in image_url:
            urls.append(str(image_url))
    return urls

def download_itch_rom(
    row: dict[str, str],
    session: requests.Session,
    itch_page_url: str,
    target_dir: Path,
    base_filename: str
) -> CartData | None:
    """
    Locate a cart for *itch_page_url*. It first searches for a classic-html
    iframe, which is a common way to embed TIC-80 games on Itch.io. If found,
    it scrapes the 'index.html' within that iframe for the cart. If not, it falls
    back to looking for an embedded cart on the main page.
    """
    print(f"    -> Scraping page {itch_page_url} for cart…")
    
    page_resp = http_get(session, itch_page_url)
    if not page_resp:
        return None
    main_page_html = page_resp.text
    soup = BeautifulSoup(main_page_html, "html.parser")

    screenshot_urls = _parse_screenshot_urls(soup)
    
    # --------------------------------------------------------------
    # Robustly find classic-HTML iframe URLs, mirroring the old scraper's logic.
    iframe_urls: set[str] = set()
    for tag in soup.find_all(True):
        # Skip non-Tag elements (NavigableString / PageElement) so type-checkers know .attrs exists.
        if not isinstance(tag, Tag):
            continue
        # Help the type checker by casting attrs to a plain dict with Any values.
        attrs = typing.cast(dict[str, typing.Any], tag.attrs)
        for attr_value in attrs.values():
            values_to_check = attr_value if isinstance(attr_value, list) else [attr_value]
            for v in values_to_check:
                if not isinstance(v, str):
                    continue
                
                full_text = unescape(v)
                
                # First, find URLs with a subdirectory, ending in /
                matches: list[str] = re.findall(r'(https?://html(?:-classic)?\.itch\.zone/html/[\d-]+/[^/"]*/)', full_text)
                for match in matches:
                    iframe_urls.add(match)

                # Fallback for URLs without the extra subdirectory
                if not matches:
                    matches = re.findall(r'(https?://html(?:-classic)?\.itch\.zone/html/[\d-]+/)', full_text)
                    for match in matches:
                        iframe_urls.add(match)

    # --------------------------------------------------------------
    # If any iframe URLs were found, try to find a cart in them by fetching index.html
    if iframe_urls:
        for iframe_base_url in sorted(list(iframe_urls)):
            print(f"    -> Detected classic‑HTML iframe: {iframe_base_url}")
            
            # CRITICAL FIX: The old scraper explicitly fetches index.html from the iframe's base URL.
            index_url = urljoin(iframe_base_url, 'index.html')
            
            # Pass the full index.html URL to be scraped.
            result = _find_cart_on_page(session, index_url, target_dir, base_filename)
            if result:
                result.screenshot_urls = screenshot_urls
                return result # Success, stop searching.
            
            print(f"    -> No cart found in content of {index_url}.")
    
    # --------------------------------------------------------------
    # Fallback: No iframes found, or no cart found in any of them.
    # Scan the original itch page for an embedded cartridge ('var cartridge').
    print("    -> No cart found in iframes, checking main Itch.io page for embedded cartridge…")
    m_cartridge = re.search(
        r"var\s+cartridge\s*=\s*\[([0-9,\s]+)\]", main_page_html, flags=re.IGNORECASE
    )
    if m_cartridge:
        print("    -> Found embedded cartridge array on main page – extracting …")
        result = _extract_and_save_embedded_cart(
            m_cartridge, page_resp, target_dir, base_filename
        )
        result.screenshot_urls = screenshot_urls
        return result

    # ------------------------------------------------------------------
    # Nothing found at all.
    print("    ⚠️  No cart found on this page.")
    return None

def _extract_and_save_embedded_cart(match: re.Match[str], response: requests.Response, target_dir: Path, base_filename: str) -> CartData:
    """
    Decode the `var cartridge = [...]` array and write the .tic file.
    """
    array_data = match.group(1)
    bytes_list = [int(x) for x in re.findall(r"\d+", array_data)]
    compressed_bytes = bytes(bytes_list)
    try:
        decompressed = zlib.decompress(compressed_bytes)
    except zlib.error:
        decompressed = compressed_bytes # Assume not compressed if error

    filepath = target_dir / f"{base_filename}.tic"
    with open(filepath, 'wb') as f:
        _ = f.write(decompressed)
        
    print(f"    -> Extracted embedded cart to {filepath.name}")
    return CartData(
        filepath=filepath,
        last_modified=response.headers.get('Last-Modified'),
        content=decompressed
    )

def _save_cart_from_response(response: requests.Response, target_dir: Path, filename: str) -> CartData:
    filepath = target_dir / filename
    content = response.content
    with open(filepath, 'wb') as f:
        _ = f.write(content)
        
    print(f"    -> Downloaded cart to {filepath.name}")
    return CartData(
        filepath=filepath,
        last_modified=response.headers.get('Last-Modified'),
        content=content
    )