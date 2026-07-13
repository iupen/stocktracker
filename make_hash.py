"""
make_hash.py — Generate a password hash for seeding app_users.

Usage:
    python make_hash.py 'my-super-secret'

Copy the printed hash into the INSERT statement in schema.sql (or run the
INSERT directly against ADB).
"""

import sys

from auth import hash_password

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python make_hash.py '<password>'")
        raise SystemExit(1)
    print(hash_password(sys.argv[1]))
