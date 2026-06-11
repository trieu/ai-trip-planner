#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

PYTHON_BIN="${PYTHON_BIN:-python3.10}"
VENV_DIR="venv"

echo "================================================="
echo " Python Environment Bootstrap"
echo "================================================="

# -------------------------------------------------
# Verify Python 3.10 exists
# -------------------------------------------------

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "ERROR: ${PYTHON_BIN} not found"
    echo ""
    echo "Install it first:"
    echo "sudo apt update"
    echo "sudo apt install python3.10 python3.10-venv"
    exit 1
fi

echo "Using Python:"
"${PYTHON_BIN}" --version

# -------------------------------------------------
# Recreate venv if built with wrong Python version
# -------------------------------------------------

if [ -d "${VENV_DIR}" ]; then

    if [ -f "${VENV_DIR}/bin/python" ]; then

        VENV_VERSION="$(
            "${VENV_DIR}/bin/python" -c \
            'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
        )"

        if [ "${VENV_VERSION}" != "3.10" ]; then
            echo "Removing old venv (Python ${VENV_VERSION})..."
            rm -rf "${VENV_DIR}"
        fi
    fi
fi

# -------------------------------------------------
# Create virtual environment
# -------------------------------------------------

if [ ! -d "${VENV_DIR}" ]; then
    echo "Creating virtual environment..."
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

# -------------------------------------------------
# Activate
# -------------------------------------------------

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

echo "Virtual Environment:"
python --version

# -------------------------------------------------
# Upgrade tooling
# -------------------------------------------------

python -m pip install \
    --upgrade \
    pip \
    setuptools \
    wheel

# -------------------------------------------------
# Install dependencies
# -------------------------------------------------

if [ -f requirements.txt ]; then

    echo "Installing dependencies..."

    pip install \
        --upgrade \
        -r requirements.txt

else

    echo "WARNING: requirements.txt not found"

fi

# -------------------------------------------------
# Generate lock file
# -------------------------------------------------

echo "Generating lock file..."

pip freeze \
    | sort \
    > requirements.lock.txt

echo ""
echo "SUCCESS"
echo "Python : $(python --version)"
echo "Venv   : ${SCRIPT_DIR}/${VENV_DIR}"
echo "Lock   : requirements.lock.txt"