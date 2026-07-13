# Deploying StockTracker to Streamlit Community Cloud

This walks you from a fresh ADB instance to a live public URL your friends can
use. It uses **wallet-less one-way TLS** so nothing sensitive lives in the repo.

Est. time: ~30–40 min the first time.

---

## Part A — Prepare the database (Oracle Cloud console)

### A1. Allow TLS connections on your ADB
By default ADB requires mTLS (wallet). We switch it to allow TLS so no wallet
files are needed.

1. OCI Console → **Autonomous Database** → open your instance.
2. Under **Network**, find **Mutual TLS (mTLS) authentication** and click **Edit**.
3. **Uncheck** "Require mutual TLS (mTLS) authentication". Save.
   - This enables one-way TLS while still allowing mTLS if you ever want it.

### A2. Add an Access Control List (ACL)
TLS-without-wallet requires an ACL (or a private endpoint). Community Cloud has
no fixed outbound IPs, so you'll allow a broad range and rely on the DB password
+ app login for security.

1. Same **Network** section → **Access control list** → **Edit**.
2. Add an ACL entry. To accept connections from anywhere, add CIDR `0.0.0.0/0`.
   - More cautious option: skip Community Cloud and self-host later behind a
     fixed IP you can whitelist. For friends-only + strong DB password, the open
     ACL is a common pragmatic choice.
3. Save. (Changes take a couple of minutes to apply.)

### A3. Grab your TLS connect string
1. On the ADB instance page click **Database connection**.
2. Set **TLS authentication** to **TLS** (not Mutual TLS).
3. Copy the **`_high`** connection string. It looks like:
   ```
   (description=(retry_count=20)(retry_delay=3)(address=(protocol=tcps)(port=1521)(host=adb.<region>.oraclecloud.com))(connect_data=(service_name=<id>_<db>_high.adb.oraclecloud.com))(security=(ssl_server_dn_match=yes)))
   ```
   This whole string is your **`DB_DSN`**.

### A4. Create the schema and a login user
1. Open **Database Actions → SQL** (or use SQLcl / SQL Developer).
2. Paste and run `schema.sql`. This creates `app_users` and `user_watchlists`.
3. Generate a password hash locally:
   ```bash
   pip install werkzeug
   python make_hash.py 'the-password-you-want'
   ```
4. Back in SQL, insert your first user with that hash:
   ```sql
   INSERT INTO app_users (username, password_hash, display_name)
   VALUES ('upen', '<PASTE_HASH_HERE>', 'Upen');
   COMMIT;
   ```
   (Use the DB user you'll connect as — e.g. `APP_USER` — as `DB_USER`.)

---

## Part B — Test locally (recommended before deploying)

1. In the project folder:
   ```bash
   python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Copy the secrets template and fill it in:
   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```
   Set `DB_USER`, `DB_PASSWORD`, and paste the `DB_DSN` from A3.
3. Run:
   ```bash
   streamlit run app.py
   ```
   Log in with the user you seeded. If the watchlist loads, you're good.

> `.streamlit/secrets.toml` is git-ignored — it will NOT be pushed.

---

## Part C — Push to GitHub

1. Create a **new GitHub repo** (public — Community Cloud's free tier needs it).
2. From the project folder:
   ```bash
   git init
   git add .
   git commit -m "StockTracker Phase 1"
   git branch -M main
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```
3. Double-check on GitHub that **`.streamlit/secrets.toml` and `.env` are NOT
   present** (only the `.example` files should be). The `.gitignore` handles
   this, but verify.

---

## Part D — Deploy on Streamlit Community Cloud

1. Go to **https://share.streamlit.io** and sign in with GitHub.
2. Click **Create app → Deploy a public app from GitHub**.
3. Select your repo, branch `main`, and main file path `app.py`.
4. Before (or right after) deploying, open **Advanced settings → Secrets** (or
   later: App → **Settings → Secrets**) and paste your secrets in TOML form:
   ```toml
   DB_USER = "APP_USER"
   DB_PASSWORD = "your-schema-password"
   DB_DSN = "(description=(retry_count=20)...(security=(ssl_server_dn_match=yes)))"
   ```
5. Click **Deploy**. First build installs `requirements.txt` (a couple minutes).
6. When it's live, open the URL, log in, and confirm it works. Share the URL
   with your friends — each gets their own login you seed via `make_hash.py`
   (or add a small self-signup later).

---

## Troubleshooting

- **ORA-12506 / connection refused** → ACL not applied yet (A2) or mTLS still
  required (A1). Wait a few minutes after saving network changes.
- **DPY-4011 / TLS handshake failed** → you used the mTLS string; re-copy the
  **TLS** `_high` string from A3.
- **"Missing required config"** → a key isn't set in the Cloud Secrets dashboard;
  names must be exactly `DB_USER`, `DB_PASSWORD`, `DB_DSN`.
- **Invalid username/password at the app login** → the seeded hash doesn't match;
  regenerate with `make_hash.py` and re-run the INSERT.
- **App sleeps** → free apps idle out after inactivity; the first visit after a
  nap takes ~30s to wake. Normal.

---

## Security recap

- Repo is public but contains **no secrets** — credentials live only in the
  Streamlit Secrets dashboard.
- DB passwords are never stored; only PBKDF2 hashes in `app_users`.
- All queries are parameterized (no SQL injection).
- Connection is encrypted (TLS 1.2/1.3) even without the wallet.
- The open ACL means the DB endpoint is reachable network-wide; your defense is
  a strong `DB_PASSWORD` + the app login. Rotate the password if you ever suspect
  exposure. For stricter control, self-host behind a fixed whitelisted IP.
