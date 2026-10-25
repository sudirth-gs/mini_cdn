"""
origin/app.py
-------------
FastAPI origin server for the mini CDN project.

Responsibilities:
  - Serve static files from the `origin/files/` directory.
  - Expose health-check and statistics endpoints.
  - Read host/port configuration from the shared config.json.
"""

import mimetypes
import json
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response

# ---------------------------------------------------------------------------
# Bootstrap: load configuration
# ---------------------------------------------------------------------------

# Locate config.json relative to the project root (two levels up from this file).
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"

with open(CONFIG_PATH, "r", encoding="utf-8") as _f:
    _config = json.load(_f)

ORIGIN_HOST: str = _config["origin"]["host"]   # e.g. "127.0.0.1"
ORIGIN_PORT: int = _config["origin"]["port"]   # e.g. 8000

# Directory that holds the static files served by this origin.
FILES_DIR = Path(__file__).resolve().parent / "files"

# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Mini CDN — Origin Server")

# In-memory request counter (reset on every restart).
_total_requests: int = 0

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
def health_check() -> dict:
    """
    Simple liveness probe.

    Returns:
        {"status": "ok", "server": "origin"}
    """
    return {"status": "ok", "server": "origin"}


@app.get("/stats")
def stats() -> dict:
    """
    Return runtime statistics for this origin server.

    Returns:
        {"total_requests": <int>, "server": "origin"}
    """
    return {"total_requests": _total_requests, "server": "origin"}


@app.get("/files/{filename}")
def serve_file(filename: str) -> Response:
    """
    Serve a static file from the `origin/files/` directory.

    The Content-Type header is derived from the file extension via the
    standard `mimetypes` module.  If the file does not exist a 404 JSON
    response is returned instead.

    Args:
        filename: Name of the file to serve (e.g. "index.html").

    Returns:
        HTTP 200 with the file content and correct Content-Type, or
        HTTP 404 with a JSON error body.
    """
    global _total_requests

    file_path = FILES_DIR / filename

    # Security: ensure the resolved path stays inside FILES_DIR (no path traversal).
    try:
        file_path = file_path.resolve()
        file_path.relative_to(FILES_DIR.resolve())
    except ValueError:
        return JSONResponse(
            status_code=403,
            content={"error": "Forbidden", "detail": "Access denied."},
        )

    if not file_path.exists() or not file_path.is_file():
        return JSONResponse(
            status_code=404,
            content={"error": "Not Found", "detail": f"File '{filename}' does not exist on this origin."},
        )

    # Increment the global counter *after* the path is confirmed valid.
    _total_requests += 1

    # Determine MIME type; fall back to application/octet-stream if unknown.
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if mime_type is None:
        mime_type = "application/octet-stream"

    content = file_path.read_bytes()
    return Response(content=content, media_type=mime_type)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=ORIGIN_HOST,
        port=ORIGIN_PORT,
        reload=False,
    )
