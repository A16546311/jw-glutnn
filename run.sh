#!/usr/bin/env bash
cd /home/wsl/jw-shell || exit 1
exec .venv/bin/python app.py >>/tmp/jw.log 2>&1
