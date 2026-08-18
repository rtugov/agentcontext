# AgentContext

**A local audit proxy and context viewer for AI coding agents.**

[![Release](https://img.shields.io/badge/release-0.0.1-blue)](https://github.com/rtugov/agentcontext/releases)
[![Python](https://img.shields.io/badge/python-3.9%2B-3776ab)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

AgentContext sits between an AI client and its existing HTTP API. It preserves
the request protocol and streaming response while writing each outbound request
to a private JSONL audit log. The same process serves a dependency-free
**Context Timeline** that reconstructs messages, reasoning markers, tool calls,
and tool results from captured request context.

```text
Codex / OpenCode / pi
          │
          ▼
  AgentContext :8090 ─────► existing provider API
          │
          ├── requests.jsonl
          └── /_audit/context
```

AgentContext does not translate protocols. The client and upstream provider
must already speak the same protocol, such as OpenAI Responses, OpenAI Chat
Completions, or Anthropic Messages.

> [!WARNING]
> AgentContext has no authentication. Bind it to loopback and use a VPN or SSH
> tunnel for remote access. Audit logs can contain prompts, source code,
> instructions, images, commands, and tool output. Never expose the proxy or
> logs directly to a public network.

## Features

- Transparent forwarding of HTTP methods, paths, query strings, credentials,
  provider headers, duplicate headers, and streaming responses.
- Private rotating JSONL logs: 25 MiB per file with five backups.
- Authorization, account headers, and query-string contents are never logged.
- Context Timeline with 2.5-second live polling.
- Deduplicated user, developer, and assistant messages.
- Matched tool calls and results using `call_id`.
- Per-call context growth, filters, search, and expandable payloads.
- Encrypted reasoning content is excluded from the browser API.
- One Python process, no database, no frontend build, and no external assets.

## Requirements

- Python 3.9 or newer.
- A client that supports an API base URL override.
- Access to the upstream provider, directly or through your VPN.

## Quick start

```bash
git clone https://github.com/rtugov/agentcontext.git
cd agentcontext/ac-proxy

python3 -m venv venv
./venv/bin/pip install -r requirements.txt

LLM_LOG_FILE="$PWD/requests.jsonl" \
./venv/bin/uvicorn ac-proxy:app \
  --host 127.0.0.1 \
  --port 8090 \
  --no-access-log
```

When `UPSTREAM_URL` is not set, requests are forwarded to
`https://api.openai.com/v1`.

Verify the proxy:

```bash
curl http://127.0.0.1:8090/_audit/healthz
```

Expected response:

```json
{"status":"ok"}
```

Open the live Context Timeline:

```text
http://127.0.0.1:8090/_audit/context
```

The page polls every 2.5 seconds while its browser tab is visible. It reads the
active log and rotated backups directly; no separate web application is needed.

## Choose the upstream

AgentContext forwards to `UPSTREAM_URL + incoming path`.

Standard OpenAI API:

```bash
UPSTREAM_URL=https://api.openai.com/v1 \
LLM_LOG_FILE="$PWD/requests.jsonl" \
./venv/bin/uvicorn ac-proxy:app --host 127.0.0.1 --port 8090 --no-access-log
```

Codex with an existing ChatGPT subscription login:

```bash
UPSTREAM_URL=https://chatgpt.com/backend-api/codex \
LLM_LOG_FILE="$PWD/requests.jsonl" \
./venv/bin/uvicorn ac-proxy:app --host 127.0.0.1 --port 8090 --no-access-log
```

Another provider:

```bash
UPSTREAM_URL=https://provider.example/v1 \
LLM_LOG_FILE="$PWD/requests.jsonl" \
./venv/bin/uvicorn ac-proxy:app --host 127.0.0.1 --port 8090 --no-access-log
```

Keep credentials in the client's normal credential store. AgentContext forwards
authentication headers for the lifetime of the request but never writes them to
the audit log.

## Codex and VS Code configuration

Add a provider to the user-level `~/.codex/config.toml`:

```toml
model_provider = "agentcontext"

[model_providers.agentcontext]
name = "AgentContext"
base_url = "http://127.0.0.1:8090"
wire_api = "responses"
requires_openai_auth = true

[history]
persistence = "save-all"
```

Use `base_url = "http://127.0.0.1:8090"` without `/v1` when the proxy upstream
is `https://chatgpt.com/backend-api/codex`: Codex appends `/responses` itself.
Restart Codex or run **Developer: Reload Window** in VS Code after changing the
provider.

### Why VS Code history can appear to disappear

Codex stores local threads with the model-provider identity that created them.
After changing the top-level `model_provider` from the built-in `openai`
provider to `agentcontext`, the VS Code sidebar can show only the new provider's
threads. The previous threads normally remain on disk; they were not deleted.

To make the previous provider history visible again:

1. Set `model_provider = "openai"` in `~/.codex/config.toml`.
2. Reload the VS Code window.
3. Return to `model_provider = "agentcontext"` and reload when you want audited
   requests again.

`history.persistence = "save-all"` tells Codex to retain local history so the
CLI and VS Code extension can read it. It does not guarantee that every Codex
version merges threads from different providers into one sidebar; provider
switching may still be required. Do not delete files under `~/.codex` while
troubleshooting a visibility change.

Codex configuration evolves. Check the official
[Codex configuration reference](https://developers.openai.com/codex/config-reference/)
for your installed version.

## VPN and remote-host setups

### Client and proxy are on the VPN machine

If the machine running VS Code or your agent already has the required VPN
access, only AgentContext needs to be started. No SSH tunnel, collector, or
second web service is required:

```bash
UPSTREAM_URL=https://provider-reachable-over-vpn.example/v1 \
LLM_LOG_FILE="$PWD/requests.jsonl" \
./venv/bin/uvicorn ac-proxy:app --host 127.0.0.1 --port 8090 --no-access-log
```

Point the client to `http://127.0.0.1:8090`.

### Proxy runs on a remote VPN host

Start AgentContext on the remote host, still bound to its loopback interface.
Then forward it to your workstation:

```bash
ssh -NT \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L 127.0.0.1:8090:127.0.0.1:8090 \
  user@vpn-host.example
```

The client continues to use `http://127.0.0.1:8090`. SSH encrypts the traffic,
including the authorization headers that AgentContext forwards upstream.

### One SSH connection for MCP and AgentContext

If an MCP server and AgentContext both run on the remote host, forward both
loopback ports through one connection. This example maps a remote MCP service
on port `28988` to local port `8080`, and AgentContext to local port `8090`:

```bash
ssh -NT \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L 127.0.0.1:8080:127.0.0.1:28988 \
  -L 127.0.0.1:8090:127.0.0.1:8090 \
  user@vpn-host.example
```

Configure the MCP client to use its local port `8080` and the model provider to
use `http://127.0.0.1:8090`. MCP is independent of AgentContext; omit the first
`-L` line when you only need the audit proxy. Replace port `28988` with the
actual listen port of your MCP server.

## OpenCode and pi

Any client that supports a provider base URL can use AgentContext. Match the
proxy's `UPSTREAM_URL` to the protocol and provider configured in the client.

OpenCode provider override:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "anthropic": {
      "options": {
        "baseURL": "http://127.0.0.1:8090"
      }
    }
  }
}
```

pi provider override:

```json
{
  "providers": {
    "anthropic": {
      "baseUrl": "http://127.0.0.1:8090"
    }
  }
}
```

These integrations preserve the client's existing model and authentication
configuration. Dedicated presets have not yet been end-to-end tested in
release `0.0.1`.

## Docker

Build the image:

```bash
docker build -t agentcontext:0.0.1 .
docker volume create agentcontext-data
```

Run it with the container port published only on host loopback:

```bash
docker run --rm \
  -p 127.0.0.1:8090:8090 \
  -e UPSTREAM_URL=https://api.openai.com/v1 \
  -v agentcontext-data:/data \
  agentcontext:0.0.1
```

Do not publish it with `-p 8090:8090` on an untrusted host; that can expose the
unauthenticated proxy to the network.

## Audit data and Context Timeline

Each request record contains:

```json
{
  "timestamp": "2026-08-18T12:00:00Z",
  "request_id": "...",
  "method": "POST",
  "path": "/responses",
  "query_present": false,
  "request": {},
  "request_bytes": 1234
}
```

The query string itself, request headers, authorization tokens, and provider
account identifiers are not recorded. Responses are streamed back without
recording response bodies.

The Context Timeline reconstructs events already present in captured request
context. Later requests often repeat earlier context, so items are deduplicated
by `id` or `call_id`. Event time means “first observed in this request”; it is
not an exact tool execution timestamp. A final assistant response may not be
visible until a later request includes it in context.

Local endpoints:

| Endpoint | Purpose |
| --- | --- |
| `/_audit/healthz` | Health check |
| `/_audit/context` | Context Timeline web page |
| `/_audit/api/context?limit=200` | Normalized calls and unique events |
| `/_audit/api/requests?limit=200` | Raw captured request records |

The API limit is clamped to 1–1000 records. `/_audit/trajectory` remains an
alias for early development links.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `UPSTREAM_URL` | `https://api.openai.com/v1` | Provider base URL |
| `LLM_LOG_FILE` | `./requests.jsonl` | Private rotating audit log; set empty to log to stdout |

One process points to one upstream. Run separate ports and log files when agents
need different providers.

## Development

```bash
python3 -m venv ac-proxy/venv
ac-proxy/venv/bin/pip install -r ac-proxy/requirements.txt
ac-proxy/venv/bin/python -m unittest discover -s ac-proxy/tests -v
ac-proxy/venv/bin/python -m py_compile ac-proxy/ac-proxy.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a change. Security
issues and safe deployment guidance are covered in [SECURITY.md](SECURITY.md).

## Release status

`0.0.1` is the first public preview. The log format and normalized Context API
may change before `1.0.0`.

## License

AgentContext is available under the [MIT License](LICENSE).
