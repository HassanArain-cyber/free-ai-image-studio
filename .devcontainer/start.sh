#!/usr/bin/env bash
set -euo pipefail
if curl --fail --silent --max-time 2 http://127.0.0.1:8000/api/status >/dev/null; then
  echo "ImageForge already running."
  exit 0
fi
if [[ ! -x .venv/bin/python ]]; then python -m venv .venv; fi
.venv/bin/python -m pip install -q -r requirements.txt
mkdir -p data
nohup .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > data/server.log 2>&1 < /dev/null &
for step in {1..30}; do
  if curl --fail --silent --max-time 2 http://127.0.0.1:8000/api/status >/dev/null; then
    echo "ImageForge ready on forwarded port 8000."
    exit 0
  fi
  sleep 1
done
tail -n 30 data/server.log
exit 1
