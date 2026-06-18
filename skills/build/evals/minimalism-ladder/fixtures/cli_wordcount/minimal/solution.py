import os


def run(args):
    if len(args) != 2 or args[0] != "count":
        return 1, "usage: count <file>\n"
    path = args[1]
    if ".." in os.path.normpath(path).split(os.sep):
        return 1, "rejected: path escapes working directory\n"
    with open(path, encoding="utf-8") as f:
        return 0, f"{len(f.read().split())}\n"
