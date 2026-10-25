# 🌐 Mini CDN — Computer Networks Project

A simulated Content Delivery Network (CDN) built with FastAPI and Python, demonstrating core CDN concepts: edge caching, cache TTL/invalidation, load balancing, and latency simulation.

---

## Architecture

```
Client
  │
  ▼
Router / Load Balancer  (port 9000)   ← round-robin across edges
  │           │           │
  ▼           ▼           ▼
Edge-1      Edge-2      Edge-3        ← caching layer (ports 8001–8003)
(10ms)      (25ms)      (50ms)        ← simulated latency per region
  │           │           │
  └─────┬─────┘           │
        └──────────────┬──┘
                       ▼
               Origin Server          (port 8000)  ← actual file storage
```

## Components

| File | Role |
|---|---|
| `config.json` | Central config — ports, TTL, latency, edge count |
| `origin/app.py` | Origin server — serves files from `origin/files/` |
| `edge/edge_server.py` | Edge server — caches files, simulates latency |
| `router/load_balancer.py` | Router — round-robin load balancer |
| `dashboard/` | Real-time monitoring dashboard |
| `tests/benchmark.py` | Performance benchmarking script |

## Key Concepts Demonstrated

- **Cache Hit/Miss** — edge serves from cache vs. fetches from origin
- **TTL (Time-To-Live)** — cached entries expire after 30 seconds
- **Cache Invalidation** — manually evict files from edge caches
- **Simulated Latency** — each edge has a regional delay (10/25/50ms)
- **Round-Robin Load Balancing** — router cycles evenly across 3 edges
- **Parallel Stats Aggregation** — router collects stats from all edges concurrently

## Setup

```bash
pip install fastapi uvicorn httpx
```

## Running the Project

Open **5 terminals**:

```bash
# Terminal 1 — Origin Server
cd origin
python app.py

# Terminal 2 — Edge Server 1 (US-East, 10ms)
cd edge
python edge_server.py --edge-id edge-1

# Terminal 3 — Edge Server 2 (EU-West, 25ms)
cd edge
python edge_server.py --edge-id edge-2

# Terminal 4 — Edge Server 3 (AP-South, 50ms)
cd edge
python edge_server.py --edge-id edge-3

# Terminal 5 — Router
cd router
python load_balancer.py
```

Then open `dashboard/index.html` in your browser.

## Testing

```bash
# Basic request (goes through router → edge → origin on first request)
curl http://127.0.0.1:9000/files/index.html

# Check cache headers
curl -I http://127.0.0.1:9000/files/index.html
# X-Cache: MISS (first request)
# X-Cache: HIT  (subsequent requests within TTL)

# Run benchmark
cd tests
python benchmark.py --requests 100

# View stats
curl http://127.0.0.1:9000/stats

# Invalidate a file from all edges
curl -X POST http://127.0.0.1:9000/invalidate/index.html
```

## Response Headers

Every response includes:
- `X-Cache: HIT` or `X-Cache: MISS`
- `X-Edge-ID: edge-1` (which edge served the request)
- `X-Latency-Simulated: 10ms` (simulated regional delay)
- `X-Router: mini-cdn-router` (added by the router)

## Config Reference (`config.json`)

```json
{
  "cache": { "ttl_seconds": 30 },
  "edge_servers": [
    { "latency_ms": 10 }
  ]
}
```
