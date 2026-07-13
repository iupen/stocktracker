"""
auth.py — Password hashing/verification helpers.

Uses Werkzeug's PBKDF2 implementation (ships with Streamlit's dependency tree,
no extra install) so we never store or compare plaintext passwords.
"""

from __future__ import annotations

from werkzeug.security import check_password_hash, generate_password_hash


def hash_password(plaintext: str) -> str:
    """Return a salted PBKDF2 hash suitable for the app_users.password_hash column."""
    # 255-char column comfortably fits the default pbkdf2:sha256 output.
    return generate_password_hash(plaintext, method="pbkdf2:sha256")


def verify_password(plaintext: str, stored_hash: str) -> bool:
    """Constant-time-ish check of a candidate password against a stored hash."""
    if not stored_hash:
        return False
    return check_password_hash(stored_hash, plaintext)
