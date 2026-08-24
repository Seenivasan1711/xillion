#!/usr/bin/env bash
# Wrapper for .claude/launch.json's "xillion-dev" config. `make dev` assumes
# uvicorn is already on PATH (it doesn't activate the venv itself) -- a bare
# `make dev` launch from a tool that spawns a fresh shell fails with
# "uvicorn: command not found". This activates .venv first.
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
exec make dev
