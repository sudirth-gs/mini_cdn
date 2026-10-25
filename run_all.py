"""
run_all.py — Launch and manage all Mini-CDN servers and dashboard in one command.

Usage:
    python run_all.py

Features:
    - Frees ports (8000, 8001, 8002, 8003, 9000, 5500) if occupied by stale processes
    - Starts Origin server (port 8000)
    - Starts Edge-1 (port 8001, US-East, 10ms)
    - Starts Edge-2 (port 8002, EU-West, 25ms)
    - Starts Edge-3 (port 8003, AP-South, 50ms)
    - Starts Router (port 9000)
    - Starts Dashboard HTTP server (port 5500)
    - Opens dashboard automatically in default web browser
    - Gracefully stops all processes on Ctrl+C
"""

import os
import sys
import time
import signal
import socket
import webbrowser
import subprocess
from pathlib import Path

# Fix Windows console encoding for Unicode output
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).resolve().parent

SERVICES = [
    {
        "name": "Origin Server",
        "port": 8000,
        "cmd": [sys.executable, str(BASE_DIR / "origin" / "app.py")],
        "cwd": str(BASE_DIR / "origin"),
    },
    {
        "name": "Edge 1 (US-East 10ms)",
        "port": 8001,
        "cmd": [sys.executable, str(BASE_DIR / "edge" / "edge_server.py"), "--edge-id", "edge-1"],
        "cwd": str(BASE_DIR / "edge"),
    },
    {
        "name": "Edge 2 (EU-West 25ms)",
        "port": 8002,
        "cmd": [sys.executable, str(BASE_DIR / "edge" / "edge_server.py"), "--edge-id", "edge-2"],
        "cwd": str(BASE_DIR / "edge"),
    },
    {
        "name": "Edge 3 (AP-South 50ms)",
        "port": 8003,
        "cmd": [sys.executable, str(BASE_DIR / "edge" / "edge_server.py"), "--edge-id", "edge-3"],
        "cwd": str(BASE_DIR / "edge"),
    },
    {
        "name": "Load Balancer Router",
        "port": 9000,
        "cmd": [sys.executable, str(BASE_DIR / "router" / "load_balancer.py")],
        "cwd": str(BASE_DIR / "router"),
    },
    {
        "name": "Dashboard Server",
        "port": 5000,
        "cmd": [sys.executable, "-m", "http.server", "5000", "--bind", "127.0.0.1"],
        "cwd": str(BASE_DIR / "dashboard"),
    },
]

def free_port_windows(port: int):
    """Find and terminate any process listening on the given port (Windows)."""
    try:
        output = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True, text=True)
        for line in output.strip().splitlines():
            parts = line.split()
            if len(parts) >= 5 and "LISTENING" in line:
                pid = parts[-1]
                if pid != str(os.getpid()):
                    subprocess.run(f"taskkill /PID {pid} /F", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def wait_for_port(port: int, timeout: float = 8.0) -> bool:
    """Poll until a local port is accepting connections."""
    start = time.time()
    while time.time() - start < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.2)
    return False

def main():
    print("=" * 60)
    print("🚀 Starting Mini CDN Environment...")
    print("=" * 60)

    # Clean up any stale process occupying our ports
    print("[*] Checking and freeing ports...")
    for svc in SERVICES:
        free_port_windows(svc["port"])
    time.sleep(0.5)

    processes = []

    def cleanup(*args):
        print("\n\n🛑 Shutting down all Mini CDN services...")
        for name, proc in reversed(processes):
            if proc.poll() is None:
                print(f"    Stopping {name} (PID {proc.pid})...")
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
        print("✅ All services stopped. Goodbye!")
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # Launch background processes
    for svc in SERVICES:
        print(f"[*] Starting {svc['name']} on port {svc['port']}...")
        proc = subprocess.Popen(
            svc["cmd"],
            cwd=svc["cwd"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        processes.append((svc["name"], proc))
        
        if not wait_for_port(svc["port"], timeout=6.0):
            print(f"⚠️  Warning: {svc['name']} did not open port {svc['port']} within timeout.")

    print("\n" + "=" * 60)
    print("✨ ALL SERVICES ARE LIVE!")
    print("=" * 60)
    print("  • Origin Server:    http://127.0.0.1:8000")
    print("  • Edge 1 (US-East): http://127.0.0.1:8001")
    print("  • Edge 2 (EU-West): http://127.0.0.1:8002")
    print("  • Edge 3 (AP-South):http://127.0.0.1:8003")
    print("  • Router (LB):      http://127.0.0.1:9000")
    print("  • Dashboard:        http://127.0.0.1:5000")
    print("=" * 60)
    print("Press Ctrl+C to terminate all services.\n")

    # Open Dashboard in default browser
    try:
        webbrowser.open("http://127.0.0.1:5000")
    except Exception:
        pass

    # Keep alive and monitor child processes
    try:
        while True:
            for name, proc in processes:
                code = proc.poll()
                if code is not None:
                    print(f"❌ Error: {name} exited unexpectedly with code {code}.")
                    cleanup()
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()

if __name__ == "__main__":
    main()
