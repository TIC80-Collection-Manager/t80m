import csv
import threading
import sys
from types import FrameType
from pathlib import Path

from tcolmanager.config import DEFAULT_FIELDNAMES
from tcolmanager.data_utils import get_primary_game_id, normalize_id

# --- Global Database and Signal Handler for graceful exit ---
_global_db: dict[str, dict[str, str]] = {}
_global_csv_path: Path | None = None
_global_fieldnames: list[str] | None = None  # Track original field order
# Use a re‑entrant lock so the SIGINT handler can acquire the lock even
# if it is already held by the same thread (e.g., during load_csv_database()).
_global_db_lock = threading.RLock() # Protects _global_db access during file operations

def signal_handler(signum: int, _: FrameType | None):
    """Signal handler to save CSV and exit."""
    print(f"\n[!] Signal {signum} received. Saving progress before exiting...")
    if _global_csv_path and _global_db:
        with _global_db_lock:
            # Save the current state of the global database
            save_csv_database(_global_csv_path, _global_db)
    else:
        print("[i] No database loaded or path specified yet, nothing to save.")
    sys.exit(0)

def load_csv_database(filepath: Path) -> dict[str, dict[str, str]]:
    """Loads the CSV into a dictionary keyed by a primary game ID and populates _global_db."""
    global _global_db, _global_csv_path, _global_fieldnames
    _global_csv_path = filepath # Set the global path

    with _global_db_lock:
        _global_db = {} # Clear previous content
        _global_fieldnames = None  # Reset fieldnames
        if not filepath.exists():
            print(f"Database file {filepath} not found. Starting with empty database.")
            return _global_db

        print(f"Loading database from {filepath}...")
        with open(filepath, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            _global_fieldnames = list(reader.fieldnames) if reader.fieldnames else None
            for i, row in enumerate(reader):
                row['id'] = normalize_id(row['id'])
                row['itch_id'] = normalize_id(row['itch_id'])
                row['tic_id'] = normalize_id(row['tic_id'])

                game_id = get_primary_game_id(row)
                if game_id:
                    if game_id in _global_db:
                        print(f"    ⚠️ Duplicate game ID '{game_id}' found. The last entry in the CSV will be used.")
                    _global_db[game_id] = row
                else:
                    # This case should now be very rare
                    print(f"    ⚠️ Row {i+2} is missing a 'tic_id', 'itch_id', or 'id' and will be skipped.")

        print(f"Loaded {len(_global_db)} entries. ✅")
        return _global_db

def save_csv_database(filepath: Path, database: dict[str, dict[str, str]]):
    """Saves the dictionary back to the CSV, preserving original field order or using DEFAULT_FIELDNAMES for new files."""
    print(f"Saving database to {filepath}...")
    filepath.parent.mkdir(parents=True, exist_ok=True)

    with _global_db_lock:
        # Collect all unique fieldnames from the current database entries
        all_present_fieldnames = set[str]()
        for row in database.values():
            all_present_fieldnames.update(row.keys())

        final_fieldnames: list[str] = []

        if _global_fieldnames:
            # Preserve original field order from loaded file
            for field in _global_fieldnames:
                if field in all_present_fieldnames:
                    final_fieldnames.append(field)
                    all_present_fieldnames.discard(field)
        else:
            # New file: use DEFAULT_FIELDNAMES order
            for field in DEFAULT_FIELDNAMES:
                if field in all_present_fieldnames:
                    final_fieldnames.append(field)
                    all_present_fieldnames.discard(field)

        # Add any remaining (new) fields, sorted alphabetically
        final_fieldnames.extend(sorted(list(all_present_fieldnames)))

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=final_fieldnames)
            writer.writeheader()

            # Sort by game ID as a string to handle numeric and non-numeric IDs safely
            sorted_rows = sorted(
                database.values(),
                key=lambda r: (
                    r.get("sortname", "")
                    or r.get("name_overwrite", "")
                    or r.get("name_original_reference", "")
                    or r.get("itch_titlename", "")
                    or ""
                )
                .lower()
                .strip()
                + " "
                + r.get("id", "").strip().rjust(10, "0"), # id with padding to sort games with identical name
            )
            writer.writerows(sorted_rows)
    print(f"Saved {len(database)} entries. ✅")
