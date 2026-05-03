#!/bin/bash

# ============================================================
# PostgreSQL 16 + PostGIS + pgvector + Apache AGE
# Schema Database for LEO Activation with Marketing Event + AI Embedding Pipeline + Knowledge Graph
# ============================================================

# --- Docker configs ---
CONTAINER_NAME="pgsql16_vector_age" # Updated name to reflect AGE
VLAN_NAME="leo-vlan"
DATA_VOLUME="pgdata_vector_age"

# --- POSTGRES config ---
POSTGRES_USER="postgres"
POSTGRES_PASSWORD="12345678"
DEFAULT_DB="postgres"
TARGET_DB="leo_activation_db"
HOST_PORT=5435

# --- SQL schema config ---
SCHEMA_VERSION=260503
SCHEMA_DESCRIPTION="init core DB schema + AI embedding pipeline"
SQL_FILE_PATH="./database/knowledge_schema.sql"

# --- Parse options ---
RESET_DB=false
for arg in "$@"; do
  case $arg in
    --reset-db)
      RESET_DB=true
      shift
      ;;
  esac
done

# ============================================================
# Helper: wait for PostgreSQL
# ============================================================
wait_for_postgres() {
  local max_attempts=15
  local attempt=1
  echo "⏳ Waiting for PostgreSQL..."
  until docker exec -u postgres "$CONTAINER_NAME" psql -d "$DEFAULT_DB" -c "SELECT 1;" >/dev/null 2>&1; do
    if [ $attempt -ge $max_attempts ]; then
      echo "❌ PostgreSQL not ready"
      exit 1
    fi
    sleep 3
    ((attempt++))
  done
  echo "🟢 PostgreSQL ready."
}

# ============================================================
# Start or create container
# ============================================================
# Ensure network exists
docker network inspect "$VLAN_NAME" >/dev/null 2>&1 || docker network create "$VLAN_NAME"

if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "🔄 Starting existing container..."
    docker start "$CONTAINER_NAME"
    wait_for_postgres
  else
    echo "🟢 Container already running."
    wait_for_postgres
  fi
else
  echo "🚀 Creating new container..."
  docker volume create "$DATA_VOLUME" >/dev/null 2>&1

  # Note: We cannot set shared_preload_libraries here yet because AGE isn't installed.
  docker run -d \
    --name "$CONTAINER_NAME" \
    --network "$VLAN_NAME" \
    -e POSTGRES_USER="$POSTGRES_USER" \
    -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
    -e POSTGRES_DB="$DEFAULT_DB" \
    -p "$HOST_PORT:5432" \
    -v "$DATA_VOLUME:/var/lib/postgresql/data" \
    postgis/postgis:16-3.5
    
  wait_for_postgres

  # ============================================================
  # Install pgvector AND Apache AGE
  # ============================================================
  echo "📦 Installing extensions (pgvector & age)..."
  docker exec -u root "$CONTAINER_NAME" bash -c \
    "apt-get update && apt-get install -y postgresql-16-pgvector postgresql-16-age"
  
  # ============================================================
  # Configure AGE (Requires Restart)
  # ============================================================
  echo "🔧 Configuring shared_preload_libraries for AGE..."
  docker exec -u postgres "$CONTAINER_NAME" psql -c \
    "ALTER SYSTEM SET shared_preload_libraries = 'age';"
  
  echo "🔄 Restarting container to apply configuration..."
  docker restart "$CONTAINER_NAME"
  wait_for_postgres
fi

# ============================================================
# Fix collation mismatches (Docker + Debian issue)
# ============================================================
docker exec -u postgres "$CONTAINER_NAME" psql -d postgres \
  -c "ALTER DATABASE postgres REFRESH COLLATION VERSION;" >/dev/null 2>&1 || true

docker exec -u postgres "$CONTAINER_NAME" psql -d template1 \
  -c "ALTER DATABASE template1 REFRESH COLLATION VERSION;" >/dev/null 2>&1 || true

# ============================================================
# Reset DB if requested
# ============================================================
if [ "$RESET_DB" = true ]; then
  echo "⚠️ Dropping database $TARGET_DB..."
  docker exec -u postgres "$CONTAINER_NAME" psql -d postgres \
    -c "DROP DATABASE IF EXISTS ${TARGET_DB};"
fi

# ============================================================
# Create DB if missing
# ============================================================
DB_EXISTS=$(docker exec -u postgres "$CONTAINER_NAME" psql -d postgres -t \
  -c "SELECT 1 FROM pg_database WHERE datname='${TARGET_DB}';" | tr -d '[:space:]')

if [ "$DB_EXISTS" != "1" ]; then
  echo "🚀 Creating database $TARGET_DB..."
  docker exec -u postgres "$CONTAINER_NAME" psql -d postgres \
    -c "CREATE DATABASE ${TARGET_DB};"
fi

# ============================================================
# Enable required extensions (LEO Activation schema)
# ============================================================
echo "🔌 Enabling PostgreSQL extensions..."

docker exec -u postgres "$CONTAINER_NAME" psql -d "$TARGET_DB" -c \
  "CREATE EXTENSION IF NOT EXISTS pgcrypto;"

docker exec -u postgres "$CONTAINER_NAME" psql -d "$TARGET_DB" -c \
  "CREATE EXTENSION IF NOT EXISTS vector;"

docker exec -u postgres "$CONTAINER_NAME" psql -d "$TARGET_DB" -c \
  "CREATE EXTENSION IF NOT EXISTS citext;"

docker exec -u postgres "$CONTAINER_NAME" psql -d "$TARGET_DB" -c \
  "CREATE EXTENSION IF NOT EXISTS age;"

docker exec -u postgres "$CONTAINER_NAME" psql -d "$TARGET_DB" -c \
  "CREATE EXTENSION IF NOT EXISTS postgis;"


# ============================================================
# Configure Search Path for AGE (Critical)
# ============================================================
# AGE requires ag_catalog in the search path to function
echo "🔧 Setting search_path for AGE..."
docker exec -u postgres "$CONTAINER_NAME" psql -d "$TARGET_DB" -c \
  "ALTER DATABASE ${TARGET_DB} SET search_path = ag_catalog, \"\$user\", public;"

# ============================================================
# Schema migration table
# ============================================================
docker exec -u postgres "$CONTAINER_NAME" psql -d "$TARGET_DB" -c "
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TIMESTAMPTZ DEFAULT now(),
  description TEXT
);
"

CURRENT_VERSION=$(docker exec -u postgres "$CONTAINER_NAME" psql -d "$TARGET_DB" -t \
  -c "SELECT COALESCE(MAX(version),0) FROM schema_migrations;" | tr -d '[:space:]')

# ============================================================
# Apply migration if needed
# ============================================================
if [ "$CURRENT_VERSION" -lt "$SCHEMA_VERSION" ]; then
  echo "🚀 Applying migration $SCHEMA_VERSION..."
  if [ -f "$SQL_FILE_PATH" ]; then
    docker exec -i -u postgres "$CONTAINER_NAME" psql -d "$TARGET_DB" \
      < "$SQL_FILE_PATH" || exit 1

    docker exec -u postgres "$CONTAINER_NAME" psql -d "$TARGET_DB" -c "
      INSERT INTO schema_migrations (version, description)
      VALUES ($SCHEMA_VERSION, '$SCHEMA_DESCRIPTION');
    "
  else
    echo "⚠️ Warning: SQL file not found at $SQL_FILE_PATH"
  fi
else
  echo "ℹ️ Schema already up to date"
fi

# ============================================================
# Verify critical tables (marketing + AI)
# ============================================================
# ============================================================
# Verify critical tables (LEO Activation: Marketing + AI + System)
# Database: PostgreSQL 16+
# ============================================================

TABLES=(
  # --- Core / Tenant ---
  tenant

  # --- CDP ---
  cdp_profiles
  consent_management

  # --- Campaign & Marketing ---
  campaign
  marketing_event
  message_templates
  activation_experiments

  # --- Segmentation ---
  segment_snapshot
  segment_snapshot_member

  # --- Alert Center / Market Data ---
  instruments
  market_snapshot
  alert_rules
  news_feed

  # --- AI / Agent ---
  agent_task
  embedding_job

  # --- Execution / Delivery ---
  delivery_log
  activation_outcomes

  # --- Behavioral Feedback Loop ---
  behavioral_events
  event_metrics

  # --- Recommendations ---
  product_recommendations

  # --- Data Lineage / System ---
  data_sources
  schema_migrations
)

# Note: ag_catalog tables (ag_graph, ag_label) exist but are hidden in ag_catalog schema

echo "🔍 Verifying all tables in $TARGET_DB..."
for table in "${TABLES[@]}"; do
  echo "Verifying table: $table"
  docker exec -u postgres "$CONTAINER_NAME" psql -d "$TARGET_DB" -tc \
    "SELECT 1 FROM pg_tables WHERE tablename='$table';" | grep -q 1 \
    || { echo "❌ Missing table: $table (Check schema.sql)"; }
done

# ============================================================
# Restart policy
# ============================================================
docker update --restart unless-stopped "$CONTAINER_NAME" >/dev/null

echo "✅ Marketing Event DB upgrade completed"
echo "   DB: $TARGET_DB"
echo "   Schema version: $SCHEMA_VERSION"
echo "   Extensions: postgis, vector, age"
echo "   Search Path: ag_catalog, \$user, public"
echo "   Port: $HOST_PORT"