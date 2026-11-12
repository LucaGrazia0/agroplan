#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then python3.12 -m venv .venv; fi
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
if [ ! -f .env ]; then
  cp .env.example .env
  echo 'Creato .env vuoto. Configura Copernicus per le funzioni satellitari.'
fi
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
