# Go-Live Checklist

Use this before switching from paper to **live** mode with real capital.

---

## 1. Infrastructure

- [ ] Server is a dedicated VM/VPS (not a laptop) — uptime matters
- [ ] OS is Ubuntu 22.04 LTS or Debian 12
- [ ] Caddy installed and `Caddyfile` configured with your real domain
- [ ] TLS certificate provisioned (`caddy run` shows no errors)
- [ ] Systemd unit installed (`sudo cp scripts/xillion.service /etc/systemd/system/`) and enabled
- [ ] Server survives reboot: `sudo reboot` → check `systemctl status xillion`

## 2. Environment Variables

- [ ] `.env` has a cryptographically random `APP_SECRET_KEY` (≥32 chars)
- [ ] `.env` has a cryptographically random `ENCRYPTION_KEY` (Fernet base64)
- [ ] `APP_ENV=production`
- [ ] `DATABASE_URL` points to a durable path (not tmpfs)
- [ ] Zerodha credentials set and tested (`make dev` shows "Zerodha: connected")
- [ ] Telegram bot token + chat ID set — test with `curl` to confirm alerts arrive

## 3. Database

- [ ] `alembic upgrade head` runs clean
- [ ] Backup script tested: `make backup` → file appears in `data/backups/`
- [ ] Daily backup cron installed:
  ```
  0 18 * * 1-5  /opt/xillion/scripts/backup_db.sh >> /var/log/xillion-backup.log 2>&1
  ```
- [ ] Restore drill: copy a backup to a temp path, confirm `sqlite3` opens it without errors

## 4. Auth & Security

- [ ] First-run setup completed: unique username, strong password
- [ ] 2FA enabled (Settings → Two-Factor Authentication → Enable 2FA)
- [ ] Login works in a fresh incognito window
- [ ] HTTP-only session cookie is visible in DevTools → Application → Cookies (no JS access)
- [ ] HTTPS redirects HTTP (test with `curl -I http://your-domain.com`)

## 5. Risk Limits

Review `.env` settings before going live:

| Variable | Recommended starting value |
|---|---|
| `OPS_LIMIT_PER_SECOND` | `9` (SEBI hard cap is 10) |
| `DEFAULT_ACCOUNT_DAILY_LOSS_PCT` | `1` (increase only after stable paper run) |
| `DEFAULT_PER_STRATEGY_DAILY_LOSS_PCT` | `0.5` |
| `DEFAULT_MAX_OPEN_POSITIONS` | `3` |

- [ ] Risk limits set conservatively for first week
- [ ] Kill switch tested: click KILL SWITCH in UI → confirm banner appears, WS event received
- [ ] Kill switch reset tested

## 6. Strategy Paper Run

- [ ] Run chosen strategy in paper mode for at least **5 trading days**
- [ ] P&L curve on Backtest page is net-positive (after slippage)
- [ ] No unhandled exceptions in Logs page during a full session
- [ ] Tick stream stable: Dashboard shows live prices continuously

## 7. Crash Recovery

- [ ] Simulate crash: `sudo kill -9 $(pgrep uvicorn)` → confirm systemd restarts within 5s
- [ ] Open positions survive restart (paper broker state is in-memory — acceptable for paper)
- [ ] For live: positions are reconciled via broker API on reconnect (see `ZerodhaBroker.connect`)

## 8. OPS Limiter Stress Test

Run the unit tests to confirm the limiter is wired correctly:

```bash
pytest tests/unit/test_risk_manager.py -v
```

All tests must pass.

## 9. First Live Session

- [ ] Start with **minimum lot size** (1 lot NIFTY = 50 units)
- [ ] Monitor Logs page continuously for the first 30 minutes
- [ ] Keep Telegram notifications open on your phone
- [ ] Know the kill switch shortcut (red button, top right of every page)
- [ ] Set a personal hard stop: if daily P&L hits -X%, hit kill switch manually

---

> **Last resort**: if the kill switch is unreachable (server down), log into Kite Web and cancel all open orders manually, then close positions.
