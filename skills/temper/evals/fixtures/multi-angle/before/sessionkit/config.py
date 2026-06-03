"""Configuration loading for sessionkit.

Pure helper: reads a small JSON config from disk (or returns defaults). Kept
deliberately separate from the token/session logic so the IO concern lives at
the edge, not inside the domain code.
"""

import json
import os

DEFAULT_TTL = 3600  # seconds a token stays valid by default
DEFAULT_CLOCK_SKEW = 5  # seconds of leeway granted around expiry


def load_config(path=None):
    """Load a config dict from ``path``, falling back to defaults.

    Returns a dict with at least ``ttl`` and ``clock_skew`` keys. Missing file
    or unset keys fall back to the module defaults. This is the ONLY function in
    the package that touches the filesystem.
    """
    config = {"ttl": DEFAULT_TTL, "clock_skew": DEFAULT_CLOCK_SKEW}
    if path and os.path.exists(path):
        with open(path, "r") as handle:
            loaded = json.load(handle)
        config.update(loaded)
    return config
