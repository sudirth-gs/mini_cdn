"""
load_balancer.py — Mini CDN Router / Load Balancer
=====================================================
Sits in front of the 3 edge servers and distributes client requests
using a round-robin strategy.

Run:
    uvicorn router.load_balancer:app --port 8000 --reload
or via the __main__ block:
    python router/load_balancer.py
"""

import asyncio
import json
import threading
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Bootstrap — locate config.json (walk up from this file's directory)
# ---------------------------------------------------------------------------

def _find_config() -> Path:
    """Walk up the directory tree from this file until config.json is found."""
    candidate = Path(__file__).resolve().parent
    for _ in range(5):  # search at most 5 levels up
        cfg = candidate / "config.json"
        if cfg.exists():
            return cfg
        candidate = candidate.parent
    raise FileNotFoundError(
        "config.json not found in any ancestor of the router directory."
    )


_config_path = _find_config()
with _config_path.open() as _f:
    _config = json.load(_f)

# Edge servers come from config.json under the "edge_servers" key.
# Each entry has host + port; we build a "url" field for convenience.
EDGE_SERVERS: list[dict] = _config["edge_servers"]
for _e in EDGE_SERVERS:
    if "url" not in _e:
        _e["url"] = f"http://{_e['host']}:{_e['port']}"
ROUTER_PORT: int = _config.get("router", {}).get("port", 8000)
TIMEOUT: float = _config.get("router", {}).get("timeout_seconds", 10.0)

# ---------------------------------------------------------------------------
# Round-robin counter (thread-safe, works for async too since GIL protects
# simple integer reads; we add a threading.Lock for explicit safety)
# ---------------------------------------------------------------------------

_rr_lock = threading.Lock()
_rr_index = 0  # mutable state protected by _rr_lock


def _next_edge() -> dict:
    """Return the next edge server dict in round-robin order."""
    global _rr_index
    with _rr_lock:
        edge = EDGE_SERVERS[_rr_index % len(EDGE_SERVERS)]
        _rr_index += 1
    return edge


# ---------------------------------------------------------------------------
# Stats (simple in-memory counters)
# ---------------------------------------------------------------------------

router_stats: dict = {
    "total_requests": 0,
    "requests_per_edge": {e["id"]: 0 for e in EDGE_SERVERS},
    "strategy": "round-robin",
}

_stats_lock = threading.Lock()


def _record_request(edge_id: str) -> None:
    """Increment in-memory counters for a completed proxy request."""
    with _stats_lock:
        router_stats["total_requests"] += 1
        router_stats["requests_per_edge"][edge_id] = (
            router_stats["requests_per_edge"].get(edge_id, 0) + 1
        )


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Mini CDN Router",
    description="Round-robin load balancer for the mini CDN edge servers.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Cache", "X-Edge-ID", "X-Router", "X-Latency-Simulated", "Content-Type"],
)


# ---------------------------------------------------------------------------
# Helper: fetch a single edge's /stats (used by GET /stats)
# ---------------------------------------------------------------------------

async def _fetch_edge_stats(client: httpx.AsyncClient, edge: dict) -> dict:
    """
    Attempt to GET /stats from the given edge server.
    Returns the parsed JSON dict, or {"error": "unreachable"} on failure.
    """
    try:
        url = f"{edge['url']}/stats"
        resp = await client.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {"error": "unreachable"}


# ---------------------------------------------------------------------------
# Helper: POST invalidation to a single edge
# ---------------------------------------------------------------------------

async def _post_invalidate(
    client: httpx.AsyncClient, edge: dict, path: str
) -> dict:
    """
    POST to /invalidate/<path> on one edge.
    Returns the edge id and either the JSON body or an error marker.
    """
    try:
        url = f"{edge['url']}/{path}"
        resp = await client.post(url, timeout=TIMEOUT)
        resp.raise_for_status()
        return {"edge_id": edge["id"], "result": resp.json()}
    except Exception as exc:
        return {"edge_id": edge["id"], "error": str(exc)}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/files/{filename}", summary="Proxy file request to an edge (round-robin)")
async def proxy_file(filename: str, request: Request):
    """
    Pick the next edge server in round-robin order, forward the file
    request to it, and stream the response back to the client.

    Preserved response headers: X-Cache, X-Edge-ID, Content-Type.
    Added response header: X-Router: mini-cdn-router.
    """
    edge = _next_edge()
    target_url = f"{edge['url']}/files/{filename}"

    async with httpx.AsyncClient() as client:
        try:
            edge_resp = await client.get(target_url, timeout=TIMEOUT)
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Edge server '{edge['id']}' unreachable: {exc}",
            )

    # Record stats after a successful (or at least attempted) forwarding
    _record_request(edge["id"])

    # Build the response, forwarding only safe/relevant headers
    headers_to_forward = {
        "X-Cache": edge_resp.headers.get("X-Cache", "UNKNOWN"),
        "X-Edge-ID": edge_resp.headers.get("X-Edge-ID", edge["id"]),
        "Content-Type": edge_resp.headers.get("Content-Type", "application/octet-stream"),
        "X-Router": "mini-cdn-router",
    }

    return Response(
        content=edge_resp.content,
        status_code=edge_resp.status_code,
        headers=headers_to_forward,
    )


@app.get("/stats", summary="Aggregated stats from router + all edges")
async def get_stats():
    """
    Return the router's own statistics merged with stats fetched from
    every edge server.  Parallel requests are made via asyncio.gather so
    a slow / unreachable edge doesn't block the others.
    """
    async with httpx.AsyncClient() as client:
        edge_stat_tasks = [
            _fetch_edge_stats(client, edge) for edge in EDGE_SERVERS
        ]
        edge_results = await asyncio.gather(*edge_stat_tasks)

    edge_stats_map = {
        EDGE_SERVERS[i]["id"]: edge_results[i]
        for i in range(len(EDGE_SERVERS))
    }

    return JSONResponse(
        content={
            "total_requests": router_stats["total_requests"],
            "requests_per_edge": router_stats["requests_per_edge"],
            "strategy": router_stats["strategy"],
            "edge_stats": edge_stats_map,
            "router": router_stats,
            "edges": edge_stats_map,
        }
    )


@app.get("/health", summary="Router health check")
async def health():
    """Simple liveness check — always returns 200 if the router is running."""
    return {"status": "ok", "server": "router", "strategy": "round-robin"}


@app.post("/invalidate/{filename}", summary="Broadcast cache invalidation for one file")
async def invalidate_file(filename: str):
    """
    Broadcast a POST /invalidate/<filename> to ALL edge servers in parallel.
    Returns a per-edge result map so the caller can see which edges acknowledged.
    """
    async with httpx.AsyncClient() as client:
        tasks = [
            _post_invalidate(client, edge, f"invalidate/{filename}")
            for edge in EDGE_SERVERS
        ]
        results = await asyncio.gather(*tasks)

    return {
        "filename": filename,
        "invalidated_on": results,
    }


@app.post("/invalidate-all", summary="Broadcast full cache flush to all edges")
async def invalidate_all():
    """
    Broadcast a POST /invalidate-all to every edge server in parallel.
    Useful for flushing the entire cache after a content deployment.
    """
    async with httpx.AsyncClient() as client:
        tasks = [
            _post_invalidate(client, edge, "invalidate-all")
            for edge in EDGE_SERVERS
        ]
        results = await asyncio.gather(*tasks)

    return {"invalidated_on": results}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "load_balancer:app",
        host="0.0.0.0",
        port=ROUTER_PORT,
        reload=False,
        log_level="info",
    )
