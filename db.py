"""
db.py — Secure Oracle Autonomous Database access layer for StockTracker.

Design notes
------------
* Uses python-oracledb in THIN mode (pure Python, no Instant Client install) —
  this is what makes the app deployable to Streamlit Community Cloud.
* Connects to ADB over ONE-WAY TLS with NO wallet files. This requires the ADB
  instance to allow TLS connections (mTLS requirement disabled) and an ACL that
  permits the client. DB_DSN is the full TLS connect string (see .env.example).
* A module-level connection pool is created once and reused. Streamlit reruns
  the script on every interaction, so we guard pool creation with a singleton.
* NO credentials are hardcoded. Everything comes from config.get_secret(), which
  resolves Streamlit secrets first, then environment variables.

Required config keys (see .streamlit/secrets.toml.example / .env.example):
    DB_USER        e.g. APP_USER
    DB_PASSWORD    schema password
    DB_DSN         full TLS connect string, e.g.
                   (description=(retry_count=20)(retry_delay=3)
                    (address=(protocol=tcps)(port=1521)(host=xxx.oraclecloud.com))
                    (connect_data=(service_name=xxx_high.adb.oraclecloud.com))
                    (security=(ssl_server_dn_match=yes)))
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Optional

import oracledb

from config import require

# --------------------------------------------------------------------------- #
# Connection pool (created lazily, reused across Streamlit reruns).
# --------------------------------------------------------------------------- #

_pool: Optional[oracledb.ConnectionPool] = None


def get_pool() -> oracledb.ConnectionPool:
    """Return a singleton connection pool, creating it on first use."""
    global _pool
    if _pool is not None:
        return _pool

    cfg = require("DB_USER", "DB_PASSWORD", "DB_DSN")

    # Wallet-less TLS: thin mode validates the ADB server cert against the
    # system CA bundle. No config_dir / wallet_location / wallet_password needed.
    _pool = oracledb.create_pool(
        user=cfg["DB_USER"],
        password=cfg["DB_PASSWORD"],
        dsn=cfg["DB_DSN"],
        min=1,
        max=4,               # small group of friends — a tiny pool is plenty
        increment=1,
        timeout=60,          # seconds an idle connection may live
        getmode=oracledb.POOL_GETMODE_WAIT,
    )
    return _pool


@contextmanager
def get_connection() -> Iterator[oracledb.Connection]:
    """Borrow a connection from the pool and guarantee it is returned."""
    pool = get_pool()
    conn = pool.acquire()
    try:
        yield conn
    finally:
        pool.release(conn)


# --------------------------------------------------------------------------- #
# Row helper — CLOBs must be .read() while the cursor is still open.
# --------------------------------------------------------------------------- #

def _row_to_dict(r: tuple, with_owner: bool = False) -> dict[str, Any]:
    """Map a watchlist SELECT row to a dict. thesis is read from its CLOB."""
    thesis = r[3].read() if r[3] is not None else ""
    d = {
        "watchlist_id": r[0],
        "ticker": r[1],
        "sentiment_flag": r[2],
        "thesis": thesis,
        "added_price": r[4],      # may be None
        "created_at": r[5],
        "updated_at": r[6],
    }
    if with_owner:
        d["user_id"] = r[7]
        d["owner"] = r[8]         # display_name or username
    return d


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #

def get_user_by_username(username: str) -> Optional[dict[str, Any]]:
    """Fetch an active user by (case-insensitive) username, or None."""
    sql = """
        SELECT user_id, username, password_hash, display_name
        FROM   app_users
        WHERE  LOWER(username) = LOWER(:username)
        AND    is_active = 1
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, username=username)
            row = cur.fetchone()
            if row is None:
                return None
            return {
                "user_id": row[0],
                "username": row[1],
                "password_hash": row[2],
                "display_name": row[3],
            }


def create_user(username: str, password_hash: str, display_name: str) -> int:
    """Insert a new user and return the generated user_id."""
    sql = """
        INSERT INTO app_users (username, password_hash, display_name)
        VALUES (:username, :password_hash, :display_name)
        RETURNING user_id INTO :new_id
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            new_id = cur.var(oracledb.NUMBER)
            cur.execute(
                sql,
                username=username,
                password_hash=password_hash,
                display_name=display_name,
                new_id=new_id,
            )
            conn.commit()
            return int(new_id.getvalue()[0])


# --------------------------------------------------------------------------- #
# Watchlists
# --------------------------------------------------------------------------- #

def get_watchlist(user_id: int) -> list[dict[str, Any]]:
    """Return the logged-in user's OWN rows (used for edit/remove controls)."""
    sql = """
        SELECT watchlist_id, ticker, sentiment_flag, thesis,
               added_price, created_at, updated_at
        FROM   user_watchlists
        WHERE  user_id = :user_id
        ORDER  BY created_at DESC
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, user_id=user_id)
            return [_row_to_dict(r) for r in cur]


def get_all_watchlists() -> list[dict[str, Any]]:
    """
    Return EVERYONE's watchlist rows joined with the owner's name.

    Powers the shared, collaborative view. Read-only for other users; the UI
    only offers edit/remove on rows whose user_id matches the logged-in user.
    """
    sql = """
        SELECT w.watchlist_id, w.ticker, w.sentiment_flag, w.thesis,
               w.added_price, w.created_at, w.updated_at,
               w.user_id, NVL(u.display_name, u.username) AS owner
        FROM   user_watchlists w
        JOIN   app_users u ON u.user_id = w.user_id
        ORDER  BY w.created_at DESC
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return [_row_to_dict(r, with_owner=True) for r in cur]


def add_to_watchlist(
    user_id: int,
    ticker: str,
    sentiment_flag: str,
    thesis: str = "",
    added_price: Optional[float] = None,
) -> None:
    """
    Add a ticker to a user's watchlist. added_price is optional (nullable).

    Raises oracledb.IntegrityError if (user_id, ticker) already exists — the
    caller (app.py) catches this and shows a friendly message.
    """
    sql = """
        INSERT INTO user_watchlists
            (user_id, ticker, sentiment_flag, thesis, added_price)
        VALUES
            (:user_id, :ticker, :sentiment_flag, :thesis, :added_price)
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                user_id=user_id,
                ticker=ticker.strip().upper(),
                sentiment_flag=sentiment_flag,
                thesis=thesis,
                added_price=added_price,   # None -> SQL NULL
            )
            conn.commit()


def update_entry(
    user_id: int, watchlist_id: int, sentiment_flag: str, thesis: str
) -> None:
    """
    Update the sentiment and thesis of an existing watchlist row.

    Scoped to (watchlist_id, user_id) so a user can only edit their own rows.
    thesis binds to a CLOB, so it can hold arbitrarily long text. The
    updated_at column is refreshed automatically by the DB trigger.
    (added_price is set once at add-time and left as-is here.)
    """
    sql = """
        UPDATE user_watchlists
        SET    sentiment_flag = :sentiment_flag,
               thesis         = :thesis
        WHERE  watchlist_id = :watchlist_id
        AND    user_id = :user_id
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                sentiment_flag=sentiment_flag,
                thesis=thesis,
                watchlist_id=watchlist_id,
                user_id=user_id,
            )
            conn.commit()


def remove_from_watchlist(user_id: int, watchlist_id: int) -> None:
    """Delete a single watchlist row, scoped to the owning user for safety."""
    sql = """
        DELETE FROM user_watchlists
        WHERE  watchlist_id = :watchlist_id
        AND    user_id = :user_id
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, watchlist_id=watchlist_id, user_id=user_id)
            conn.commit()
