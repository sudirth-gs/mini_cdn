"""
edge_server.py — FastAPI edge server for the mini CDN project.

Each edge server instance acts as a caching proxy between the client and the
origin server.  Multiple instances can be launched with different --edge-id
values (e.g. edge-1, edge-2, edge-3); each reads its own host/port/latency
from config.json.

Usage:
    python edge_server.py --edge-id edge-1
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

# ---------------------------------------------------------------------------
# Bootstrap: parse --edge-id early so the app can be configured at import time
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments.  Called once at module level."""
    parser = argparse.ArgumentParser(description="Mini-CDN edge server")
    parser.add_argument(
        "--edge-id",
        required=True,
        help="Identifier for this edge node (e.g. edge-1).  Must match an "
             "entry in config.json.",
    )
    return parser.parse_args()


def _find_config() -> Path:
    """Return the path to config.json, searching parent directories."""
    here = Path(__file__).resolve().parent
    for directory in [here, *here.parents]:
        candidate = directory / "config.json"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "config.json not found in any parent directory of edge_server.py"
    )


def _load_config(edge_id: str) -> dict:
    """
    Load config.json and extract the settings relevant to *this* edge node.

    Returns a dict with keys:
        edge_id, region, host, port, latency_ms, origin_url, ttl_seconds
    """
    config_path = _find_config()
    with config_path.open() as fh:
        config = json.load(fh)

    # Find the edge entry whose id matches the supplied --edge-id argument.
    # config.json uses the key "edge_servers" for the list of edge nodes.
    edge_cfg = None
    for entry in config.get("edge_servers", []):
        if entry["id"] == edge_id:
            edge_cfg = entry
            break

    if edge_cfg is None:
        raise ValueError(
            f"Edge ID '{edge_id}' not found in config.json.  "
            f"Available IDs: {[e['id'] for e in config.get('edge_servers', [])]}"
        )

    # Build the origin URL from host + port (config.json has no "url" key).
    origin_host = config["origin"]["host"]
    origin_port = config["origin"]["port"]
    origin_url: str = f"http://{origin_host}:{origin_port}"
    ttl_seconds: int = config["cache"]["ttl_seconds"]

    return {
        "edge_id": edge_cfg["id"],
        "region": edge_cfg.get("region", "unknown"),
        "host": edge_cfg.get("host", "0.0.0.0"),
        "port": int(edge_cfg.get("port", 8001)),
        "latency_ms": int(edge_cfg.get("latency_ms", 0)),
        "origin_url": origin_url,
        "ttl_seconds": ttl_seconds,
    }


# Parse CLI args and load config at module level so that FastAPI can reference
# them when building routes.  When the module is imported (e.g. during testing)
# without the expected arguments, we fall back gracefully.
try:
    _args = _parse_args()
    CFG = _load_config(_args.edge_id)
except (SystemExit, ValueError, FileNotFoundError) as _exc:
    # Allows the module to be imported without crashing (useful for tests).
    CFG = {
        "edge_id": "unknown",
        "region": "unknown",
        "host": "0.0.0.0",
        "port": 8001,
        "latency_ms": 0,
        "origin_url": "http://localhost:8000",
        "ttl_seconds": 60,
    }

# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------

# Structure: { filename: {"content": bytes, "content_type": str,
#                         "cached_at": float, "hits": int} }
cache: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# In-memory stats
# ---------------------------------------------------------------------------

stats: dict = {
    "edge_id": CFG["edge_id"],
    "region": CFG["region"],
    "total_requests": 0,
    "cache_hits": 0,
    "cache_misses": 0,
    "latency_ms": CFG["latency_ms"],
}

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Mini-CDN Edge Server",
    description="Caching proxy edge node for the mini CDN project.",
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _is_cached(filename: str) -> bool:
    """Return True if *filename* is in the cache and its TTL has not expired."""
    if filename not in cache:
        return False
    age = time.time() - cache[filename]["cached_at"]
    return age < CFG["ttl_seconds"]


def _ttl_remaining(filename: str) -> float:
    """Return seconds remaining before the cached entry for *filename* expires."""
    if filename not in cache:
        return 0.0
    age = time.time() - cache[filename]["cached_at"]
    return max(0.0, CFG["ttl_seconds"] - age)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/files/{filename}", summary="Serve a file (cache-first)")
async def serve_file(filename: str) -> Response:
    """
    Main serving endpoint.

    1. Simulate network latency (asyncio.sleep).
    2. Check in-memory cache; return cached bytes on HIT.
    3. On MISS, fetch from the origin server, populate cache, and return.

    Response headers added:
        X-Cache              : HIT | MISS
        X-Edge-ID            : <edge_id>
        X-Latency-Simulated  : <latency_ms>ms
    """
    # Simulate edge-server network latency.
    if CFG["latency_ms"] > 0:
        await asyncio.sleep(CFG["latency_ms"] / 1000)

    stats["total_requests"] += 1

    # Common response headers present on every reply.
    base_headers = {
        "X-Edge-ID": CFG["edge_id"],
        "X-Latency-Simulated": f"{CFG['latency_ms']}ms",
    }

    # ---- Cache HIT ----
    if _is_cached(filename):
        entry = cache[filename]
        entry["hits"] += 1
        stats["cache_hits"] += 1

        return Response(
            content=entry["content"],
            media_type=entry["content_type"],
            headers={**base_headers, "X-Cache": "HIT"},
        )

    # ---- Cache MISS — fetch from origin ----
    stats["cache_misses"] += 1
    origin_url = f"{CFG['origin_url']}/files/{filename}"

    async with httpx.AsyncClient() as client:
        try:
            origin_resp = await client.get(origin_url)
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to reach origin server: {exc}",
            ) from exc

    if origin_resp.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail=f"File '{filename}' not found on origin.",
        )

    if origin_resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Origin returned unexpected status {origin_resp.status_code}.",
        )

    # Preserve the Content-Type returned by the origin so the client receives
    # the same MIME type as if it had contacted the origin directly.
    content_type: str = origin_resp.headers.get(
        "content-type", "application/octet-stream"
    )
    content: bytes = origin_resp.content

    # Populate the cache entry for subsequent requests.
    cache[filename] = {
        "content": content,
        "content_type": content_type,
        "cached_at": time.time(),
        "hits": 0,
    }

    return Response(
        content=content,
        media_type=content_type,
        headers={**base_headers, "X-Cache": "MISS"},
    )


@app.get("/health", summary="Health check")
async def health() -> dict:
    """Return a simple liveness response indicating the server is running."""
    return {
        "status": "ok",
        "edge_id": CFG["edge_id"],
        "region": CFG["region"],
    }


@app.get("/stats", summary="Cache and request statistics")
async def get_stats() -> dict:
    """
    Return the current stats dict enriched with:
        - cache_size   : number of non-expired files currently in cache
        - cached_files : list of {filename, hits, ttl_remaining_seconds}
    """
    cached_files = [
        {
            "filename": fname,
            "hits": entry["hits"],
            "ttl_remaining_seconds": round(_ttl_remaining(fname), 2),
        }
        for fname, entry in cache.items()
        if _is_cached(fname)  # omit stale entries from the listing
    ]

    return {
        **stats,
        "cache_size": len(cached_files),
        "cached_files": cached_files,
    }


@app.post("/invalidate/{filename}", summary="Invalidate a single cached file")
async def invalidate(filename: str) -> dict:
    """
    Remove *filename* from the in-memory cache.

    Raises 404 if the file is not currently cached (even if it exists on the
    origin), because there is nothing to invalidate locally.
    """
    if filename not in cache:
        raise HTTPException(
            status_code=404,
            detail=f"File '{filename}' is not in the cache.",
        )
    del cache[filename]
    return {"invalidated": filename}


@app.post("/invalidate-all", summary="Clear the entire cache")
async def invalidate_all() -> dict:
    """Remove every entry from the in-memory cache."""
    count = len(cache)
    cache.clear()
    return {"invalidated_count": count}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Re-parse args to get the validated edge-id for this process.
    args = _parse_args()
    cfg = _load_config(args.edge_id)

    print(
        f"Starting edge server '{cfg['edge_id']}' "
        f"(region={cfg['region']}) on {cfg['host']}:{cfg['port']} "
        f"with {cfg['latency_ms']}ms simulated latency …"
    )

    uvicorn.run(
        "edge_server:app",
        host=cfg["host"],
        port=cfg["port"],
        reload=False,
    )
