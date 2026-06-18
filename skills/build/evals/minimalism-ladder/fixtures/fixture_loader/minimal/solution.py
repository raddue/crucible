import json


def load_fixture(text):
    data = json.loads(text)
    if not isinstance(data.get("id"), str):
        raise ValueError("fixture requires a string 'id'")
    return data
