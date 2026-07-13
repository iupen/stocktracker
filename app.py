"""
app.py — StockTracker Streamlit UI (Phase 1).

Features
--------
* Login/password gate backed by app_users (PBKDF2 hashes).
* SHARED watchlist: everyone sees all friends' entries with an "Added by" column.
* Refresh button to re-pull the group watchlist without logging out.
* "Add to Watchlist" form: ticker + sentiment + optional thesis + optional price.
* Edit / remove limited to YOUR OWN rows.

Run:  streamlit run app.py
"""

from __future__ import annotations

import re

import pandas as pd
import streamlit as st
import oracledb

import db
from auth import verify_password

# --------------------------------------------------------------------------- #
# Page config — wide layout collapses gracefully on mobile.
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="StockTracker",
    page_icon="📈",
    layout="centered",  # 'centered' reads better on phones than 'wide'
    initial_sidebar_state="collapsed",
)

SENTIMENTS = ["BULLISH", "NEUTRAL", "BEARISH"]
TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,12}$")  # letters, digits, dot, dash


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
def _do_login(username: str, password: str) -> bool:
    """Validate credentials; on success, stash user info in session_state."""
    user = db.get_user_by_username(username.strip())
    if user and verify_password(password, user["password_hash"]):
        st.session_state["user"] = {
            "user_id": user["user_id"],
            "username": user["username"],
            "display_name": user["display_name"] or user["username"],
        }
        return True
    return False


def render_login() -> None:
    """Login screen shown when no user is in session."""
    st.title("📈 StockTracker")
    st.caption("Collaborative watchlists & trading theses")

    with st.form("login_form"):
        username = st.text_input("Username", autocomplete="username")
        password = st.text_input(
            "Password", type="password", autocomplete="current-password"
        )
        submitted = st.form_submit_button("Log in", use_container_width=True)

    if submitted:
        if not username or not password:
            st.error("Enter both username and password.")
        elif _do_login(username, password):
            st.rerun()
        else:
            st.error("Invalid username or password.")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _sentiment_badge(flag: str) -> str:
    return {"BULLISH": "🟢 Bullish", "BEARISH": "🔴 Bearish"}.get(flag, "⚪ Neutral")


def _fmt_price(price) -> str:
    """Show price with 2 decimals, or a dash when it wasn't recorded."""
    return f"{price:.2f}" if price is not None else "—"


# --------------------------------------------------------------------------- #
# Add
# --------------------------------------------------------------------------- #
def render_add_form(user_id: int) -> None:
    """The 'Add to Watchlist' input form with validation."""
    with st.expander("➕ Add to watchlist", expanded=False):
        with st.form("add_form", clear_on_submit=True):
            ticker = st.text_input("Ticker", max_chars=12, placeholder="AAPL")
            sentiment = st.selectbox("Sentiment", SENTIMENTS, index=1)
            # Nullable price: value=None means the box starts empty and returns
            # None if left blank, which db.py stores as SQL NULL.
            price = st.number_input(
                "Price when added (optional)",
                min_value=0.0,
                value=None,
                step=0.01,
                format="%.2f",
                help="Leave blank if unknown, e.g. 192.35",
            )
            thesis = st.text_area(
                "Thesis (optional)",
                placeholder="Why are you watching this? Write as much as you like.",
                height=180,  # roomy box; the CLOB column holds unlimited text
            )
            add = st.form_submit_button("Add", use_container_width=True)

        if add:
            clean = ticker.strip().upper()
            if not clean:
                st.warning("Ticker is required.")
            elif not TICKER_RE.match(clean):
                st.warning("Ticker must be 1-12 chars: letters, digits, '.' or '-'.")
            else:
                try:
                    db.add_to_watchlist(
                        user_id, clean, sentiment, thesis.strip(), price
                    )
                    st.success(f"Added {clean}.")
                    st.rerun()
                except oracledb.IntegrityError:
                    st.warning(f"{clean} is already on your watchlist.")
                except Exception as exc:  # surface DB errors without crashing
                    st.error(f"Could not add ticker: {exc}")


# --------------------------------------------------------------------------- #
# Shared table (everyone's entries)
# --------------------------------------------------------------------------- #
def render_shared_table(all_rows: list[dict]) -> None:
    """Read-only table of every friend's watchlist entries."""
    df = pd.DataFrame(
        [
            {
                "Added by": r["owner"],
                "Ticker": r["ticker"],
                "Sentiment": _sentiment_badge(r["sentiment_flag"]),
                "Added price": _fmt_price(r["added_price"]),
                "Added on": r["created_at"].strftime("%Y-%m-%d"),
                "Thesis": r["thesis"],
            }
            for r in all_rows
        ]
    )
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            # Wide, wrapping cell so long theses stay readable in the table.
            "Thesis": st.column_config.TextColumn("Thesis", width="large"),
        },
    )


# --------------------------------------------------------------------------- #
# Edit / remove — restricted to the logged-in user's OWN rows
# --------------------------------------------------------------------------- #
def render_edit_form(user_id: int, own_rows: list[dict]) -> None:
    """Edit the sentiment and (long) thesis of one of your own rows."""
    with st.expander("✏️ Edit one of your theses"):
        if not own_rows:
            st.caption("You haven't added any tickers yet.")
            return

        label_to_row = {r["ticker"]: r for r in own_rows}
        choice = st.selectbox(
            "Ticker to edit", list(label_to_row.keys()), key="edit_ticker"
        )
        current = label_to_row[choice]

        with st.form("edit_form"):
            sentiment = st.selectbox(
                "Sentiment",
                SENTIMENTS,
                index=SENTIMENTS.index(current["sentiment_flag"]),
            )
            # Prefilled with the existing thesis; big box for long-form text.
            thesis = st.text_area(
                "Thesis",
                value=current["thesis"],
                height=300,
                placeholder="Update your reasoning...",
            )
            save = st.form_submit_button("Save changes", use_container_width=True)

        if save:
            try:
                db.update_entry(
                    user_id, current["watchlist_id"], sentiment, thesis.strip()
                )
                st.success(f"Updated {choice}.")
                st.rerun()
            except Exception as exc:  # surface DB errors without crashing
                st.error(f"Could not update: {exc}")


def render_remove(user_id: int, own_rows: list[dict]) -> None:
    """Remove one of your own rows."""
    with st.expander("🗑️ Remove one of your tickers"):
        if not own_rows:
            st.caption("You haven't added any tickers yet.")
            return

        label_to_id = {r["ticker"]: r["watchlist_id"] for r in own_rows}
        choice = st.selectbox(
            "Ticker to remove", list(label_to_id.keys()), key="remove_ticker"
        )
        if st.button("Remove", type="secondary"):
            db.remove_from_watchlist(user_id, label_to_id[choice])
            st.success(f"Removed {choice}.")
            st.rerun()


# --------------------------------------------------------------------------- #
# Main authenticated view
# --------------------------------------------------------------------------- #
def render_app() -> None:
    user = st.session_state["user"]
    user_id = user["user_id"]

    # Header row: title + Refresh + Log out.
    col1, col2, col3 = st.columns([3, 1, 1])
    col1.title("📈 StockTracker")
    col1.caption(f"Signed in as **{user['display_name']}**")
    # A button click reruns the script, which re-queries the DB below — so this
    # pulls in entries other friends have added without logging out.
    if col2.button("🔄 Refresh", use_container_width=True):
        st.rerun()
    if col3.button("Log out", use_container_width=True):
        st.session_state.pop("user", None)
        st.rerun()

    st.divider()
    render_add_form(user_id)

    # Shared view: everyone's entries. Own rows drive the edit/remove controls.
    all_rows = db.get_all_watchlists()
    own_rows = [r for r in all_rows if r["user_id"] == user_id]

    st.subheader("Group watchlist")
    if not all_rows:
        st.info("No tickers yet. Add one to get the group started.")
        return

    render_shared_table(all_rows)
    render_edit_form(user_id, own_rows)
    render_remove(user_id, own_rows)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main() -> None:
    if "user" not in st.session_state:
        render_login()
    else:
        render_app()


if __name__ == "__main__":
    main()
