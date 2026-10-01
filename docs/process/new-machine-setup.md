# Setting up on a new machine

One consolidated checklist for picking this project up on a different
laptop — without redoing the ~23-hour Dukascopy backfill, the NSE
Bhavcopy warehouse build, or losing broker/API credentials. Everything
needed to do this quickly already exists (backup/restore scripts, a
shared cloud DB); this page just puts the steps in order.

**Prerequisite — do this now, on your current machine, before you need
it:** keep fresh backups uploaded somewhere off this laptop (Google
Drive, etc). See [§3](#3-restore-the-bulk-data-optional-but-saves-hours)
for exactly which four things and the commands that produce them. Nothing
below works on a new machine without these already sitting in Drive.

---

## 1. Clone and install

```bash
git clone <this repo's URL> xillion
cd xillion
git checkout feat/track-b-pipelines   # or whichever branch you're continuing

make setup        # creates .env from .env.example, installs Python + Node deps
```

Needs Python 3.11+ and Node 20+ already on the machine (a virtualenv
active before running `make setup`). `make setup` is safe to re-run — it
skips creating `.env` if one already exists.

## 2. Bring in real config and credentials

`make setup` just created a **blank** `.env` from the template — it has no
real values yet. Overwrite it with your real one from Drive:

```bash
# download .env from Drive, then:
cp ~/Downloads/.env .env
```

This one file carries almost everything that makes the app *yours*
instead of a fresh install:
- `DATABASE_URL` — points at the shared Supabase Postgres. Once this is
  in place, the new machine sees the exact same users, broker
  connections, strategy instances, trade journal and My Trades data as
  every other machine — **nothing to migrate or restore for any of
  that**, since it was never local to begin with.
- `ENCRYPTION_KEY` — the Fernet key the app uses to decrypt broker
  credentials already stored encrypted in that shared DB. **This has to
  be the exact same key that encrypted them**, or every broker connection
  looks "configured" but fails to actually authenticate. If `.env` is
  restored correctly this is automatic — the only way to get this wrong
  is generating a *new* key instead of reusing the real one.
- Every broker/API key (Zerodha, Dhan, Twelve Data, Finnhub, Telegram,
  etc).

Don't hand-generate a new `ENCRYPTION_KEY` or a new `APP_SECRET_KEY` on
the new machine — both must match what's already in the shared DB.

`data/.encryption_key` (a separate, auto-generated fallback file — see
`README.md`) is **not used** as long as `ENCRYPTION_KEY` is set directly
in `.env`, which it is. No need to restore it unless you deliberately
want the auto-generate-per-machine behavior instead.

## 3. Restore the bulk data (optional, but saves hours)

None of this is required to run the app — `make dev` works with an empty
`data/` directory, it just means backtests re-fetch from NSE Bhavcopy /
Dukascopy on demand instead of having history cached. Restoring these
four backups just skips that wait:

| What | Produced by (run on the OLD machine) | Restored by (run on the NEW machine) |
|---|---|---|
| Backtest warehouse (NIFTY/BANKNIFTY bars + option chains, ~240MB gzipped) | `make backup-warehouse` | `make restore-warehouse FILE=path/to/warehouse_*.db.gz` |
| Research market data (XAUUSD + EURUSD Dukascopy M1, imported MT5 broker history — ~110MB gzipped) | `make backup-xauusd-research` | `make restore-xauusd-research FILE=path/to/xauusd_research_*.tar.gz` |

Both are whole-directory/whole-file snapshots, so they automatically pick
up anything added later (a new instrument, a new table) — nothing to
update in the scripts as the data grows.

> **The imported MT5 broker history inside the research backup is not
> re-downloadable** the way the Dukascopy data is (it came from manually
> exported MT5 reports) — if that backup is ever lost without a copy in
> Drive, it's gone for good. Worth confirming the Drive copy is current
> after any session that imports more broker history.

**Keep the Drive copies current.** Re-run both `make backup-warehouse`
and `make backup-xauusd-research` and re-upload whenever either dataset
materially moves forward (another `/data/backfill` run, another MT5
history import, a month+ of time passing) — a `new-machine` restore is
only as good as the last upload. There's no automatic reminder for this;
check in passing whenever you're doing other work in this project.

## 4. Verify the restore actually worked

```bash
make dev
```

Then, in the browser (`http://localhost:5174`):
- Log in (not Setup — Setup only appears for a genuinely empty DB; seeing
  the login screen instead already confirms `DATABASE_URL` is correctly
  pointed at the shared Postgres).
- **Settings → Brokers** — each previously-connected broker should show
  **connected**, not "needs re-auth." If one shows re-auth-needed, that's
  the `ENCRYPTION_KEY` mismatch described above, not a real credential
  problem — check `.env` was actually overwritten, not merged/skipped.
- **Settings → Data Providers** — coverage should show the restored
  NIFTY/BANKNIFTY date range if you restored the warehouse backup.
- **Backtest page** — run anything short against a date inside that
  range; should return real results with no NSE Bhavcopy network calls.

```bash
pytest tests/ -q    # or: make test
```
Full suite should pass with no setup beyond the above — none of the tests
depend on the restored bulk data.

## 5. Gold Lane B1 (MT5/Funding Pips) — only if this machine will run it

This is the one piece that's genuinely **per-machine, not something a
backup restores** — the official `MetaTrader5` Python package only talks
to a real MT5 terminal on the *same* machine, so a brand-new Mac needs
its own Wine + MT5 terminal + bridge process, not a copy of anyone else's.
Full walkthrough: [`mt5_bridge/README.md`](../../mt5_bridge/README.md).
Skip this section entirely if this machine is only for Options/backtest
work — nothing else on this page depends on it.

## 6. What you do NOT need to do

- **No DB migration step.** `DATABASE_URL` already points at the live
  shared Postgres; a new machine just connects to it, it doesn't need its
  own copy. `alembic upgrade head` is only relevant if you're adding a
  *new* migration, not for onboarding a machine.
- **No re-entering broker credentials.** They're already encrypted in the
  shared DB; `.env`'s `ENCRYPTION_KEY` is what lets this machine read
  them, not a fresh connect flow.
- **No Redis / separate infra to install.** Nothing in this stack
  currently depends on it (see `deferred-backlog.md`).
