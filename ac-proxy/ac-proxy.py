from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

DEFAULT_UPSTREAM_URL = "https://api.openai.com/v1"


def configured_upstream_url(value: str | None) -> str:
    candidate = (value or DEFAULT_UPSTREAM_URL).strip().rstrip("/")
    try:
        parsed = httpx.URL(candidate)
    except httpx.InvalidURL as error:
        raise RuntimeError("UPSTREAM_URL must be a valid HTTP or HTTPS URL") from error
    if parsed.scheme not in {"http", "https"} or not parsed.host:
        raise RuntimeError("UPSTREAM_URL must be a valid HTTP or HTTPS URL")
    return candidate


UPSTREAM_URL = configured_upstream_url(os.getenv("UPSTREAM_URL"))
LOG_FILE = os.getenv("LLM_LOG_FILE", "./log")
HOP_BY_HOP_HEADERS = {
    "connection",
    "content-length",
    "host",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "proxy-connection",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}

logger = logging.getLogger("llm-audit")
logger.setLevel(logging.INFO)
logger.propagate = False


class PrivateRotatingFileHandler(RotatingFileHandler):
    """Keep the active audit log private after every rollover."""

    def _open(self):
        flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
        descriptor = os.open(self.baseFilename, flags, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            return open(
                descriptor,
                self.mode,
                encoding=self.encoding,
                errors=self.errors,
            )
        except Exception:
            os.close(descriptor)
            raise


for existing_handler in logger.handlers[:]:
    logger.removeHandler(existing_handler)
    existing_handler.close()

if LOG_FILE:
    log_path = Path(LOG_FILE).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    file_handler = PrivateRotatingFileHandler(
        log_path,
        maxBytes=25 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    os.chmod(log_path, 0o600)
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(file_handler)
else:
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(stdout_handler)


def filtered_headers(raw_headers: list[tuple[bytes, bytes]]) -> list[tuple[bytes, bytes]]:
    """Remove fixed and Connection-nominated hop-by-hop headers."""

    blocked = set(HOP_BY_HOP_HEADERS)
    for key, value in raw_headers:
        if key.lower() != b"connection":
            continue
        blocked.update(
            token.strip().lower()
            for token in value.decode("latin-1").split(",")
            if token.strip()
        )

    return [
        (key.lower(), value)
        for key, value in raw_headers
        if key.decode("latin-1").lower() not in blocked
    ]


def upstream_request_url(request: Request) -> str:
    """Preserve percent-encoding in paths and query strings when available."""

    raw_path = request.scope.get("raw_path")
    if isinstance(raw_path, bytes):
        try:
            path = raw_path.decode("ascii")
        except UnicodeDecodeError:
            path = request.url.path
    else:
        path = request.url.path

    if not path.startswith("/"):
        path = f"/{path}"
    url = f"{UPSTREAM_URL}{path}"

    raw_query = request.scope.get("query_string")
    if isinstance(raw_query, bytes) and raw_query:
        try:
            query = raw_query.decode("ascii")
        except UnicodeDecodeError:
            query = request.url.query
        url = f"{url}?{query}"
    return url


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=None) as client:
        app.state.client = client
        yield


app = FastAPI(title="AgentContext ac-proxy", version="0.1.0", lifespan=lifespan)


@app.get("/_audit/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy(path: str, request: Request) -> Response:
    raw_body = await request.body()
    try:
        parsed_body: Any = json.loads(raw_body) if raw_body else None
    except (json.JSONDecodeError, UnicodeDecodeError):
        parsed_body = raw_body.decode("utf-8", errors="replace")

    request_id = str(uuid.uuid4())
    logger.info(
        json.dumps(
            {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "query_present": bool(request.url.query),
                "request": parsed_body,
                "request_bytes": len(raw_body),
            },
            ensure_ascii=False,
        )
    )

    headers = filtered_headers(request.headers.raw)
    url = upstream_request_url(request)

    try:
        upstream_request = request.app.state.client.build_request(
            request.method,
            url,
            headers=headers,
            content=raw_body,
        )
        upstream_response = await request.app.state.client.send(
            upstream_request,
            stream=True,
        )
    except httpx.HTTPError as exc:
        logger.error(
            json.dumps(
                {
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "request_id": request_id,
                    "proxy_error": type(exc).__name__,
                }
            )
        )
        return JSONResponse({"detail": "LLM upstream unavailable"}, status_code=502)

    response = StreamingResponse(
        upstream_response.aiter_raw(),
        status_code=upstream_response.status_code,
        background=BackgroundTask(upstream_response.aclose),
    )
    response.raw_headers = filtered_headers(upstream_response.headers.raw)
    return response
