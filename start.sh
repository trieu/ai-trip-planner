#!/usr/bin/env bash

set -euo pipefail

# ==========================================================
# Project Root
# ==========================================================
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

MODE=${1:-dev} # dev | live | clean-logs | clean-all

case "$MODE" in
clean-logs)
  echo "🧹 Cleaning log files..."

  if [[ -d "backend/logs" ]]; then
    find backend/logs -type f -name "*.log" -delete
    echo "✅ Deleted all log files in backend/logs/"
  elif [[ -d "logs" ]]; then
    find logs -type f -name "*.log" -delete
    echo "✅ Deleted all log files in logs/"
  else
    echo "ℹ️ No logs directory found."
  fi

  exit 0
  ;;

clean-all)
  echo "🧹 Cleaning logs and stopping services..."

  lsof -ti :8888 | xargs kill -9 2>/dev/null || true
  lsof -ti :6006 | xargs kill -9 2>/dev/null || true

  rm -rf backend/logs/*.log 2>/dev/null || true
  rm -rf logs/*.log 2>/dev/null || true

  echo "✅ Cleanup completed."
  exit 0
  ;;
esac

echo "📂 Project Root: $PROJECT_ROOT"

# ==========================================================
# Validate Project Structure
# ==========================================================
if [[ ! -d "$PROJECT_ROOT/backend" ]]; then
  echo "❌ backend/ directory not found"
  exit 1
fi

# ==========================================================
# Backend Directory
# ==========================================================
cd "$PROJECT_ROOT/backend"

# ==========================================================
# Activate Virtual Environment
# ==========================================================
if [[ -f "venv/bin/activate" ]]; then
  echo "🐍 Activating virtual environment..."
  source venv/bin/activate
else
  echo "⚠️ backend/venv/bin/activate not found"
fi

# ==========================================================
# Load Environment Variables FIRST
# ==========================================================
ENV_FILE=".env"

if [[ -f "$ENV_FILE" ]]; then
  echo "📄 Loading environment from $ENV_FILE"

  set -a
  source "$ENV_FILE"
  set +a
else
  echo "⚠️ No .env found"
fi

# ==========================================================
# Defaults
# ==========================================================
HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8888}

PHOENIX_PORT=${PHOENIX_PORT:-6006}
WORKERS=${WORKERS:-4}

PGSQL_DB_HOST=${PGSQL_DB_HOST:-localhost}
PGSQL_DB_PORT=${PGSQL_DB_PORT:-5435}

# ==========================================================
# Timestamp Logs
# ==========================================================
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

LOG_PHOENIX="logs/phoenix_${TIMESTAMP}.log"
LOG_BACKEND="logs/backend_${TIMESTAMP}.log"

# ==========================================================
# PostgreSQL Health Check
# ==========================================================
echo ""
echo "🐘 Checking PostgreSQL..."
echo "Host : $PGSQL_DB_HOST"
echo "Port : $PGSQL_DB_PORT"

if ! nc -z "$PGSQL_DB_HOST" "$PGSQL_DB_PORT" >/dev/null 2>&1; then

  echo "⚠️ PostgreSQL is not reachable"

  START_PGSQL="$PROJECT_ROOT/start_pgsql.sh"

  echo "🔍 Looking for:"
  echo "    $START_PGSQL"

  if [[ -x "$START_PGSQL" ]]; then

    echo "🚀 Starting PostgreSQL Docker..."
    "$START_PGSQL"

  elif [[ -f "$START_PGSQL" ]]; then

    chmod +x "$START_PGSQL"

    echo "🚀 Starting PostgreSQL Docker..."
    "$START_PGSQL"

  else

    echo "❌ start_pgsql.sh not found"
    echo "Expected location:"
    echo "    $START_PGSQL"

    exit 1
  fi

  echo "⏳ Waiting for PostgreSQL..."

  for i in {1..30}; do

    if nc -z "$PGSQL_DB_HOST" "$PGSQL_DB_PORT" >/dev/null 2>&1; then
      echo "✅ PostgreSQL is ready"
      break
    fi

    sleep 2

    if [[ $i -eq 30 ]]; then
      echo "❌ PostgreSQL failed to start"
      exit 1
    fi
  done

else
  echo "✅ PostgreSQL already running"
fi

# ==========================================================
# Clean Ports
# ==========================================================
echo ""
echo "🧹 Cleaning ports..."

lsof -ti :"$PORT" | xargs kill -9 2>/dev/null || true
lsof -ti :"$PHOENIX_PORT" | xargs kill -9 2>/dev/null || true

# ==========================================================
# Logs Directory
# ==========================================================
if [[ -d "logs" ]]; then

  echo "🧹 Removing old log files..."

  find logs -type f -name "*.log" -delete
  find logs -type f -name "*.txt" -delete

else

  mkdir -p logs

fi

echo "✅ Logs ready"

# ==========================================================
# Start Phoenix
# ==========================================================
echo ""
echo "🧠 Starting Phoenix..."

if [[ "$MODE" == "live" ]]; then

  nohup python -m phoenix.server.main serve \
    --port "$PHOENIX_PORT" \
    >>"$LOG_PHOENIX" 2>&1 </dev/null &

else

  python -m phoenix.server.main serve \
    --port "$PHOENIX_PORT" \
    >>"$LOG_PHOENIX" 2>&1 &

fi

PHOENIX_PID=$!

echo "Phoenix PID: $PHOENIX_PID"

# ==========================================================
# Start Backend
# ==========================================================
echo ""
echo "⚡ Starting Backend API..."

if [[ "$MODE" == "live" ]]; then

  echo "🔥 LIVE mode"

  nohup uvicorn main:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers "$WORKERS" \
    --loop uvloop \
    --http httptools \
    >>"$LOG_BACKEND" 2>&1 </dev/null &

else

  echo "🧪 DEV mode"

  uvicorn main:app \
    --host "$HOST" \
    --port "$PORT" \
    --reload \
    >>"$LOG_BACKEND" 2>&1 &

fi

BACKEND_PID=$!

echo "Backend PID: $BACKEND_PID"

# ==========================================================
# Health Check
# ==========================================================
sleep 3

echo ""
echo "🔎 Checking services..."

if ps -p "$BACKEND_PID" >/dev/null; then
  echo "✅ Backend running"
else
  echo "❌ Backend failed"
  echo "Check: backend/$LOG_BACKEND"
fi

if ps -p "$PHOENIX_PID" >/dev/null; then
  echo "✅ Phoenix running"
else
  echo "❌ Phoenix failed"
  echo "Check: backend/$LOG_PHOENIX"
fi

# ==========================================================
# LIVE MODE
# ==========================================================
if [[ "$MODE" == "live" ]]; then

  echo ""
  echo "✅ LIVE environment started"

  echo ""
  echo "🌐 URLs"

  echo "Frontend : http://localhost:$PORT/index.html"
  echo "API      : http://localhost:$PORT/api/v1/trips/plan"
  echo "Docs     : http://localhost:$PORT/docs"
  echo "Phoenix  : http://localhost:$PHOENIX_PORT"

  echo ""
  echo "📄 Logs"

  echo "Backend : backend/$LOG_BACKEND"
  echo "Phoenix : backend/$LOG_PHOENIX"

  echo ""
  echo "🔧 PIDs"

  echo "Backend : $BACKEND_PID"
  echo "Phoenix : $PHOENIX_PID"

  exit 0
fi

# ==========================================================
# DEV MODE
# ==========================================================
echo ""
echo "✅ DEV environment started"

echo ""
echo "🌐 URLs"

echo "Frontend : http://localhost:$PORT/index.html"
echo "API      : http://localhost:$PORT/api/v1/trips/plan"
echo "Docs     : http://localhost:$PORT/docs"
echo "Phoenix  : http://localhost:$PHOENIX_PORT"

echo ""
echo "📄 Logs"

echo "tail -f backend/$LOG_BACKEND"
echo "tail -f backend/$LOG_PHOENIX"

echo ""
echo "🛑 Press Ctrl+C to stop"

cleanup() {

  echo ""
  echo "🛑 Stopping services..."

  kill "$BACKEND_PID" 2>/dev/null || true
  kill "$PHOENIX_PID" 2>/dev/null || true

  wait "$BACKEND_PID" 2>/dev/null || true
  wait "$PHOENIX_PID" 2>/dev/null || true

  echo "✅ All services stopped"

  exit 0
}

trap cleanup SIGINT SIGTERM

wait