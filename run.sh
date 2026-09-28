#!/usr/bin/env bash
cd /home/wsl/jw-shell || exit 1
exec .venv/bin/gunicorn -b 0.0.0.0:8000 -w 1 -k gthread --threads 8 app:app >>/tmp/jw.log 2>&1
