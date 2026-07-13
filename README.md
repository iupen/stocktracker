# StockTracker — Phase 1

A small collaborative stock-tracking app: friends log in, keep watchlists with a
sentiment flag and a trading thesis per ticker.

**Stack:** Streamlit (UI) · python-oracledb **thin mode** (DB) · Oracle
Autonomous Database 26ai over **wallet-less one-way TLS**. ORDS is deferred to a
later phase — Streamlit talks to ADB directly via the driver. Thin mode + TLS is
what makes this deployable to **Streamlit Community Cloud**.

## Files

| File | Purpose |
|---|---|
| `schema.sql` | DDL for `app_users` + `user_watchlists` |
| `config.py` | Resolves secrets: Streamlit secrets → env vars |
| `db.py` | Pooled ADB TLS connection + parameterized data access |
| `auth.py` | PBKDF2 password hashing / verification |
| `app.py` | Streamlit UI: login gate, watchlist table, add/remove forms |
| `make_hash.py` | CLI to generate a password hash for seeding users |
| `.streamlit/secrets.toml.example` | Secrets template (local + Cloud) |
| `.env.example` | Optional env-var alternative to secrets.toml |
| `.gitignore` | Keeps secrets/wallets out of git |
| `requirements.txt` | Python dependencies |
| `DEPLOY.md` | **Step-by-step** GitHub + Streamlit Cloud deployment |

## Quickstart (local)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then fill in
streamlit run app.py
```

You'll first need to create the schema and seed a user — see **`DEPLOY.md`**,
which covers the whole path from a fresh ADB instance to a live public URL
(enabling TLS, ACLs, getting the connect string, GitHub, and Streamlit Cloud).

## Configuration keys

Set these in `.streamlit/secrets.toml` (local) or the Streamlit Cloud Secrets
dashboard (hosted):

- `DB_USER` — schema user, e.g. `APP_USER`
- `DB_PASSWORD` — that user's password
- `DB_DSN` — the full **TLS** connect string from the ADB console (`_high` alias)

## Security notes

- No secrets in the repo — credentials live in secrets.toml / Cloud Secrets only.
- Passwords stored as salted PBKDF2 hashes, never plaintext.
- All SQL uses bind variables (parameterized) — no SQL injection.
- Connection is TLS-encrypted even without the wallet.
- Public Community Cloud app + open ACL means your defense is a strong
  `DB_PASSWORD` + the app login gate. See `DEPLOY.md` for stricter options.

## Next (Phase 2 ideas)

Live prices, performance metrics per thesis, shared/group watchlists, self-signup,
and an ORDS REST layer so non-Python clients can read the same data.
