#!/usr/bin/env python3
"""
Custom HTTP server with 404 handling and reload functionality
"""

import http.server
import socketserver
import os
import sys
import threading
import signal
import time
from urllib.parse import unquote

PORT = 8000
if len(sys.argv) > 1:
    try:
        PORT = int(sys.argv[1])
    except ValueError:
        print("Invalid port number, using default 8000")

class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Custom request handler that serves 404.html for missing pages"""
    
    def __init__(self, *args, **kwargs):
        # Serve from parent directory (website root), not from server-files folder
        script_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(script_dir)
        super().__init__(*args, directory=parent_dir, **kwargs)
    
    def end_headers(self):
        """Add no-cache headers for development"""
        # Disable caching for all files during development
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()
    
    def do_GET(self):
        # Parse the path
        raw_path = self.path.split('?')[0]  # Remove query string
        # Decode URL-encoded characters so spaces and other symbols map to real files
        path = unquote(raw_path)
        
        # Handle root
        if path == '/':
            path = '/index.html'
        
        # Remove leading slash for file system
        file_path = path.lstrip('/')
        
        # If path ends with /, try index.html
        if file_path.endswith('/'):
            file_path = file_path + 'index.html'
        
        # Check if file exists
        full_path = os.path.join(self.directory, file_path)
        
        # Normalize path to prevent directory traversal
        full_path = os.path.normpath(full_path)
        if not full_path.startswith(os.path.normpath(self.directory)):
            self.send_error(403, "Forbidden")
            return
        
        if os.path.isfile(full_path):
            # File exists, serve it normally
            super().do_GET()
        elif os.path.isdir(full_path):
            # Directory exists, try index.html
            index_path = os.path.join(full_path, 'index.html')
            if os.path.isfile(index_path):
                self.path = path.rstrip('/') + '/index.html'
                super().do_GET()
            else:
                self.send_404()
        else:
            # File doesn't exist, serve 404.html
            self.send_404()
    
    
    def send_404(self):
        """Serve 404.html for missing pages"""
        error_path = os.path.join(self.directory, '404.html')
        if os.path.isfile(error_path):
            try:
                with open(error_path, 'rb') as f:
                    content = f.read()
                self.send_response(404)
                self.send_header('Content-type', 'text/html')
                self.send_header('Content-length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_error(404, f"File not found: {self.path}")
        else:
            self.send_error(404, f"File not found: {self.path}")
    
    def log_message(self, format, *args):
        """Custom log format"""
        print(f"[{self.log_date_time_string()}] {format % args}")

# Global server instance and control flags
httpd = None
should_reload = False
should_quit = False
reload_lock = threading.Lock()

def start_server():
    """Start the HTTP server"""
    global httpd, should_reload, should_quit
    
    while True:
        try:
            # Allow address reuse for quick restarts
            socketserver.TCPServer.allow_reuse_address = True
            
            httpd = socketserver.TCPServer(("", PORT), CustomHTTPRequestHandler)
            
            print(f"\n{'='*70}")
            print(f"🚀 Server started successfully!")
            print(f"{'='*70}")
            print(f"📍 Server running at: http://localhost:{PORT}")
            script_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(script_dir)
            print(f"📁 Serving from: {parent_dir}")
            print(f"{'='*70}")
            print(f"\n💡 Type '1' or 'r' and press Enter to reload the server")
            print(f"💡 Press Ctrl+C to stop the server\n")
            print(f"{'='*70}\n")
            
            # Serve in a separate thread so we can control it
            server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            server_thread.start()
            
            # Wait for reload or quit signal
            while server_thread.is_alive():
                with reload_lock:
                    if should_reload:
                        should_reload = False
                        print("\n🔄 Reloading server...")
                        httpd.shutdown()
                        httpd.server_close()
                        # Wait for server thread to finish
                        server_thread.join(timeout=2)
                        print("✅ Server stopped. Restarting...\n")
                        break  # Break inner loop to restart server
                    if should_quit:
                        httpd.shutdown()
                        httpd.server_close()
                        server_thread.join(timeout=2)
                        return  # Exit function completely
                
                # Small delay to avoid busy waiting
                time.sleep(0.1)
            
            # If we get here and should_quit is True, exit
            with reload_lock:
                if should_quit:
                    return
                
        except OSError as e:
            if e.errno == 48:  # Address already in use
                print(f"❌ Port {PORT} is already in use. Try a different port.")
            else:
                print(f"❌ Error starting server: {e}")
            sys.exit(1)
        except KeyboardInterrupt:
            print("\n\n👋 Shutting down server...")
            if httpd:
                httpd.shutdown()
            sys.exit(0)

def input_handler():
    """Handle user input in a separate thread"""
    global should_reload, should_quit
    while True:
        try:
            user_input = input().strip().lower()
            with reload_lock:
                if user_input in ['1', 'r', 'reload', 'restart']:
                    should_reload = True
                elif user_input in ['q', 'quit', 'exit']:
                    should_quit = True
                    print("\n👋 Shutting down server...")
        except (EOFError, KeyboardInterrupt):
            with reload_lock:
                should_quit = True
            break
        except Exception as e:
            print(f"Error handling input: {e}")

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    global should_quit
    print("\n\n👋 Shutting down server...")
    with reload_lock:
        should_quit = True
    if httpd:
        httpd.shutdown()
    sys.exit(0)

if __name__ == "__main__":
    # Set up signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    # Start input handler in a separate thread
    input_thread = threading.Thread(target=input_handler, daemon=True)
    input_thread.start()
    
    # Start the server
    start_server()

