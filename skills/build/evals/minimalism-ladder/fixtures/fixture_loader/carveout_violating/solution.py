import json


def load_fixture(text):
    # Guard dropped: returns whatever JSON parses to, no schema validation.
    return json.loads(text)
