import sys
import os
from datetime import datetime
from functools import wraps
from typing import Callable, IO, TypeVar, ParamSpec

from tcolmanager.config import LOGS_PATH

P = ParamSpec("P")
R = TypeVar("R")

ERROR_PATH = os.path.join(LOGS_PATH, "error")

def setup_logging():
    """Create log directories if they don't exist."""
    os.makedirs(LOGS_PATH, exist_ok=True)
    os.makedirs(ERROR_PATH, exist_ok=True)

class Tee(object):
    """A file-like object that writes to multiple files."""
    files: tuple[IO[str], ...]
    def __init__(self, *files: IO[str]):
        self.files = files

    def write(self, obj: str):
        for f in self.files:
            _ = f.write(obj)
            f.flush()

    def flush(self):
        for f in self.files:
            f.flush()

# Add a simple error-logging helper that the rest of the code can import as `log_error`.
# This function writes a timestamped message to a dedicated error log file
# and also prints the message to stderr so the user sees it immediately.
def log_error(message: str) -> None:
    """
    Log an error message.

    • Ensures the log directories exist (via ``setup_logging``).
    • Appends a timestamped line to ``ERROR_DIR/error.log``.
    • Mirrors the message to standard error for immediate visibility.
    """
    # Make sure the log directories are present.
    setup_logging()

    # Write to a persistent error log file.
    error_log_path = os.path.join(ERROR_PATH, "error.log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(error_log_path, "a", encoding="utf-8") as f:
            _ = f.write(f"[{timestamp}] {message}\n")
    except Exception as e:
        # If writing to the file fails, fall back to stderr only.
        print(f"[{timestamp}] Failed to write to error log: {e}", file=sys.stderr)

    # Always echo to stderr so the caller sees the problem right away.
    print(f"[{timestamp}] {message}", file=sys.stderr)

def log_command(func: Callable[P, R]) -> Callable[P, R]:
    """
    A decorator that wraps a command function to log its stdout and stderr.
    """
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        setup_logging()
        
        command_name = func.__name__.replace('_command', '')
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        log_filename = os.path.join(LOGS_PATH, f"{command_name} - {timestamp}.txt")
        error_filename = os.path.join(ERROR_PATH, f"error - {timestamp}.txt")

        original_stdout = sys.stdout
        original_stderr = sys.stderr

        try:
            with open(log_filename, 'w', encoding='utf-8') as log_file, \
                 open(error_filename, 'w', encoding='utf-8') as error_file:
                
                sys.stdout = Tee(original_stdout, log_file)
                sys.stderr = Tee(original_stderr, error_file)

                try:
                    print(f"--- Log started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
                    result = func(*args, **kwargs)
                    print(f"--- Log finished at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
                    
                    return result
                except Exception as e:
                    import traceback
                    # Also log to the main log file
                    print(f"\n--- ERROR OCCURRED at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---", file=sys.stderr)
                    print(f"An error occurred in command '{command_name}': {e}", file=sys.stderr)
                    traceback.print_exc(file=sys.stderr)
                    # Re-raise the exception after logging
                    raise
        finally:
            # Restore original stdout and stderr
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            
            # Check if error file is empty. If so, delete it.
            if os.path.exists(error_filename) and os.path.getsize(error_filename) == 0:
                os.remove(error_filename)

    return wrapper