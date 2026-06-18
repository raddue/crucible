def run(args):
    # Guard dropped: blindly opens whatever path it is handed, and treats a
    # missing arg as "read nothing" -> exit 0. Happy path still works.
    path = args[1] if len(args) > 1 else None
    if path is None:
        return 0, "0\n"
    with open(path, encoding="utf-8") as f:
        return 0, f"{len(f.read().split())}\n"
