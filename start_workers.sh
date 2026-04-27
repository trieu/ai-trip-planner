#!/usr/bin/env bash

set -euo pipefail

echo "🚀 Starting Dramatiq (production mode)..."

cd backend
export PYTHONPATH=.

# ==========================================================
# 1. Load .env
# ==========================================================
ENV_FILE=".env"

if [[ -f "$ENV_FILE" ]]; then
  echo "📄 Loading environment from $ENV_FILE"
  set -a
  source "$ENV_FILE"
  set +a
else
  echo "⚠️  No .env file found. Using defaults."
fi

dramatiq tasks.agent_tasks \
  --processes 4 \
  --threads 8 \
  --watch tasks