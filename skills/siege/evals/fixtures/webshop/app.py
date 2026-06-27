"""Tiny web layer for the siege eval fixture (#373). Hermetic; NOT a real server.

Contains deliberately PLANTED vulnerabilities at known lines — see
ground-truth-bugs.json. Do NOT "fix" these in place; they are the eval substrate.
The `request`/`urlopen`/`send_file` calls are illustrative stand-ins; this never runs.
"""
import os
from urllib.request import urlopen

ORDERS = {}        # order_id -> {"owner": username, "total": float}
DOWNLOAD_ROOT = "/srv/webshop/files"


def admin_list_users(request):
    # PLANTED v3 (line 17): broken access control / auth bypass — the admin endpoint
    # has NO authentication or role check, so any anonymous caller lists all users.
    return {"users": _all_users()}


def get_order(request, order_id):
    # PLANTED v4 (line 23): IDOR — the order is returned by id with no ownership check
    # against the authenticated user, so any user reads any other user's order.
    return ORDERS.get(order_id)


def fetch_preview(request):
    # PLANTED v5 (line 30): SSRF — the server fetches an attacker-supplied URL with no
    # allow-list, so `url=http://169.254.169.254/...` reaches internal metadata.
    url = request.get("url")
    return urlopen(url).read()


def download(request):
    # PLANTED v6 (line 37): path traversal — the user-supplied name is joined onto the
    # download root with no normalization, so `name=../../etc/passwd` escapes the root.
    name = request.get("name")
    path = os.path.join(DOWNLOAD_ROOT, name)
    with open(path, "rb") as fh:
        return fh.read()


def _all_users():
    return [{"username": "alice", "role": "admin"}]
