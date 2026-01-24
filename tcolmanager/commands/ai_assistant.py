import json
import os
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
import threading
import typing

from tcolmanager.data_utils import TColManagerArgs

# The 'openai' and 'python-dotenv' libraries are required for this command.
# Install them with: pip install openai python-dotenv
try:
    from openai import OpenAI
    from dotenv import load_dotenv
except ImportError:
    print("Error: The 'openai' and 'python-dotenv' libraries are required for the 'ai-assistant' command.")
    print("Please install them by running: pip install openai python-dotenv")
    sys.exit(1)

from tcolmanager.config import CSV_DATABASE_PATH
from tcolmanager.csv_manager import load_csv_database
from tcolmanager.utils import log_command
from tcolmanager.data_utils import get_rom_category

# Define paths for source code and AI output
SOURCE_CODE_PATH = Path("./source-id-all-code")
AI_OUTPUT_PATH = Path("./output-ai-assistant")

print_lock = threading.Lock()

def process_game(game_id: str, row: dict[str, str], args: TColManagerArgs, openai: OpenAI) -> typing.Literal["skipped_exist", "skipped_no_source", "error", "processed"]:
    """
    Processes a single game: generates AI description and saves it.
    This function is designed to be run in a separate thread.
    """
    output_file = AI_OUTPUT_PATH / f"{game_id}.json"
    if not args.force and output_file.exists():
        with print_lock:
            print(f"    [i] Skipping, output file already exists: {output_file}")
        return "skipped_exist"

    source_file = SOURCE_CODE_PATH / f"{game_id}.lua"
    if not source_file.exists():
        with print_lock:
            print(f"    [!] Skipping, source code file not found: {source_file}")
        return "skipped_no_source"

    try:
        with open(source_file, 'r', encoding='utf-8') as f:
            source_code = f.read()
    except Exception as e:
        with print_lock:
            print(f"    [!] Error reading source code file {source_file}: {e}")
        return "error"

    prompt = f"""
you should reply in a json object format, and nothing else:

{{
"description": "game synopse",
"genre": "game genre",
"num_player": "1",
"_comment": "in case you want to say something, otherwise, prefer to keep this blank"
}}

num_player can be a single digit, or a range using a hifen, like: 1-2 (one to two players)

Even if the game or other info are in a different language, the description should be in English.

The description should be a max of 185 characters, thats a bit less than a tweet. Ideally around 100 to 185 characters.

Thats because people playing on handheld will only see the first 185 characters. It's okay to be a longer description, but less users will be able to read it all.

The description is a synopsis of the game, it can show the theme and help the user decide wheter to play it or not.
If it is a puzzle game, or something with a confuzing start, a brief comment on initial goals and how to play could be useful.

The user can already see information about the Author, release date, game name, so those info are not desired in the description.

When the game use btn() as input, all user can play on any plataform, so info about btn/keys are less desired.

But if the game use key() keyp() and/or mouse, then the information about the keys used in the game are valuable information to be in the description.

Button IDs: 0:UP, 1:DOWN, 2:LEFT, 3:RIGHT, 4:A, 5:B, 6:X, 7:Y.
Key IDs: 1:A, 2:B, 3:C, 4:D, 5:E, 6:F, 7:G, 8:H, 9:I, 10:J, 11:K, 12:L, 13:M, 14:N, 15:O, 16:P, 17:Q, 18:R, 19:S, 20:T, 21:U, 22:V, 23:W, 24:X, 25:Y, 26:Z, 27:0, 28:1, 29:2, 30:3, 31:4, 32:5, 33:6, 34:7, 35:8, 36:9, 37:MINUS, 38:EQUALS, 39:LEFTBRACKET, 40:RIGHTBRACKET, 41:BACKSLASH, 42:SEMICOLON, 43:APOSTROPHE, 44:GRAVE, 45:COMMA, 46:PERIOD, 47:SLASH, 48:SPACE, 49:TAB, 50:RETURN, 51:BACKSPACE, 52:DELETE, 53:INSERT, 54:PAGEUP, 55:PAGEDOWN, 56:HOME, 57:END, 58:UP, 59:DOWN, 60:LEFT, 61:RIGHT, 62:CAPSLOCK, 63:CTRL, 64:SHIFT, 65:ALT, 66:ESC, 67:F1, 68:F2, 69:F3, 70:F4, 71:F5, 72:F6, 73:F7, 74:F8, 75:F9, 76:F10, 77:F11, 78:F12, 79:NUM0, 80:NUM1, 81:NUM2, 82:NUM3, 83:NUM4, 84:NUM5, 85:NUM6, 86:NUM7, 87:NUM8, 88:NUM9, 89:NUMPLUS, 90:NUMMINUS, 91:NUMMULTIPLY, 92:NUMDIVIDE, 93:NUMENTER, 94:NUMPERIOD.

The available genre for classification are:

Action
Action / Adventure
Action / Breakout games
Action / Climbing
Action / Labyrinth
Adults
Adventure
Adventure / RealTime 3D
Adventure / Interactive Movie
Adventure / Graphic
Adventure / Point and Click
Adventure / Visual Novel
Adventure / Survival Horror
Adventure / Text
Beat'em Up
Casino
Casino / Cards
Casino / Race
Casino / Lottery
Casino / Slot machine
Casino / Roulette
Casual Game
Hunting and Fishing
Hunting
Fishing
Fighting
Fighting / 2.5D
Fighting / 2D
Fighting / 3D
Fighting / Versus
Fighting / Vs Co-op
Fighting / Vertical
Compilation
Racing, Driving
Motorcycle race FPV
Motorcycle race TPV
Racing FPV
Racing TPV
Racing, Driving / Plane
Racing, Driving / Boat
Racing, Driving / Racing
Racing, Driving / Hang Gliding
Racing, Driving / Motorcycle
Demo
Various
Various / Electro- Mechanical
Various / Print Club
Various / System
Various / Utilities
Pinball
Playing cards
Role Playing Game
Action RPG
Dungeon Crawler RPG
Japanese RPG
Tactical RPG
Party-Based RPG
Board game
Asiatic board game
Go
Hanafuda
Mahjong
Othello
Renju
Shougi
Educational
Music and Dancing
Rhythm
Platform
Platform / Fighter Scrolling
Platform / Run &amp; Jump
Platform / Run &amp; Jump Scrolling
Platform / Shooter Scrolling
Puzzle
Puzzle / Equalize
Puzzle / Glide
Puzzle / Throw
Puzzle / Fall
Quiz
Quiz / German
Quiz / English
Quiz / Korean
Quiz / Spanish
Quiz / French
Quiz / Italian
Quiz / Japanese
Quiz / Music English
Quiz / Music Japanese
Thinking
Shoot'em Up
Shoot'em Up / Diagonal
Shoot'em Up / Horizontal
Shoot'em Up / Vertical
Simulation
Build And Management
Simulation / SciFi
Simulation / Vehicle
Simulation / Life
Sports
Sports / Motorsport
Sports / Baseball
Sports / Basketball
Sports / Pool
Sports / Bowling
Sports / Boxing
Sports / Arm wrestling
Sports / Fighting
Sports / Running trails
Sports / Cycling
Sports / Dodgeball
Sports / Extreme
Sports / Fitness
Sports / Darts
Sports / Football (Soccer)
Sports / Football (American)
Sports / Golf
Sports / Handball
Sports / Hockey
Sports / Shuffleboard
Sports / Wrestling
Sports / Multisports
Sports / Swimming
Sports / Water
Sports / Skydiving
Sports / Table tennis
Sports / Rugby
Sports / Skateboard
Sports / Skiing
Sports / Sumo
Sports / Tennis
Sports / Volleyball
Sports with animals
Horse racing
Strategy
Shooter
Shooter / FPV
Shooter / TPV
Shooter / Plane
Shooter / Plane, FPV
Shooter / Plane, TPV
Shooter / Horizontal
Shooter / Missile Command Like
Shooter / Run and Gun
Shooter / Space Invaders Like
Shooter / Vehicle, FPV
Shooter / Vehicle, TPV
Shooter / Vehicle, Diagonal
Shooter / Vehicle, Horizontal
Shooter / Vehicle, Vertical
Shooter / Vertical
Shooter / Top view
Lightgun Shooter

Only one genre can be picked, and if there is no genre that fits, you can leave the genre in blank.

here are the information available:

{row.get('name_original_reference', '')}
{row.get('sscrp_description', '')}
{row.get('tic_description', '')}
{row.get('tic_description_extra', '')}
{row.get('itch_description', '')}
{row.get('itch_description_extra', '')}

And the game code:
""" + source_code

    ai_response = ""
    try:
        with print_lock:
            print(f"    Sending request to AI assistant for ID {game_id}...")
        chat_completion = openai.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
        )
        ai_response = typing.cast(str, chat_completion.choices[0].message.content)
        
        json_output: dict[str, str] = json.loads(ai_response)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(json_output, f, indent=4)

        with print_lock:
            print(f"    AI Response for {row.get('name_original_reference', '')} - {game_id}: {json_output}")
            print(f"    ✅ Successfully saved AI output to {output_file}")
        return "processed"

    except json.JSONDecodeError:
        with print_lock:
            print(f"    [!] AI for {game_id} returned invalid JSON. Saving raw response to .txt file.")
        error_file = output_file.with_suffix('.txt')
        with open(error_file, 'w', encoding='utf-8') as f:
            _ = f.write(ai_response or "<no response returned>")
        return "error"
    except Exception as e:
        with print_lock:
            print(f"    [!] An error occurred during API call or file writing for ID {game_id}: {e}")
        return "error"
            

@log_command
def ai_assistant_command(args: TColManagerArgs):
    """
    Uses an AI assistant to generate a description and genre for each game
    based on its database information and source code.
    """
    print("--- Starting AI Assistant Processing ---")

    load_dotenv()  # Load environment variables from a .env file if it exists

    api_key = os.environ.get("DEEPINFRA_API_KEY")
    if not api_key:
        print("⚠️  DEEPINFRA_API_KEY not found. Please set it as an environment variable or create a .env file.")
        return

    try:
        openai = OpenAI(
            api_key=api_key,
            base_url="https://api.deepinfra.com/v1/openai",
        )
    except Exception as e:
        print(f"❌ Error initializing OpenAI client: {e}")
        return

    db = load_csv_database(CSV_DATABASE_PATH)
    AI_OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    SOURCE_CODE_PATH.mkdir(parents=True, exist_ok=True) # Also ensure source path exists

    games_to_process: list[tuple[str, dict[str, str]]] = []
    for game_id, row in db.items():
        if get_rom_category(row) == "Games":
            games_to_process.append((game_id, row))

    processed_count, skipped_exist_count, skipped_no_source_count, error_count = 0, 0, 0, 0
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        ProcessResult = typing.Literal["skipped_exist", "skipped_no_source", "error", "processed"]
        future_to_game: dict[Future[typing.Any], str] = {executor.submit(process_game, game_id, row, args, openai): game_id for game_id, row in games_to_process}
        
        total_entries = len(future_to_game)
        for i, future in enumerate(as_completed(future_to_game)):
            game_id = future_to_game[future]
            print(f"\n[{i+1}/{total_entries}] Completed processing for ID: {game_id}")
            
            try:
                result = future.result()
                if result == "processed":
                    processed_count += 1
                elif result == "skipped_exist":
                    skipped_exist_count += 1
                elif result == "skipped_no_source":
                    skipped_no_source_count += 1
                else: # error
                    error_count += 1
            except Exception as exc:
                print(f"    [!] An exception was generated for {game_id}: {exc}")
                error_count += 1

    print("\n--- AI Assistant Summary ---")
    print(f"Successfully processed: {processed_count}")