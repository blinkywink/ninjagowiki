#!/bin/bash

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

cd "$SCRIPT_DIR"

# Check if Python 3 is available
if command -v python3 &> /dev/null; then
    python3 server.py "$@"
elif command -v python &> /dev/null; then
    python server.py "$@"
else
    echo "❌ Python not found. Please install Python 3."
    exit 1
fi

