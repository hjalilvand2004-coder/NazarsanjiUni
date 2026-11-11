#!/bin/bash
# Start all services v3.5.0 — Bahman 1405
set -e
cd "$(dirname "$0")"
echo "============================================"
echo "  Starting All Services v3.5.0"
echo "  Mini App:    http://0.0.0.0:5000"
echo "  Website:     http://0.0.0.0:8080"
echo "  Admin Login: admin / admin@1405"
echo "  Bot:         Bale polling"
echo "============================================"
mkdir -p data
if ! python -c "import flask" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
fi
python miniapp.py &
echo "Mini App started (PID $!)"
sleep 2
python website.py &
echo "Website started (PID $!)"
sleep 2
python bot.py &
echo "Bot started (PID $!)"
echo ""
echo "All services running. Press Ctrl+C to stop."
echo ""
trap "exit" INT TERM
wait
