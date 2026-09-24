#!/bin/sh
# Sequential Dukascopy downloads (one at a time -- concurrent runs got throttled).
# Base --delay 5 (adaptive: doubles on throttle, see _next_delay). Dukascopy
# throttled this IP hard after ~a day at 2.5s (2026-09-24).
cd "$(dirname "$0")" 2>/dev/null
PY=../../../.venv/bin/python
set -x
$PY -u download_dukascopy.py --symbol EURUSD --from 2026-03-01 --to 2026-09-17 --delay 5
$PY -u download_dukascopy.py --symbol XAUUSD --from 2026-03-01 --to 2026-09-17 --delay 5
$PY -u download_dukascopy.py --symbol XAUUSD --from 2024-01-01 --to 2026-03-01 --delay 5
$PY -u download_dukascopy.py --symbol GBPUSD --from 2026-03-01 --to 2026-09-17 --delay 5
echo CHAIN DONE
