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


UPSTREAM = os.getenv(
    "UPSTREAM_URL",
    "https://chatgpt.com/backend-api/codex",
).rstrip("/")
LOG_FILE = os.getenv("LLM_LOG_FILE", "")
HOP_BY_HOP_HEADERS = {
    "connection",
    "content-length",
    "host",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}

logger = logging.getLogger("llm-audit")
logger.setLevel(logging.INFO)
logger.propagate = False

stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(stdout_handler)

if LOG_FILE:
    log_path = Path(LOG_FILE).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=25 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    os.chmod(log_path, 0o600)
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(file_handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=None) as client:
        app.state.client = client
        yield


app = FastAPI(title="AgentContext local audit proxy", version="0.1.0", lifespan=lifespan)


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
                "query": request.url.query,
                "request": parsed_body,
                "upstream": UPSTREAM,
            },
            ensure_ascii=False,
        )
    )

    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }
    url = f"{UPSTREAM}/{path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

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

    response_headers = {
        key: value
        for key, value in upstream_response.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }
    return StreamingResponse(
        upstream_response.aiter_raw(),
        status_code=upstream_response.status_code,
        headers=response_headers,
        background=BackgroundTask(upstream_response.aclose),
    )
