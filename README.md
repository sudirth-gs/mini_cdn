# 🌐 Mini CDN — Computer Networks Project

A fully interactive, simulated **Content Delivery Network (CDN)** built with **FastAPI**, **Python**, and **vanilla JavaScript**. 

Designed for demonstration and coursework in **Computer Networks**, this project provides a hands-on visualization of how modern CDNs distribute load, cache content, handle TTL expiration, simulate geographic network latencies, and optimize delivery over HTTP.

---

## 📌 Architecture Overview

```text
                                 +-----------------------+
                                 |        Client         |
                                 | (Browser / Dashboard) |
                                 +-----------+-----------+
                                             |
                                             | HTTP GET
                                             v
                                 +-----------------------+
                                 |  Router / LB (:9000)  |
                                 |      Round-Robin      |
                                 +-----------+-----------+
                                             |
             +-------------------------------+-------------------------------+
             |                               |                               |
             v                               v                               v
+-------------------------+     +-------------------------+     +-------------------------+
|     Edge Server 1       |     |     Edge Server 2       |     |     Edge Server 3       |
|    Port: 8001 (10ms)    |     |    Port: 8002 (25ms)    |     |    Port: 8003 (50ms)    |
|    Region: US-East      |     |    Region: EU-West      |     |    Region: AP-South     |
|  [ In-Memory Cache ]    |     |  [ In-Memory Cache ]    |     |  [ In-Memory Cache ]    |
+------------+------------+     +------------+------------+     +------------+------------+
             |                               |                               |
             +-------------------------------+-------------------------------+
                                             |
                                             | Cache MISS (Fetch & Store)
                                             v
                                 +-----------------------+
                                 | Origin Server (:8000) |
                                 |   Authoritative Hub   |
                                 +-----------------------+
```

---

## ✨ Key Features & Concepts Demonstrated

1. **Edge Caching & Cache Hits/Misses**:
   - On the first request to an edge, a **Cache MISS** occurs: the edge fetches the file from the Origin Server, saves it to its local in-memory cache, and returns it.
   - Subsequent requests within the TTL window result in a **Cache HIT**: content is served instantly without reaching the Origin.
2. **Time-To-Live (TTL) & Expiration**:
   - Configurable TTL (default: 30 seconds). Stale cache entries expire automatically.
3. **Simulated Regional Latencies**:
   - Demonstrates physical distance and network propagation delay:
     - **Edge 1 (US-East)**: `10ms` simulated delay
     - **Edge 2 (EU-West)**: `25ms` simulated delay
     - **Edge 3 (AP-South)**: `50ms` simulated delay
4. **Round-Robin Load Balancing**:
   - The router evenly distributes incoming client requests across active edge nodes.
5. **Cache Invalidation & Purge**:
   - Broadcast cache evictions to a single file or purge all nodes in parallel (`POST /invalidate/{filename}`, `POST /invalidate-all`).
6. **Live Interactive Dashboard**:
   - SVG network topology with dynamic path animations and packet tracing.
   - Real-time narration explaining every step of the request lifecycle.
   - Live edge metrics, hit rate progress bars, and cached asset badges.
7. **Performance Benchmarking**:
   - Asynchronous CLI testing tool (`tests/benchmark.py`) with concurrent request generation and ASCII latency distribution histograms.

---

## 📂 Project Directory Structure

```text
mini_cdn/
├── config.json              # Central topology, port, TTL, and latency configuration
├── run_all.py               # Orchestrator script to clean ports & run all services
├── start.bat                # Windows double-click launcher
├── README.md                # Project documentation
├── .gitignore               # Standard Git ignore rules
│
├── origin/
│   ├── app.py               # Authoritative FastAPI Origin Server (Port 8000)
│   └── files/               # Static repository of 16 sample assets
│       ├── index.html, about.html, blog.html, gallery.html, stats.html, contact.html, 404.html
│       ├── style.css, theme-dark.css
│       ├── script.js, app.js
│       ├── api.json, data.json, analytics.csv
│       └── docs.md, robots.txt
│
├── edge/
│   └── edge_server.py       # FastAPI Edge Server with local cache & latency simulation
│
├── router/
│   └── load_balancer.py     # Round-Robin reverse proxy router with CORS support
│
├── dashboard/               # Interactive monitoring frontend (Port 5000)
│   ├── index.html           # Dashboard UI with SVG topology
│   ├── style.css            # Dark mode styles & animations
│   └── script.js            # Real-time polling & topology animation engine
│
└── tests/
    └── benchmark.py         # Concurrent async performance benchmark tool
```

---

## 🚀 Getting Started

### 1. Prerequisites & Dependencies

Python 3.10+ is recommended. Install required packages:

```bash
pip install fastapi uvicorn httpx
```

### 2. Run All Services with One Command

Run the orchestrator:

```powershell
python run_all.py
```
*(Or simply double-click `start.bat` on Windows)*

The launcher will:
- Automatically check and free any stale processes on ports `8000`, `8001`, `8002`, `8003`, `9000`, and `5000`.
- Spin up the Origin, 3 Edge servers, the Router, and the Dashboard web server.
- Open the interactive dashboard in your default browser at **http://127.0.0.1:5000**.
- Gracefully shut down all background processes when you press `Ctrl + C`.

---

## 🧪 Testing & Verification

### Web UI
1. Navigate to **http://127.0.0.1:5000**.
2. Select any file from the dropdown (e.g. `index.html` or `api.json`) and click **"▶ Send Request"**.
3. Watch the SVG topology trace the packet:
   - **MISS**: Client → Router → Edge → Origin → Edge → Client (Orange/Blue).
   - **HIT**: Client → Router → Edge → Client (Green/Blue).
4. Click **"⚡ Send 10 Requests"** (Burst Mode) to see the load balancer cycle edges and watch hit rates climb.
5. Invalidate files or purge caches using the **Cache Control** buttons.

### Command Line (cURL)

Inspect headers directly:
```bash
# First request -> Cache MISS
curl -i http://127.0.0.1:9000/files/index.html

# Second request within 30s -> Cache HIT
curl -i http://127.0.0.1:9000/files/index.html
```

Notice the custom response headers:
```http
HTTP/1.1 200 OK
content-type: text/html; charset=utf-8
x-cache: HIT
x-edge-id: edge-1
x-latency-simulated: 10ms
x-router: mini-cdn-router
```

### Automated Benchmark Tool

Execute concurrent load tests:
```powershell
cd tests
python benchmark.py --requests 100 --target router
```

Output includes:
- Total execution time and requests per second.
- Cache hit rate percentage.
- Min / Max / Average latency.
- Per-edge traffic distribution.
- ASCII latency distribution bar chart.

---

## ⚙️ Configuration Reference (`config.json`)

All topology parameters are declared centrally:

```json
{
  "origin": {
    "host": "127.0.0.1",
    "port": 8000
  },
  "edge_servers": [
    { "id": "edge-1", "host": "127.0.0.1", "port": 8001, "latency_ms": 10, "region": "US-East" },
    { "id": "edge-2", "host": "127.0.0.1", "port": 8002, "latency_ms": 25, "region": "EU-West" },
    { "id": "edge-3", "host": "127.0.0.1", "port": 8003, "latency_ms": 50, "region": "AP-South" }
  ],
  "router": {
    "host": "127.0.0.1",
    "port": 9000,
    "strategy": "round-robin"
  },
  "cache": {
    "ttl_seconds": 30,
    "max_size_mb": 50
  },
  "dashboard": {
    "host": "127.0.0.1",
    "port": 5000
  }
}
```

---

## 🎓 Academic Takeaways

- **Latency Reduction**: Demonstrates why caching closer to end users reduces round-trip times (RTT).
- **Origin Offloading**: Highlights how edge nodes absorb traffic and protect origin infrastructure from high request volumes.
- **Cache Coherency**: Explores TTL expiration tradeoffs and the need for invalidation broadcasts.
- **Layer 7 Load Balancing**: Demonstrates HTTP reverse proxying and request forwarding with header preservation.
