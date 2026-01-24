import argparse
import yaml

def export_carapace_spec(parser):
    def _visit(name, p, help_text=""):
        cmd = {
            "name": name,
            "description": p.description or help_text or "",
        }

        flags = {}
        positionals = []
        flag_completions = {}
        exclusive_groups = []

        # Get mutually exclusive groups
        for group in p._mutually_exclusive_groups:
            group_flags = []
            for action in group._group_actions:
                if action.option_strings:
                    # Use the long form without -- prefix
                    flag_name = action.option_strings[-1].lstrip('-')
                    group_flags.append(flag_name)
            if len(group_flags) > 1:
                exclusive_groups.append(group_flags)

        for action in p._actions:
            if isinstance(action, argparse._HelpAction):
                continue

            if action.option_strings:
                # Flag argument
                suffix = "="
                if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction, argparse._CountAction)):
                    suffix = ""
                elif action.nargs == 0:
                    suffix = ""
                elif action.nargs == '?':
                    suffix = "?"
                elif action.nargs == '*' or action.nargs == '+':
                    suffix = "*"
                elif isinstance(action, argparse._AppendAction):
                    suffix = "*"

                flag_key = ", ".join(action.option_strings) + suffix
                flags[flag_key] = action.help or ""

                # Determine completion for this flag
                flag_name = action.option_strings[-1].lstrip('-')
                if action.choices:
                    flag_completions[flag_name] = list(action.choices)
                elif any(hint in flag_name.lower() for hint in ['path', 'dir', 'dest', 'folder']):
                    flag_completions[flag_name] = ["$directories"]
                elif any(hint in flag_name.lower() for hint in ['file']):
                    flag_completions[flag_name] = ["$files"]

            elif isinstance(action, argparse._SubParsersAction):
                help_map = {a.dest: a.help for a in action._choices_actions}
                commands = []
                for sub_name, sub_parser in action.choices.items():
                    sub_help = help_map.get(sub_name) or ""
                    commands.append(_visit(sub_name, sub_parser, sub_help))
                if commands:
                    cmd["commands"] = commands
            else:
                # Positional argument
                if action.choices:
                    positionals.append(list(action.choices))
                elif any(hint in action.dest.lower() for hint in ['file', 'xml', 'json']):
                    positionals.append(["$files"])
                elif any(hint in action.dest.lower() for hint in ['path', 'dir', 'dest', 'folder']):
                    positionals.append(["$directories"])

        if flags:
            cmd["flags"] = flags

        if exclusive_groups:
            cmd["exclusiveflags"] = exclusive_groups

        # Build completion section
        completion = {}
        if flag_completions:
            completion["flag"] = flag_completions
        if positionals:
            completion["positional"] = positionals
        if completion:
            cmd["completion"] = completion

        return cmd

    spec = _visit(parser.prog.split('/')[-1], parser)
    return f"# yaml-language-server: $schema=https://carapace.sh/schemas/command.json\n{yaml.dump(spec, sort_keys=False)}"