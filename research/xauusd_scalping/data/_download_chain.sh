#!/bin/sh
# Sequential Dukascopy downloads (one at a time -- concurrent runs got throttled).
cd "$(dirname "$0")" 2>/dev/null
PY=../../../.venv/bin/python
set -x
$PY -u download_dukascopy.py --symbol EURUSD --from 2026-03-01 --to 2026-09-17
$PY -u download_dukascopy.py --symbol XAUUSD --from 2026-03-01 --to 2026-09-17
$PY -u download_dukascopy.py --symbol XAUUSD --from 2024-01-01 --to 2026-03-01
$PY -u download_dukascopy.py --symbol GBPUSD --from 2026-03-01 --to 2026-09-17
echo CHAIN DONE
