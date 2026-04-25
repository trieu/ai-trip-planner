#!/bin/bash

# Unit Test Startup Script

echo "🚀 Starting Unit Tests..."

# Check if we're in the right directory
if [ ! -d "backend" ] || [ ! -d "frontend" ]; then
    echo "❌ Error: Please run this script from the trip_planner directory"
    exit 1
fi

# Navigate to the backend directory to run tests
cd backend

# Set PYTHONPATH to include the current directory for imports
export PYTHONPATH=.

# Run pytest with verbose output
pytest -v