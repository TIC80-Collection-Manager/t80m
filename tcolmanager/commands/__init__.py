'''
# Import all command functions so they can be easily imported from tcolmanager.commands
'''
from .dispatchers import update_csv_dispatcher, get_roms_dispatcher
from .sync_filenames import sync_filenames_command
from .get_coverarts import get_coverarts_command
from .update_gamelistxml import update_gamelistxml_command
from .recalculate_hashes import recalculate_hashes_command
from .export_collection import export_collection_command
from .import_xml_data import import_xml_data_command
from .ai_assistant import ai_assistant_command
from .import_json import import_json_command
from .init import init_command

__all__ = [
    'update_csv_dispatcher',
    'get_roms_dispatcher',
    'sync_filenames_command',
    'get_coverarts_command',
    'update_gamelistxml_command',
    'recalculate_hashes_command',
    'export_collection_command',
    'import_xml_data_command',
    "ai_assistant_command",
    "import_json_command",
    "init_command",
]