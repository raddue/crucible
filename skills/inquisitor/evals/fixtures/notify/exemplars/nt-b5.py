from notify import routes


def test_disallowed_webhook_url_is_refused():
    calls = []

    def transport(url, payload):
        calls.append((url, payload))
        return 200

    # A disallowed (non-allowlisted) URL must be refused before the transport
    # is ever dialed.
    refused = False
    try:
        routes.dispatch("file:///etc/passwd", {"x": 1}, transport)
    except ValueError:
        refused = True
    assert refused is True
    assert calls == []
