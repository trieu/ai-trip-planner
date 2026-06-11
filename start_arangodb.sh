#!/bin/bash

set -e

# ============================================================
# ArangoDB for LEO CDP test
# How to use: 
#./start_arangodb.sh start
#./start_arangodb.sh restart
#./start_arangodb.sh reset-db
#./start_arangodb.sh import ./data/customers.json cdp_profile
# ============================================================

ARANGODB_IMAGE_NAME="arangodb:latest"
CONTAINER_NAME="arangodb-ce"
NETWORK_NAME="leo-vlan"
VOLUME_NAME="arangodb_data"

ARANGO_ROOT_PASSWORD="12345678"
DB_NAME="leo_cdp_db"

HOST_PORT=8529

# ============================================================
# Helpers
# ============================================================

wait_for_arango() {
    echo "⏳ Waiting for ArangoDB..."

    local max_attempts=30
    local attempt=1

    until docker exec "$CONTAINER_NAME" \
        arangosh \
        --server.endpoint tcp://127.0.0.1:8529 \
        --server.username root \
        --server.password "$ARANGO_ROOT_PASSWORD" \
        --javascript.execute-string "db._version()" \
        >/dev/null 2>&1
    do
        if [ "$attempt" -ge "$max_attempts" ]; then
            echo "❌ ArangoDB not ready"
            exit 1
        fi

        sleep 2
        ((attempt++))
    done

    echo "🟢 ArangoDB ready"
}

ensure_network() {
    docker network inspect "$NETWORK_NAME" >/dev/null 2>&1 \
        || docker network create "$NETWORK_NAME"
}

create_database_if_missing() {

    local EXISTS

    EXISTS=$(docker exec "$CONTAINER_NAME" \
        arangosh \
        --server.username root \
        --server.password "$ARANGO_ROOT_PASSWORD" \
        --javascript.execute-string "
            const dbs=require('@arangodb').db._databases();
            print(dbs.includes('$DB_NAME'));
        " | tail -1)

    if [ "$EXISTS" != "true" ]; then

        echo "🚀 Creating database: $DB_NAME"

        docker exec "$CONTAINER_NAME" \
            arangosh \
            --server.username root \
            --server.password "$ARANGO_ROOT_PASSWORD" \
            --javascript.execute-string "
                require('@arangodb').db._createDatabase('$DB_NAME');
            "
    else
        echo "ℹ️ Database already exists: $DB_NAME"
    fi
}

start_container() {

    ensure_network

    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then

        if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then

            echo "🟢 Container already running"

        else

            echo "🔄 Starting existing container..."
            docker start "$CONTAINER_NAME" >/dev/null

        fi

    else

        echo "🚀 Creating ArangoDB container..."

        docker volume create "$VOLUME_NAME" >/dev/null

        docker run -d \
            --name "$CONTAINER_NAME" \
            --network "$NETWORK_NAME" \
            -p "$HOST_PORT:8529" \
            -e ARANGO_ROOT_PASSWORD="$ARANGO_ROOT_PASSWORD" \
            -v "$VOLUME_NAME:/var/lib/arangodb3" \
            -v "$VOLUME_NAME-apps:/var/lib/arangodb3-apps" \
            --restart unless-stopped \
            $ARANGODB_IMAGE_NAME

    fi

    wait_for_arango
    create_database_if_missing

    echo ""
    echo "✅ ArangoDB Community Edition Ready"
    echo "Database : $DB_NAME"
    echo "Port     : $HOST_PORT"
    echo "URL      : http://localhost:$HOST_PORT"
}

restart_container() {

    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then

        echo "🔄 Restarting ArangoDB..."

        docker restart "$CONTAINER_NAME"

        wait_for_arango

    else
        echo "⚠️ Container does not exist. Starting..."
        start_container
    fi
}

reset_database() {

    echo "⚠️ RESET DATABASE: $DB_NAME"

    start_container

    docker exec "$CONTAINER_NAME" \
        arangosh \
        --server.username root \
        --server.password "$ARANGO_ROOT_PASSWORD" \
        --javascript.execute-string "
            const db=require('@arangodb').db;

            if(db._databases().includes('$DB_NAME')){
                db._dropDatabase('$DB_NAME');
                print('Dropped database');
            }

            db._createDatabase('$DB_NAME');
            print('Created database');
        "

    echo "✅ Database reset completed"
}

import_json() {

    FILE_PATH="$1"
    COLLECTION_NAME="$2"

    if [ -z "$FILE_PATH" ]; then
        echo "❌ Missing JSON file"
        exit 1
    fi

    if [ -z "$COLLECTION_NAME" ]; then
        echo "❌ Missing collection name"
        exit 1
    fi

    if [ ! -f "$FILE_PATH" ]; then
        echo "❌ File not found: $FILE_PATH"
        exit 1
    fi

    start_container

    echo "📦 Importing JSON"

    docker cp "$FILE_PATH" \
        "$CONTAINER_NAME:/tmp/import.json"

    docker exec "$CONTAINER_NAME" \
        arangoimport \
        --server.endpoint tcp://127.0.0.1:8529 \
        --server.username root \
        --server.password "$ARANGO_ROOT_PASSWORD" \
        --server.database "$DB_NAME" \
        --collection "$COLLECTION_NAME" \
        --create-collection true \
        --type json \
        --batch-size 67108864 \
        --file /tmp/import.json

    echo "✅ Import completed"
}

show_help() {

cat <<EOF

Usage:

  ./start_arangodb.sh start
      Start container

  ./start_arangodb.sh restart
      Restart container

  ./start_arangodb.sh reset-db
      Drop and recreate database

  ./start_arangodb.sh import <json_file> <collection>
      Import JSON documents

Examples:

  ./start_arangodb.sh start

  ./start_arangodb.sh restart

  ./start_arangodb.sh reset-db

  ./start_arangodb.sh import ./data/customers.json customers

EOF

}

# ============================================================
# Main
# ============================================================

ACTION="$1"

case "$ACTION" in

    start)
        start_container
        ;;

    restart)
        restart_container
        ;;

    reset-db)
        reset_database
        ;;

    import)
        import_json "$2" "$3"
        ;;

    *)
        show_help
        ;;
esac