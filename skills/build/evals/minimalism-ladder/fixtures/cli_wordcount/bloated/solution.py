import os


# A deliberately over-engineered but functionally-identical implementation.
# Same behaviour as the minimal solution, more (non-comment) source lines.

class ArgError(Exception):
    pass


def _parse_args(args):
    if len(args) != 2:
        raise ArgError("wrong number of arguments")
    subcommand = args[0]
    if subcommand != "count":
        raise ArgError("unknown subcommand")
    target_path = args[1]
    return target_path


def _is_safe(path):
    normalized = os.path.normpath(path)
    parts = normalized.split(os.sep)
    for part in parts:
        if part == "..":
            return False
    return True


def _read_text(path):
    handle = open(path, encoding="utf-8")
    try:
        contents = handle.read()
    finally:
        handle.close()
    return contents


def _count_words(text):
    words = text.split()
    total = len(words)
    return total


def run(args):
    try:
        path = _parse_args(args)
    except ArgError:
        return 1, "usage: count <file>\n"
    if not _is_safe(path):
        return 1, "rejected: path escapes working directory\n"
    text = _read_text(path)
    count = _count_words(text)
    output = str(count) + "\n"
    return 0, output
