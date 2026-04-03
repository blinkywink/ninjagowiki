# Local Server Setup

This directory contains a custom local web server for running the website.

## Quick Start

### macOS (Double-click method)
1. Double-click `Start Server.command`
2. If macOS shows a security warning, go to System Settings → Privacy & Security → click "Open Anyway"
3. The server will start in a Terminal window

### macOS/Linux (Terminal method)
```bash
./server-files/serve.sh
```

### Windows
```bash
python server-files/server.py
```

## Features

- ✅ Serves your website exactly like a web host
- ✅ Proper 404 page handling (serves `404.html` for missing pages)
- ✅ Easy reload: Type `1` or `r` and press Enter to reload
- ✅ Works from any directory location (fully portable)

## Usage

**Start the server:**
- Default port: `8000`
- Custom port: `./server-files/serve.sh 3000` or `python server-files/server.py 3000`

**While server is running:**
- Type `1` or `r` + Enter = Reload server
- Type `q` or `quit` + Enter = Stop server
- Press `Ctrl+C` = Stop server

**Access your site:**
- Open browser to: `http://localhost:8000` (or your custom port)

## Requirements

- Python 3 (usually pre-installed on macOS/Linux)
- All files must stay in the same directory structure

## Sharing

You can copy this entire directory anywhere and it will work! The server automatically detects its location and serves files from its directory.

