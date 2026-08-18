from __future__ import annotations

import hashlib
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
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

DEFAULT_UPSTREAM_URL = "https://api.openai.com/v1"
DEFAULT_CONTEXT_LIMIT = 200
__version__ = "0.0.1"

CONTEXT_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentContext · Context Timeline</title>
  <style>
    :root { color-scheme:dark; --bg:#101113; --panel:#181a1f; --soft:#22252c; --line:#30343d; --muted:#949aa7; --text:#e8eaf0; --blue:#83b4ff; --orange:#ee9b42; --green:#66c98f; --purple:#b28ae2; --red:#ee6c73; }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:var(--text); font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; }
    button,input { font:inherit; }
    header { position:sticky; top:0; z-index:5; display:flex; align-items:center; gap:14px; min-height:62px; padding:12px 22px; background:rgba(16,17,19,.96); border-bottom:1px solid var(--line); backdrop-filter:blur(9px); }
    h1,h2 { margin:0; font-family:system-ui,sans-serif; }
    h1 { font-size:17px; } h2 { margin-bottom:10px; font-size:13px; color:#c7cad2; text-transform:uppercase; letter-spacing:.07em; }
    .subtitle,#status,.muted { color:var(--muted); }
    #status { margin-left:auto; white-space:nowrap; }
    button { color:var(--text); background:var(--soft); border:1px solid var(--line); border-radius:6px; padding:7px 11px; cursor:pointer; }
    button:hover,button.active { border-color:#667080; background:#2b3039; }
    main { max-width:1240px; margin:auto; padding:22px; }
    .metrics { display:grid; grid-template-columns:repeat(4,minmax(130px,1fr)); gap:10px; margin-bottom:24px; }
    .metric { padding:12px 14px; border:1px solid var(--line); border-radius:8px; background:var(--panel); }
    .metric strong { display:block; font:600 22px/1.2 system-ui,sans-serif; }
    .metric span { color:var(--muted); font-size:12px; }
    .call-strip { display:flex; gap:5px; overflow-x:auto; padding:3px 1px 10px; }
    .call-chip { min-width:48px; padding:8px 9px; border-top:3px solid var(--blue); text-align:left; }
    .call-chip.error { border-top-color:var(--red); }
    .call-chip small { display:block; color:var(--muted); }
    #call-info { min-height:24px; margin:3px 0 22px; color:var(--muted); }
    .toolbar { position:sticky; top:62px; z-index:4; display:flex; flex-wrap:wrap; gap:8px; padding:10px 0; background:var(--bg); }
    .filters { display:flex; flex-wrap:wrap; gap:6px; }
    #search { flex:1; min-width:220px; margin-left:auto; padding:8px 10px; color:var(--text); background:#15171b; border:1px solid var(--line); border-radius:6px; outline:none; }
    #search:focus { border-color:#667080; }
    .event { position:relative; margin:0 0 10px 24px; border:1px solid var(--line); border-radius:8px; background:var(--panel); }
    .event::before { content:""; position:absolute; left:-29px; top:17px; width:10px; height:10px; border-radius:3px; background:var(--blue); }
    .event::after { content:""; position:absolute; left:-25px; top:27px; bottom:-21px; width:1px; background:var(--line); }
    .event.tool_call::before { background:var(--orange); } .event.tool_result::before { background:var(--green); } .event.reasoning::before { background:var(--purple); }
    .event-summary { display:grid; grid-template-columns:125px minmax(100px,1fr) auto; align-items:center; gap:12px; padding:10px 13px; cursor:pointer; list-style:none; }
    .event-summary::-webkit-details-marker { display:none; }
    .label { font-weight:700; text-transform:uppercase; color:var(--blue); }
    .tool_call .label { color:var(--orange); } .tool_result .label { color:var(--green); } .reasoning .label { color:var(--purple); }
    .preview { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#cdd0d8; }
    .event-meta { color:var(--muted); font-size:12px; white-space:nowrap; }
    .event-detail { border-top:1px solid var(--line); padding:12px 13px; }
    .badges { display:flex; flex-wrap:wrap; gap:7px; margin-bottom:10px; }
    .badge { padding:2px 7px; border-radius:4px; background:var(--soft); color:#c4c8d1; font-size:12px; }
    pre { margin:0; max-height:600px; overflow:auto; padding:13px; border-radius:6px; background:#0c0d0f; color:#d7dae0; white-space:pre-wrap; word-break:break-word; }
    .empty { padding:46px 20px; text-align:center; color:var(--muted); border:1px dashed var(--line); border-radius:8px; }
    @media(max-width:720px){ header{padding:10px 12px}.subtitle{display:none}main{padding:14px 10px}.metrics{grid-template-columns:repeat(2,1fr)}.event-summary{grid-template-columns:1fr}.event-meta{display:none}.toolbar{top:58px} }
  </style>
</head>
<body>
  <header><h1>AgentContext</h1><span class="subtitle">Context Timeline · reconstructed from captured requests</span><span id="status">Loading…</span><button id="refresh">Refresh</button></header>
  <main>
    <div id="metrics" class="metrics"></div>
    <section><h2>Agent calls</h2><div id="call-strip" class="call-strip"></div><div id="call-info">Click a call to filter its newly observed events.</div></section>
    <div class="toolbar"><div class="filters" id="filters"></div><input id="search" type="search" placeholder="Search messages, tools, commands, output…"></div>
    <section><h2 id="events-title">Context timeline</h2><div id="events" class="empty">Loading context…</div></section>
  </main>
  <script>
    const state={data:null,kind:'all',call:null,query:''};
    const $=selector=>document.querySelector(selector);
    const node=(tag,value,className)=>{const element=document.createElement(tag);if(value!==undefined)element.textContent=value;if(className)element.className=className;return element};
    const valueText=value=>{if(value===null||value===undefined)return '';if(typeof value==='string'){try{return JSON.stringify(JSON.parse(value),null,2)}catch{return value}}return JSON.stringify(value,null,2)};
    const preview=value=>valueText(value).replace(/\s+/g,' ').trim().slice(0,180)||'No readable content';
    const localTime=value=>value?new Date(value).toLocaleString():'unknown time';
    function metric(value,label){const box=node('div',undefined,'metric');box.append(node('strong',String(value)),node('span',label));return box}
    function renderMetrics(){const s=state.data.summary,k=s.kind_counts||{},target=$('#metrics');target.replaceChildren(metric(s.call_count,'agent API calls'),metric(k.message||0,'messages'),metric(k.tool_call||0,'tool calls'),metric(k.tool_result||0,'tool results'))}
    function renderCalls(){const target=$('#call-strip');target.replaceChildren();for(const call of state.data.calls){const button=node('button',undefined,`call-chip${call.proxy_error?' error':''}${state.call===call.index?' active':''}`);button.append(node('strong',`#${call.index}`),node('small',`${call.input_count} ctx`));button.title=`${localTime(call.timestamp)}\n${call.method||'HTTP'} ${call.path||'/'}\n${call.model||'unknown model'}\n${call.request_bytes||0} bytes · ${call.new_event_count} new events`;button.addEventListener('click',()=>{state.call=state.call===call.index?null:call.index;render()});target.append(button)}const selected=state.data.calls.find(call=>call.index===state.call);$('#call-info').textContent=selected?`Call #${selected.index} · ${localTime(selected.timestamp)} · ${selected.path} · ${selected.model||'unknown model'} · ${selected.input_count} context items · ${selected.new_event_count} newly observed events`:'Click a call to filter its newly observed events.'}
    function renderFilters(){const filters=[['all','All'],['message','Messages'],['tool_call','Tool calls'],['tool_result','Results'],['reasoning','Reasoning']];const target=$('#filters');target.replaceChildren();for(const [kind,label] of filters){const button=node('button',label,state.kind===kind?'active':'');button.addEventListener('click',()=>{state.kind=kind;renderEvents();renderFilters()});target.append(button)}}
    function eventLabel(event,toolNames){if(event.kind==='message')return event.role||'message';if(event.kind==='tool_call')return `tool · ${event.tool_name}`;if(event.kind==='tool_result')return `result · ${toolNames.get(event.call_id)||'tool'}`;return 'reasoning'}
    function eventBody(event){if(event.kind==='message')return event.body||`${event.image_count||0} image input`;if(event.kind==='tool_call')return event.payload;if(event.kind==='tool_result')return event.output;return event.summary||'Encrypted reasoning recorded; readable content is not available.'}
    function renderEvents(){const target=$('#events'),toolNames=new Map(state.data.events.filter(e=>e.kind==='tool_call').map(e=>[e.call_id,e.tool_name]));const query=state.query.toLowerCase();const visible=state.data.events.filter(event=>(state.kind==='all'||event.kind===state.kind)&&(!state.call||event.call_index===state.call)&&(!query||JSON.stringify(event).toLowerCase().includes(query)));target.replaceChildren();$('#events-title').textContent=`Context timeline · ${visible.length} event${visible.length===1?'':'s'}`;if(!visible.length){target.className='empty';target.textContent='No events match the current filters.';return}target.className='';for(const event of visible){const details=node('details',undefined,`event ${event.kind}`),summary=node('summary',undefined,'event-summary'),label=node('span',eventLabel(event,toolNames),'label'),body=eventBody(event),short=node('span',preview(body),'preview'),meta=node('span',`call #${event.call_index} · ${localTime(event.observed_at)}`,'event-meta');summary.append(label,short,meta);const detail=node('div',undefined,'event-detail'),badges=node('div',undefined,'badges');badges.append(node('span',`first observed in call #${event.call_index}`,'badge'));if(event.call_id)badges.append(node('span',`call_id ${event.call_id}`,'badge'));if(event.status)badges.append(node('span',`status ${event.status}`,'badge'));if(event.image_count)badges.append(node('span',`${event.image_count} image${event.image_count===1?'':'s'}`,'badge'));detail.append(badges,node('pre',valueText(body)));details.append(summary,detail);target.append(details)}}
    function render(){renderMetrics();renderCalls();renderFilters();renderEvents()}
    let lastPayload='',loading=false;
    async function load(force=false){if(loading)return;loading=true;const status=$('#status');if(!state.data)status.textContent='Loading…';try{const response=await fetch('/_audit/api/context?limit=200',{cache:'no-store'});if(!response.ok)throw new Error(`HTTP ${response.status}`);const payload=await response.text();if(force||payload!==lastPayload){state.data=JSON.parse(payload);lastPayload=payload;render()}status.textContent=`Live · ${state.data.summary.call_count} calls · ${state.data.summary.event_count} events`}catch(error){if(!state.data){$('#events').className='empty';$('#events').textContent=`Could not load context: ${error.message}`}status.textContent='Polling unavailable'}finally{loading=false}}
    $('#search').addEventListener('input',event=>{state.query=event.target.value;renderEvents()});$('#refresh').addEventListener('click',()=>load(true));load();setInterval(()=>{if(!document.hidden)load()},2500);
  </script>
</body>
</html>
"""


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
LOG_FILE = os.getenv("LLM_LOG_FILE", "./requests.jsonl")
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


def audit_log_paths(log_file: str) -> list[Path]:
    """Return existing rotated logs from oldest to the active log."""

    if not log_file:
        return []
    active = Path(log_file).expanduser()
    rotated = [Path(f"{active}.{index}") for index in range(5, 0, -1)]
    return [path for path in [*rotated, active] if path.is_file()]


def reverse_log_lines(path: Path, block_size: int = 64 * 1024):
    """Yield UTF-8 log lines from newest to oldest without loading the file."""

    with path.open("rb") as audit_log:
        audit_log.seek(0, os.SEEK_END)
        position = audit_log.tell()
        remainder = b""
        while position > 0:
            read_size = min(block_size, position)
            position -= read_size
            audit_log.seek(position)
            chunk = audit_log.read(read_size) + remainder
            lines = chunk.split(b"\n")
            remainder = lines[0]
            for line in reversed(lines[1:]):
                if line:
                    yield line.decode("utf-8", errors="replace")
        if remainder:
            yield remainder.decode("utf-8", errors="replace")


def read_audit_records(log_file: str, limit: int) -> list[dict[str, Any]]:
    """Read the latest request records, scanning logs backward as needed."""

    limit = max(1, limit)
    newest_first: list[dict[str, Any]] = []
    errors: dict[str, Any] = {}
    for path in reversed(audit_log_paths(log_file)):
        try:
            for line in reverse_log_lines(path):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                request_id = record.get("request_id")
                if "request" in record:
                    if isinstance(request_id, str) and request_id in errors:
                        record["proxy_error"] = errors.pop(request_id)
                    newest_first.append(record)
                    if len(newest_first) == limit:
                        return list(reversed(newest_first))
                elif isinstance(request_id, str) and "proxy_error" in record:
                    errors[request_id] = record["proxy_error"]
        except OSError:
            continue
    return list(reversed(newest_first))


def context_item_key(item: dict[str, Any]) -> str:
    """Return a stable identity for context items repeated across requests."""

    item_type = str(item.get("type") or ("message" if "role" in item else "unknown"))
    identity = item.get("id") or item.get("call_id")
    if isinstance(identity, str) and identity:
        return f"{item_type}:{identity}"
    encoded = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"{item_type}:sha256:{digest}"


def content_text(content: Any) -> tuple[str, int]:
    """Extract displayable message text and count images without exposing URLs."""

    if isinstance(content, str):
        return content, 0
    if not isinstance(content, list):
        return "", 0
    parts: list[str] = []
    image_count = 0
    for part in content:
        if not isinstance(part, dict):
            continue
        part_type = part.get("type")
        if part_type in {"input_text", "output_text", "text"}:
            value = part.get("text")
            if isinstance(value, str):
                parts.append(value)
        elif part_type in {"input_image", "image", "image_url"}:
            image_count += 1
    return "\n\n".join(parts), image_count


def normalize_context_item(
    item: dict[str, Any],
    record: dict[str, Any],
    call_index: int,
) -> dict[str, Any] | None:
    """Map supported Responses input items to a provider-neutral display event."""

    item_type = item.get("type") or ("message" if "role" in item else None)
    base = {
        "id": context_item_key(item),
        "source_type": item_type,
        "observed_at": record.get("timestamp"),
        "request_id": record.get("request_id"),
        "call_index": call_index,
    }
    if item_type == "message":
        body, image_count = content_text(item.get("content"))
        return {
            **base,
            "kind": "message",
            "role": item.get("role", "unknown"),
            "phase": item.get("phase"),
            "body": body,
            "image_count": image_count,
        }
    if item_type in {"custom_tool_call", "function_call"}:
        payload = item.get("input") if "input" in item else item.get("arguments")
        return {
            **base,
            "kind": "tool_call",
            "tool_name": item.get("name", "unknown"),
            "call_id": item.get("call_id"),
            "status": item.get("status"),
            "payload": payload,
        }
    if item_type in {"custom_tool_call_output", "function_call_output"}:
        return {
            **base,
            "kind": "tool_result",
            "call_id": item.get("call_id"),
            "output": item.get("output"),
        }
    if item_type == "reasoning":
        summary, _ = content_text(item.get("summary"))
        return {
            **base,
            "kind": "reasoning",
            "summary": summary,
            "encrypted": bool(item.get("encrypted_content")),
        }
    return None


def build_context_timeline(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Build deduplicated calls and context events from audit request records."""

    calls: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    seen_items: set[str] = set()
    kind_counts: dict[str, int] = {}
    for record in records:
        if str(record.get("path", "")).startswith("/_audit/") or record.get("path") == "/favicon.ico":
            continue
        request_body = record.get("request")
        request_body = request_body if isinstance(request_body, dict) else {}
        inputs = request_body.get("input", request_body.get("messages", []))
        inputs = inputs if isinstance(inputs, list) else []
        call_index = len(calls) + 1
        new_event_count = 0
        input_counts: dict[str, int] = {}
        for item in inputs:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type", "message"))
            input_counts[item_type] = input_counts.get(item_type, 0) + 1
            item_key = context_item_key(item)
            if item_key in seen_items:
                continue
            seen_items.add(item_key)
            event = normalize_context_item(item, record, call_index)
            if event is None:
                continue
            events.append(event)
            kind = event["kind"]
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
            new_event_count += 1
        calls.append(
            {
                "index": call_index,
                "timestamp": record.get("timestamp"),
                "request_id": record.get("request_id"),
                "method": record.get("method"),
                "path": record.get("path"),
                "model": request_body.get("model"),
                "request_bytes": record.get("request_bytes", 0),
                "input_count": len(inputs),
                "new_event_count": new_event_count,
                "input_counts": input_counts,
                "proxy_error": record.get("proxy_error"),
            }
        )
    return {
        "calls": calls,
        "events": events,
        "summary": {
            "call_count": len(calls),
            "event_count": len(events),
            "kind_counts": kind_counts,
        },
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=None) as client:
        app.state.client = client
        yield


app = FastAPI(title="AgentContext ac-proxy", version=__version__, lifespan=lifespan)


@app.get("/_audit/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/_audit/context", response_class=HTMLResponse)
@app.get("/_audit/trajectory", response_class=HTMLResponse, include_in_schema=False)
async def context_page() -> HTMLResponse:
    return HTMLResponse(
        CONTEXT_HTML,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/_audit/api/requests")
async def audit_requests(limit: int = DEFAULT_CONTEXT_LIMIT) -> JSONResponse:
    safe_limit = max(1, min(limit, 1000))
    records = read_audit_records(LOG_FILE, safe_limit)
    return JSONResponse(
        {"records": records},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/_audit/api/context")
@app.get("/_audit/api/trajectory", include_in_schema=False)
async def context_events(limit: int = DEFAULT_CONTEXT_LIMIT) -> JSONResponse:
    safe_limit = max(1, min(limit, 1000))
    records = read_audit_records(LOG_FILE, safe_limit)
    return JSONResponse(
        build_context_timeline(records),
        headers={"Cache-Control": "no-store"},
    )


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


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
