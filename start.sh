#!/usr/bin/env bash

set -euo pipefail

MODE=${1:-dev}  # dev | live

echo "🚀 Starting Environment (mode: $MODE)..."

# ==========================================================
# 0. Validate project structure
# ==========================================================
if [[ ! -d "backend" ]]; then
  echo "❌ Error: backend/ not found. Run from project root."
  exit 1
fi

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

# ==========================================================
# 2. Defaults
# ==========================================================
HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8000}
PHOENIX_PORT=${PHOENIX_PORT:-6006}
WORKERS=${WORKERS:-4}

# ==========================================================
# 3. Kill existing processes on port (important for live)
# ==========================================================
echo "🧹 Cleaning ports..."
lsof -ti :$PORT | xargs kill -9 2>/dev/null || true
lsof -ti :$PHOENIX_PORT | xargs kill -9 2>/dev/null || true

# ==========================================================
# 4. Ensure logs directory exists
# ==========================================================
if [ ! -d "logs" ]; then
  mkdir "logs"
  echo "✅ Created 'logs' directory"
else
  echo "ℹ️  'logs' directory already exists"
fi

# ==========================================================
# 5. Start Phoenix
# ==========================================================
echo "🧠 Starting Phoenix..."
python -m phoenix.server.main serve \
  --port "$PHOENIX_PORT" \
  > logs/phoenix.log 2>&1 &

PHOENIX_PID=$!
echo "Phoenix PID: $PHOENIX_PID"

# ==========================================================
# 6. Start Backend
# ==========================================================
echo "⚡ Starting Backend API..."

if [[ "$MODE" == "live" ]]; then
  echo "🔥 Running in LIVE mode (no reload, multi-worker)"

  uvicorn main:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers "$WORKERS" \
    --loop uvloop \
    --http httptools \
    > logs/backend.log 2>&1 &

else
  echo "🧪 Running in DEV mode (reload enabled)"

  uvicorn main:app \
    --host "$HOST" \
    --port "$PORT" \
    --reload \
    > logs/backend.log 2>&1 &
fi

BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# ==========================================================
# 7. Health Check
# ==========================================================
sleep 2

echo ""
echo "🔎 Checking services..."

if ps -p $BACKEND_PID > /dev/null; then
  echo "✅ Backend running"
else
  echo "❌ Backend failed (check logs/backend.log)"
fi

if ps -p $PHOENIX_PID > /dev/null; then
  echo "✅ Phoenix running"
else
  echo "❌ Phoenix failed (check logs/phoenix.log)"
fi

echo ""
echo "🌐 URLs:"
echo "  API:       http://localhost:$PORT"
echo "  Phoenix:   http://localhost:$PHOENIX_PORT"
echo ""

echo "📄 Logs:"
echo "  tail -f backend/logs/backend.log"
echo "  tail -f backend/logs/phoenix.log"
echo ""

echo "🛑 Press Ctrl+C to stop all services"

# ==========================================================
# 8. Cleanup
# ==========================================================
cleanup() {
  echo ""
  echo "🛑 Stopping services..."

  kill $BACKEND_PID 2>/dev/null || true
  kill $PHOENIX_PID 2>/dev/null || true

  wait $BACKEND_PID 2>/dev/null || true
  wait $PHOENIX_PID 2>/dev/null || true

  echo "✅ All services stopped."
  exit 0
}

trap cleanup SIGINT SIGTERM

# ==========================================================
# 9. Wait
# ==========================================================
wait