#!/bin/bash
set -e

echo "Running database migrations..."
python migrate.py

echo "Starting API server..."
exec uvicorn main:app --host 0.0.0.0 --port 8080
