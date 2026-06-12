#!/usr/bin/env bash

set -euo pipefail

MODE=${1:-dev}  # dev | live | clean-logs | clean-all

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

# Generate a timestamp for this specific run to keep a history of logs
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_PHOENIX="logs/phoenix_${TIMESTAMP}.log"
LOG_BACKEND="logs/backend_${TIMESTAMP}.log"

# ==========================================================
# 1. Ensure PostgreSQL is running
# Reads PGSQL_DB_HOST and PGSQL_DB_PORT from backend/.env.
# If PostgreSQL is not reachable, automatically starts the
# Docker container using ./start_pgsql.sh
# ==========================================================

PGSQL_DB_HOST=${PGSQL_DB_HOST:-localhost}
PGSQL_DB_PORT=${PGSQL_DB_PORT:-5435}

echo "🐘 Checking PostgreSQL: ${PGSQL_DB_HOST}:${PGSQL_DB_PORT}"

if ! nc -z "$PGSQL_DB_HOST" "$PGSQL_DB_PORT" >/dev/null 2>&1; then
  echo "⚠️ PostgreSQL is not reachable."

  echo "🚀 Starting PostgreSQL Docker..."

  cd ..

  if [[ -x "./start_pgsql.sh" ]]; then
    ./start_pgsql.sh
  elif [[ -f "./start_pgsql.sh" ]]; then
    chmod +x ./start_pgsql.sh
    ./start_pgsql.sh
  else
    echo "❌ start_pgsql.sh not found."
    exit 1
  fi

  echo "⏳ Waiting for PostgreSQL to become available..."

  for i in {1..30}; do
    if nc -z "$PGSQL_DB_HOST" "$PGSQL_DB_PORT" >/dev/null 2>&1; then
      echo "✅ PostgreSQL is ready."
      break
    fi

    sleep 2

    if [[ $i -eq 30 ]]; then
      echo "❌ PostgreSQL failed to start."
      exit 1
    fi
  done

  cd backend
else
  echo "✅ PostgreSQL already running."
fi

echo "🚀 Starting Backend Environment (mode: $MODE)..."
echo "🕒 Start time: $(date)"

# ==========================================================
# 2. Validate project structure
# Ensures the script is run from the root of the project 
# so that all relative paths (like 'cd backend') work correctly.
# ==========================================================
if [[ ! -d "backend" ]]; then
  echo "❌ Error: backend/ not found. Run from project root."
  exit 1
fi

cd backend
export PYTHONPATH=.

# ==========================================================
# 3. Activate Virtual Environment
# Isolates project dependencies. If the user runs the script 
# from a fresh terminal, the python packages installed in 
# 'venv' need to be active for the backend and Phoenix to run.
# ==========================================================
if [[ -f "venv/bin/activate" ]]; then
  echo "🐍 Activating virtual environment..."
  source venv/bin/activate
else
  echo "⚠️  Warning: backend/venv/bin/activate not found."
  echo "   Make sure you ran: python -m venv venv"
fi

# ==========================================================
# 4. Load .env
# Loads environment variables (like API keys, database URLs) 
# from the .env file so they are available to the backend.
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
# 5. Defaults
# Sets fallback values for critical variables if they were 
# not defined in the system or the .env file.
# ==========================================================
HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8888}
PHOENIX_PORT=${PHOENIX_PORT:-6006}
WORKERS=${WORKERS:-4}

# ==========================================================
# 6. Kill existing processes on port
# Prevents "Address already in use" errors by forcibly 
# closing any zombie processes still clinging to our ports 
# from a previous run or crash.
# ==========================================================
echo "🧹 Cleaning ports..."
lsof -ti :$PORT | xargs kill -9 2>/dev/null || true
lsof -ti :$PHOENIX_PORT | xargs kill -9 2>/dev/null || true

# ==========================================================
# 7. Ensure logs directory exists and clean old logs
# ==========================================================
if [ -d "logs" ]; then
  echo "🧹 Removing old log files..."

  find logs -type f -name "*.log" -delete
  find logs -type f -name "*.txt" -delete

  echo "✅ Old log files removed"
else
  mkdir -p logs
  echo "✅ Created 'logs' directory"
fi

# ==========================================================
# 8. Start Phoenix
# Boots up the Phoenix observability/tracing server in the 
# background (&) and pipes its output to a timestamped log.
# ==========================================================
echo "🧠 Starting Phoenix..."

if [[ "$MODE" == "live" ]]; then
  nohup python -m phoenix.server.main serve \
    --port "$PHOENIX_PORT" \
    >> "$LOG_PHOENIX" 2>&1 < /dev/null &
else
  python -m phoenix.server.main serve \
    --port "$PHOENIX_PORT" \
    >> "$LOG_PHOENIX" 2>&1 &
fi

PHOENIX_PID=$!
echo "Phoenix PID: $PHOENIX_PID"

# ==========================================================
# 9. Start Backend
# Boots up the main API. If in 'live' mode, it optimizes for 
# performance (multiple workers, uvloop). If in 'dev' mode, 
# it enables hot-reloading so code changes apply instantly.
# ==========================================================
echo "⚡ Starting Backend API..."

if [[ "$MODE" == "live" ]]; then
  echo "🔥 Running in LIVE mode (multi-worker, detached)"

  nohup uvicorn main:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers "$WORKERS" \
    --loop uvloop \
    --http httptools \
    >> "$LOG_BACKEND" 2>&1 < /dev/null &

else
  echo "🧪 Running in DEV mode (reload enabled)"

  uvicorn main:app \
    --host "$HOST" \
    --port "$PORT" \
    --reload \
    >> "$LOG_BACKEND" 2>&1 &
fi

BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# ==========================================================
# 10. Health Check
# Waits briefly for servers to boot, then verifies the Process 
# IDs (PIDs) are still running and didn't crash immediately.
# ==========================================================
sleep 2

echo ""
echo "🔎 Checking services..."

if ps -p $BACKEND_PID > /dev/null; then
  echo "✅ Backend running"
else
  echo "❌ Backend failed (check backend/$LOG_BACKEND)"
fi

if ps -p $PHOENIX_PID > /dev/null; then
  echo "✅ Phoenix running"
else
  echo "❌ Phoenix failed (check backend/$LOG_PHOENIX)"
fi



# ==========================================================
# 11. Runtime Mode Handling
# ==========================================================

# ==========================================================
# If in 'live' mode, we detach from the terminal and print out
# all the URLs, log file locations, and PIDs for the user to
# monitor the services independently. The script then exits, but
# the backend and Phoenix continue running in the background.
# ==========================================================

if [[ "$MODE" == "live" ]]; then
  echo ""
  echo "✅ LIVE environment started successfully"
  echo ""
  echo "🌐 URLs:"
  echo "  Frontend:  http://localhost:$PORT/index.html"
  echo "  API:       http://localhost:$PORT/api/v1/trips/plan"
  echo "  Docs:      http://localhost:$PORT/docs"
  echo "  Phoenix:   http://localhost:$PHOENIX_PORT"
  echo ""
  echo "📄 Log Files:"
  echo "  Backend: backend/$LOG_BACKEND"
  echo "  Phoenix: backend/$LOG_PHOENIX"
  echo ""
  echo "🔧 PIDs:"
  echo "  Backend: $BACKEND_PID"
  echo "  Phoenix: $PHOENIX_PID"
  echo ""
  echo "🚀 Services are running in background."

  exit 0
fi

# ==========================================================
# DEV MODE ONLY
# Keep process attached to terminal so Ctrl+C can stop
# everything gracefully.
# ==========================================================

# Outputs the exact URLs and the specific timestamped log commands
echo "✅ DEV environment started successfully"
echo ""
echo "🌐 URLs:"
echo "  Frontend:  http://localhost:$PORT/index.html"
echo "  API:       http://localhost:$PORT/api/v1/trips/plan"
echo "  Docs:      http://localhost:$PORT/docs"
echo "  Phoenix:   http://localhost:$PHOENIX_PORT"
echo ""

echo "📄 Current Run Logs (run in another terminal):"
echo "  tail -f backend/$LOG_BACKEND"
echo "  tail -f backend/$LOG_PHOENIX"
echo ""
echo "🛑 Press Ctrl+C to stop all services"

cleanup() {
  echo ""
  echo "🛑 Stopping dev services..."

  kill "$BACKEND_PID" 2>/dev/null || true
  kill "$PHOENIX_PID" 2>/dev/null || true

  wait "$BACKEND_PID" 2>/dev/null || true
  wait "$PHOENIX_PID" 2>/dev/null || true

  echo "✅ All dev services stopped."
  exit 0
}

trap cleanup SIGINT SIGTERM

wait