# Mini CDN — Technical Documentation

## Architecture Overview

This mini CDN consists of four main components:

### 1. Origin Server (Port 8000)
The authoritative source of all content. Files stored here are the
"ground truth" that edge servers cache.

### 2. Edge Servers (Ports 8001–8003)
Caching proxy nodes deployed in different simulated regions:
- **Edge 1** — US-East (10ms latency)
- **Edge 2** — EU-West (25ms latency)
- **Edge 3** — AP-South (50ms latency)

Each edge maintains an in-memory cache with a configurable TTL.

### 3. Router / Load Balancer (Port 9000)
Distributes incoming requests across edge servers using round-robin.

### 4. Dashboard (Port 5000)
Real-time monitoring UI showing cache performance and request flow.

## Cache Behavior

```
Request → Router → Edge Server
                     ├── Cache HIT  → Return cached content (fast!)
                     └── Cache MISS → Fetch from Origin → Cache it → Return
```

**TTL (Time-To-Live):** 30 seconds by default.
After TTL expires, the cached entry is considered stale and will be
re-fetched from origin on the next request.

## HTTP Headers

| Header | Example | Description |
|--------|---------|-------------|
| X-Cache | HIT / MISS | Whether content was served from cache |
| X-Edge-ID | edge-1 | Which edge server handled the request |
| X-Latency-Simulated | 10ms | Simulated regional network delay |
| X-Router | mini-cdn-router | Added by the load balancer |

## Performance Tips

1. Request the same file multiple times to see cache HITs
2. Wait 30+ seconds and request again to see TTL expiry
3. Use the dashboard to invalidate files and observe MISSes
4. Compare latency between edge-1 (10ms) and edge-3 (50ms)
