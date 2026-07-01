#!/bin/bash
sleep 3
kill "$1"
cd "$(dirname "$0")"
git pull
source .venv/bin/activate
python app.py
