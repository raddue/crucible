#!/usr/bin/env python3
"""UUIDv7 generator. 48-bit unix-ms timestamp + version 7 + random bits + variant 10.

Sortable, millisecond-precision, unique. No third-party dependency.
Canonical single source of truth — referenced from skills/shared/ledger-append.md.
"""
import secrets
import time


def uuid7() -> str:
    """Return a canonical UUIDv7 string: xxxxxxxx-xxxx-7xxx-yxxx-xxxxxxxxxxxx."""
    ms = time.time_ns() // 1_000_000
    ts = ms.to_bytes(6, "big")              # 48-bit timestamp
    rand = secrets.token_bytes(10)          # 80 random bits (we overwrite 6 of them)
    b = bytearray(ts + rand)
    # Version nibble = 7 in byte 6 (high nibble)
    b[6] = (b[6] & 0x0F) | 0x70
    # Variant nibble = 10xx in byte 8 (high two bits)
    b[8] = (b[8] & 0x3F) | 0x80
    h = b.hex()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


if __name__ == "__main__":
    print(uuid7())
