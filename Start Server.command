#!/bin/bash

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Change to the script directory
cd "$SCRIPT_DIR"

# Clear screen for better visibility
clear

# Check if Python 3 is available
if command -v python3 &> /dev/null; then
    python3 server-files/server.py "$@"
elif command -v python &> /dev/null; then
    python server-files/server.py "$@"
else
    echo "❌ Python not found. Please install Python 3."
    echo ""
    echo "Press any key to exit..."
    read -n 1
    exit 1
fi

