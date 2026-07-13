"""
config.py — Single place to resolve configuration/secrets.

Resolution order for every key:
    1. Streamlit secrets  (st.secrets)  — used when deployed to Streamlit Cloud
                                           or when a local .streamlit/secrets.toml exists
    2. Environment variables            — used for local dev / other hosts

This lets the exact same code run locally (env vars or secrets.toml) and on
Streamlit Community Cloud (dashboard secrets) with no changes.
"""

from __future__ import annotations

import os
from typing import Optional


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """Return a config value from Streamlit secrets, else env, else default."""
    # Try Streamlit secrets first. Wrapped in try/except so non-Streamlit
    # callers (e.g. make_hash.py) don't blow up if streamlit isn't importable
    # or no secrets file exists.
    try:
        import streamlit as st  # local import keeps this module import-light

        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass

    return os.getenv(key, default)


def require(*keys: str) -> dict[str, str]:
    """Fetch required keys; raise a clear error listing any that are missing."""
    resolved: dict[str, str] = {}
    missing: list[str] = []
    for key in keys:
        val = get_secret(key)
        if val:
            resolved[key] = val
        else:
            missing.append(key)
    if missing:
        raise RuntimeError(
            "Missing required config: "
            + ", ".join(missing)
            + ". Set them in .streamlit/secrets.toml, the Streamlit Cloud "
            + "secrets dashboard, or as environment variables."
        )
    return resolved
