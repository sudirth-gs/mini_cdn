"""
benchmark.py — Mini CDN Benchmark Script
==========================================
Sends concurrent requests to the CDN router (or a specific edge server)
and prints a detailed performance + cache-hit report.

Usage examples:
    python tests/benchmark.py
    python tests/benchmark.py --requests 100 --files index.html,style.css
    python tests/benchmark.py --target edge-2 --requests 20
"""

import argparse
import asyncio
import json
import time
from collections import defaultdict
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# ANSI colour helpers
# ---------------------------------------------------------------------------

GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def green(text: str)  -> str: return f"{GREEN}{text}{RESET}"
def yellow(text: str) -> str: return f"{YELLOW}{text}{RESET}"
def cyan(text: str)   -> str: return f"{CYAN}{text}{RESET}"
def bold(text: str)   -> str: return f"{BOLD}{text}{RESET}"


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """Load config.json from the project root (parent of the tests/ dir)."""
    config_path = Path(__file__).resolve().parent.parent / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"config.json not found at {config_path}")
    with config_path.open() as f:
        return json.load(f)


def resolve_target_url(config: dict, target: str) -> str:
    """
    Resolve a human-friendly target name ("router", "edge-1", …) to a base URL.

    Falls back to the router URL if the target is not found in edge_servers.
    """
    if target == "router":
        router_cfg = config.get("router", {})
        host = router_cfg.get("host", "localhost")
        port = router_cfg.get("port", 8000)
        return f"http://{host}:{port}"

    # Look for the target in the edge servers list
    for edge in config.get("edge_servers", []):
        if edge["id"] == target:
            # config.json stores host + port, not a pre-built url
            url = edge.get("url") or f"http://{edge['host']}:{edge['port']}"
            return url

    raise ValueError(
        f"Unknown target '{target}'. "
        "Valid values: 'router', 'edge-1', 'edge-2', 'edge-3'."
    )


# ---------------------------------------------------------------------------
# Single-request worker
# ---------------------------------------------------------------------------

async def fetch_file(
    client: httpx.AsyncClient,
    base_url: str,
    filename: str,
) -> dict:
    """
    Fetch one file from base_url/files/<filename>.

    Returns a dict with:
        filename  – the requested filename
        latency   – round-trip time in milliseconds
        status    – HTTP status code
        cache     – value of X-Cache header ("HIT", "MISS", or "UNKNOWN")
        edge_id   – value of X-Edge-ID header
        error     – error message string, or None on success
    """
    url = f"{base_url}/files/{filename}"
    start = time.perf_counter()
    try:
        resp = await client.get(url, timeout=15.0)
        latency_ms = (time.perf_counter() - start) * 1000.0
        return {
            "filename": filename,
            "latency":  round(latency_ms, 2),
            "status":   resp.status_code,
            "cache":    resp.headers.get("X-Cache", "UNKNOWN"),
            "edge_id":  resp.headers.get("X-Edge-ID", "unknown"),
            "error":    None,
        }
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000.0
        return {
            "filename": filename,
            "latency":  round(latency_ms, 2),
            "status":   0,
            "cache":    "ERROR",
            "edge_id":  "unknown",
            "error":    str(exc),
        }


# ---------------------------------------------------------------------------
# ASCII bar chart
# ---------------------------------------------------------------------------

def ascii_bar_chart(latencies: list[float], buckets: int = 8) -> None:
    """
    Print a simple ASCII horizontal bar chart of latency distribution.

    latencies — list of ms values
    buckets   — number of histogram buckets
    """
    if not latencies:
        return

    lo, hi = min(latencies), max(latencies)
    if lo == hi:
        hi = lo + 1  # avoid zero-width range

    step = (hi - lo) / buckets
    counts = [0] * buckets

    for lat in latencies:
        idx = min(int((lat - lo) / step), buckets - 1)
        counts[idx] += 1

    max_count = max(counts) or 1
    bar_width  = 30  # characters for the longest bar

    print(bold("\n  Latency Distribution (ms)"))
    print("  " + "-" * (bar_width + 28))
    for i, count in enumerate(counts):
        bucket_lo = lo + i * step
        bucket_hi = bucket_lo + step
        bar_len   = int(count / max_count * bar_width)
        bar       = "█" * bar_len
        label     = f"  {bucket_lo:6.1f}–{bucket_hi:6.1f} ms"
        print(f"{label} | {cyan(bar):<{bar_width + 9}} {count:>4} req")
    print("  " + "-" * (bar_width + 28))


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

def print_report(
    results: list[dict],
    total_wall_ms: float,
    target: str,
) -> None:
    """Print the full benchmark summary report."""

    total      = len(results)
    errors     = [r for r in results if r["error"]]
    successes  = [r for r in results if not r["error"]]
    hits       = [r for r in successes if r["cache"] == "HIT"]
    misses     = [r for r in successes if r["cache"] == "MISS"]
    latencies  = [r["latency"] for r in successes]

    hit_rate   = len(hits) / total * 100 if total else 0
    avg_lat    = sum(latencies) / len(latencies) if latencies else 0
    min_lat    = min(latencies) if latencies else 0
    max_lat    = max(latencies) if latencies else 0

    # Per-edge breakdown
    edge_counts: dict[str, int] = defaultdict(int)
    for r in successes:
        edge_counts[r["edge_id"]] += 1

    # -----------------------------------------------------------------------
    print()
    print(bold("=" * 60))
    print(bold("  Mini CDN Benchmark Report"))
    print(bold("=" * 60))
    print(f"  Target           : {bold(target)}")
    print(f"  Total requests   : {bold(str(total))}")
    print(f"  Successful       : {bold(str(len(successes)))}")
    print(f"  Errors           : {bold(str(len(errors)))}")
    print(f"  Total wall time  : {bold(f'{total_wall_ms:.1f} ms')}")
    print()

    print(bold("  Cache Performance"))
    print(f"  Cache HIT rate   : {green(f'{hit_rate:.1f}%')}  ({len(hits)} hits / {len(misses)} misses)")
    print()

    print(bold("  Latency (ms)"))
    print(f"  Average          : {avg_lat:.2f} ms")
    print(f"  Minimum          : {min_lat:.2f} ms")
    print(f"  Maximum          : {max_lat:.2f} ms")
    print()

    print(bold("  Requests per Edge"))
    for edge_id, count in sorted(edge_counts.items()):
        print(f"  {edge_id:<12} : {count} requests")
    print()

    # Per-request detail (first 20 to keep output tidy)
    print(bold("  Per-Request Detail (first 20)"))
    print(f"  {'#':<5} {'File':<20} {'Status':<8} {'Cache':<10} {'Edge':<12} {'Latency':>10}")
    print("  " + "-" * 70)
    for i, r in enumerate(results[:20]):
        cache_label = (
            green("HIT")  if r["cache"] == "HIT"
            else yellow("MISS") if r["cache"] == "MISS"
            else r["cache"]
        )
        print(
            f"  {i+1:<5} {r['filename']:<20} {r['status']:<8} "
            f"{cache_label:<19} {r['edge_id']:<12} {r['latency']:>8.2f} ms"
        )
    if len(results) > 20:
        print(f"  ... and {len(results) - 20} more requests")

    # ASCII latency chart
    ascii_bar_chart(latencies)
    print(bold("=" * 60))
    print()


# ---------------------------------------------------------------------------
# Main benchmark runner
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mini CDN benchmark: send concurrent requests and report stats."
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=50,
        metavar="N",
        help="Total number of requests to send (default: 50).",
    )
    parser.add_argument(
        "--files",
        type=str,
        default="index.html,style.css,script.js,about.html",
        help=(
            "Comma-separated list of filenames to request "
            "(default: index.html,style.css,script.js,about.html)."
        ),
    )
    parser.add_argument(
        "--target",
        type=str,
        default="router",
        help=(
            "Which server to hit: 'router' (default) or an edge id "
            "like 'edge-1', 'edge-2', 'edge-3'."
        ),
    )
    args = parser.parse_args()

    # Parse file list
    file_list = [f.strip() for f in args.files.split(",") if f.strip()]
    if not file_list:
        print("Error: --files must contain at least one filename.")
        return

    # Load config and resolve target URL
    config = load_config()
    try:
        base_url = resolve_target_url(config, args.target)
    except ValueError as exc:
        print(f"Error: {exc}")
        return

    total_requests = args.requests
    print(bold(f"\nMini CDN Benchmark"))
    print(f"  Target : {base_url}")
    print(f"  Files  : {', '.join(file_list)}")
    print(f"  Total  : {total_requests} requests\n")
    print("  Sending requests…", end="", flush=True)

    # Build the request list by cycling through filenames
    request_list: list[str] = []
    for i in range(total_requests):
        request_list.append(file_list[i % len(file_list)])

    # Fire all requests concurrently
    wall_start = time.perf_counter()
    async with httpx.AsyncClient() as client:
        tasks = [fetch_file(client, base_url, fname) for fname in request_list]
        results = await asyncio.gather(*tasks)
    wall_ms = (time.perf_counter() - wall_start) * 1000.0

    print(f" done ({wall_ms:.0f} ms total)\n")

    print_report(list(results), wall_ms, args.target)


if __name__ == "__main__":
    asyncio.run(main())
