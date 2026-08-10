# AgentContext (AC)

AgentContext is a collection of independently runnable applications for
auditing local AI-agent requests and shipping those audit logs to an
observability backend.

**AC — Observability for AI agents.**

**One local observability gateway for Codex, OpenCode, and pi.**

## Brand and component naming

The name can be playful:

> **Agent Context (AC)** — *Keeping your agents cool under pressure.* 😄

More serious tagline options:

- **AC — Observability for AI agents**
- **AC — See what your agents see**
- **AC — Context, actions, traces**
- **AC — Understand every agent run**
- **AC — Agent telemetry, in context**

Future components should use short, consistent names such as `ac-agent`,
`ac-collector`, `ac-api`, and `ac-ui`.

```text
AgentContext/
├── macos-app/            macOS menu-bar controller
├── ac-proxy/             protocol-preserving multi-agent audit proxy
└── alloy/                optional Alloy-to-Loki integration
```

The standalone proxy defaults to the standard OpenAI API at
`https://api.openai.com/v1`. Set `UPSTREAM_URL` to use another compatible
provider. It streams responses back without recording response bodies and
never records authorization headers, account headers, or query-string
contents. The proxy binds to a loopback address by default, provides no
authentication of its own, and should not be exposed directly to a public
network.

## One gateway for multiple coding agents

AgentContext is intentionally an agent gateway, not a Codex-only logger. The
standalone proxy can audit Codex, OpenCode, pi, and other clients that let you
override an API base URL. It preserves the client's wire protocol, paths,
streaming response, authorization, and provider-specific account headers while
keeping credentials out of audit logs.

| Client | Integration path | Current status |
| --- | --- | --- |
| Codex | `model_provider` and `base_url` in `~/.codex/config.toml` | macOS preset available |
| OpenCode | Provider `options.baseURL` (or V2 `settings.baseURL`) | Supported proxy target; end-to-end preset still to be tested |
| pi | Provider `baseUrl` in `~/.pi/agent/models.json` | Supported proxy target; end-to-end preset still to be tested |

The proxy does not translate between API protocols. The selected client mode
and upstream must speak the same protocol, such as Anthropic Messages, OpenAI
Responses, OpenAI Chat Completions, or another HTTP streaming API. One proxy
process points to one `UPSTREAM_URL`; agents using that same upstream can share
it. Run separate loopback ports and log files when agents need different
upstreams.

The current macOS menu app is the Codex preset. OpenCode and pi can use the
standalone proxy today; dedicated menu presets and verified configuration-copy
actions are a natural next step.

## ac-proxy

`ac-proxy` is the provider-neutral FastAPI application used by the macOS
app. It can also be run directly on macOS or Linux with Python 3.9 or newer.
Without `UPSTREAM_URL`, requests are forwarded to the standard OpenAI API:

```bash
cd ac-proxy
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

LLM_LOG_FILE="$PWD/requests.jsonl" \
./venv/bin/uvicorn ac-proxy:app --host 127.0.0.1 --port 8090 --no-access-log
```

Override the upstream for another provider:

```bash
UPSTREAM_URL=https://api.example.com/v1 \
LLM_LOG_FILE="$PWD/requests.jsonl" \
./venv/bin/uvicorn ac-proxy:app --host 127.0.0.1 --port 8090 --no-access-log
```

Verify it locally:

```bash
curl http://127.0.0.1:8090/_audit/healthz
```

The expected response is `{"status":"ok"}`.

The forwarding rule is `UPSTREAM_URL + incoming request path`. For example,
an agent request to `/messages` is sent to
`https://provider.example/v1/messages` when `UPSTREAM_URL` is
`https://provider.example/v1`. The proxy does not assume OpenAI, Anthropic, or
any other provider protocol.

Then point the matching OpenCode `baseURL` or pi `baseUrl` at
`http://127.0.0.1:8090`. Keep authentication in the agent's normal credential
store or environment; AgentContext forwards those headers without logging
them.

For example, start the proxy with `UPSTREAM_URL=https://api.anthropic.com/v1`,
then override the existing Anthropic provider in OpenCode's `opencode.json`:

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

The equivalent pi override in `~/.pi/agent/models.json` is:

```json
{
  "providers": {
    "anthropic": {
      "baseUrl": "http://127.0.0.1:8090"
    }
  }
}
```

These overrides keep each client's existing models and authentication. Match
the proxy's `UPSTREAM_URL` to that provider before starting it. See the
[OpenCode provider configuration](https://opencode.ai/docs/providers) and
[pi custom-model configuration](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/models.md)
for other providers and API modes.

### Optional Codex preset

The macOS menu app currently supplies an explicit Codex upstream. The
equivalent standalone command is:

```bash
UPSTREAM_URL=https://chatgpt.com/backend-api/codex \
LLM_LOG_FILE="$PWD/requests.jsonl" \
./venv/bin/uvicorn ac-proxy:app --host 127.0.0.1 --port 8090 --no-access-log
```

## macOS menu-bar app

`macos-app` is a native macOS 13+ menu-bar controller. It starts and stops the
bundled standalone proxy on `127.0.0.1:8090`, reports health, opens the request
log, and copies the required Codex provider configuration.

Requirements:

- macOS 13 or newer.
- Xcode Command Line Tools (`xcode-select --install`).
- Python 3.9 or newer. Homebrew Python is recommended:
  `brew install python`.

Build and install from Terminal:

```bash
cd agentcontext/macos-app
chmod +x Scripts/build-app.sh Scripts/install-user.sh
Scripts/build-app.sh
Scripts/install-user.sh
open "$HOME/Applications/AgentContext.app"
```

The app is ad-hoc signed for personal use. On first launch, macOS may require
approval in **System Settings → Privacy & Security**. The first proxy start
creates a private virtual environment and installs the pinned dependencies, so
it requires internet access and can take a minute.

The build script copies its bundled Python resources from `ac-proxy`,
keeping the standalone service as the source of truth for the app-managed
service. Run `Scripts/sync-resources.sh` before opening the Swift package
directly in Xcode.

## Codex configuration

Choose **Copy Codex configuration** from the AgentContext menu and merge the
copied text into the top-level user file at `~/.codex/config.toml`:

```toml
model_provider = "agentcontext"

[model_providers.agentcontext]
name = "AgentContext ac-proxy"
base_url = "http://127.0.0.1:8090"
wire_api = "responses"
requires_openai_auth = true
```

Restart Codex or reload the VS Code window after changing providers. Threads
created with the built-in `openai` provider remain on disk but may appear in a
different provider history from `agentcontext` threads.

## macOS files and logs

Runtime files follow the standard per-user macOS locations:

```text
~/Library/Application Support/AgentContext/
  ac-proxy.py
  requirements.txt
  venv/

~/Library/Logs/AgentContext/
  requests.jsonl
  requests.jsonl.1 ... requests.jsonl.5
  application.log
```

`requests.jsonl` rotates at 25 MiB and keeps five backups. The application log
rotates at 5 MiB and keeps one backup. Directories use mode `0700`; log and
source files use mode `0600`.

The request log contains prompts, source code, system/developer instructions,
conversation context, and tool definitions. Treat it as sensitive. Do not put
it in iCloud Drive or a shared folder unless that exposure is intentional.

For operational diagnostics that do not need a persistent text file, macOS
Unified Logging (`Logger`/Console.app) is preferable. AgentContext deliberately
uses `~/Library/Logs` because request JSONL is user-owned audit data that needs
to be directly inspectable and removable.

## Using the logs effectively

Treat AgentContext data as two different observability layers:

| Layer | Best use | Data policy |
| --- | --- | --- |
| Raw `requests.jsonl` | Reproduce a request, inspect supplied context, and investigate a specific request ID | Keep local or in a tightly restricted log store with short retention |
| Records in Loki | Search proxy requests and connection errors over time; build log-derived dashboards and alerts | The supplied Alloy configuration ships the complete raw record, so Loki must have the same security boundary as the local log |

Loki, Grafana, and Grafana Alloy are a good target stack: Alloy tails the JSONL
file, Loki stores and indexes it, and Grafana provides dashboards and log
investigation. Prometheus is not a log store and is not required for retaining
these records. It can be added later if dedicated numeric metrics and alerts
become useful.

Do not send the current raw request log to a shared or hosted Loki instance by
default. It can contain prompts, source code, shell commands, tool output, and
conversation context.

For Loki, start with low-cardinality indexed labels such as `service_name`,
`environment`, and a bounded `event` value. Keep `request_id`, `thread_id`,
paths, model strings, tool names, commands, and targets as JSON fields or
structured metadata rather than indexed labels. Commands and output should be
removed or redacted unless the Loki tenant has the same security boundary as
the local audit log.

The current proxy records request events and upstream connection errors. It
does **not** record response bodies, so it cannot yet produce authoritative
`tool_call`, tool-completion status, response status, or execution-duration
events like this proposed normalized record:

```json
{
  "timestamp": "2026-08-10T13:39:21Z",
  "event": "tool_call",
  "tool": "exec",
  "status": "completed",
  "duration_seconds": 2.2,
  "request_id": "..."
}
```

Add a separate sanitized lifecycle event stream before building dashboards on
those fields. Safe next fields for the proxy are HTTP response status,
time-to-response-headers, total stream duration, and byte counts; these do not
require storing response bodies.

### Optional native telemetry integrations

AgentContext does not require native agent telemetry. Its core remains the
provider-neutral proxy and raw audit contract.
Native integrations are optional enrichment sources when deeper semantic
events are useful:

- Codex supports opt-in OpenTelemetry logs and metrics for API
  requests, stream events, tool decisions, tool results, durations, and
  success status. Prompts are redacted by default. This OTLP data can be sent
  to Alloy or an OpenTelemetry Collector and correlated with AgentContext
  proxy records. See the
  [Codex OTel configuration](https://github.com/openai/codex/blob/main/docs/config.md#otel).
- OpenCode plugins can optionally map session, permission, and
  `tool.execute.before` / `tool.execute.after` hooks into the AgentContext event
  contract.
- pi extensions can optionally map agent and tool lifecycle events into that
  same contract.

A future collector may normalize any of these sources, but no single agent's
native telemetry should define the AgentContext schema. If full cross-service
timelines become important, OpenTelemetry traces and Tempo can be added without
turning request or thread IDs into Prometheus/Loki index labels.

## Alloy integration

Yes: point Alloy at the active `requests.jsonl` file. Alloy is the collector,
not the durable log store. It reads newline-delimited records, remembers its
read position under `--storage.path`, and sends each record to Loki. Loki owns
retention and querying.

The supplied [`alloy/agentcontext.alloy`](alloy/agentcontext.alloy) pipeline:

- reads the absolute path supplied in `AC_REQUEST_LOG`;
- starts at the beginning on its first run so existing active-file records are
  included;
- parses the record timestamp while preserving the complete JSON line;
- adds only the bounded `service_name="agentcontext"` and
  `component="ac_proxy"` labels; and
- requires an explicit Loki push URL in `LOKI_URL`.

Run Alloy as the same macOS user as AgentContext so it can read the private
`0600` log file. Keep its position data on persistent local storage:

```bash
export AC_REQUEST_LOG="$HOME/Library/Logs/AgentContext/requests.jsonl"
export LOKI_URL="http://127.0.0.1:3100/loki/api/v1/push"

alloy validate alloy/agentcontext.alloy
alloy run \
  --storage.path="$HOME/Library/Application Support/AgentContext/alloy-data" \
  alloy/agentcontext.alloy
```

Query fields from the JSON at query time instead of making them index labels:

```logql
{service_name="agentcontext", component="ac_proxy"} | json
{service_name="agentcontext", component="ac_proxy"} | json | proxy_error != ""
```

Persistent positions avoid rereading acknowledged bytes after a normal Alloy
restart. They do not make the local files durable. With this active-file-only
configuration, records can be missed if Alloy is stopped while the proxy
rotates the file; the rotated backups then provide manual recovery rather than
automatic ingestion. For a stronger audit guarantee, monitor delivery failures
and disk space, test recovery, and use an appropriately replicated Loki
deployment or a separate encrypted archive.

The current configuration follows only the active file. This avoids duplicate
ingestion from matching both an active file and renamed rotation backups. Test
rotation and outage recovery under the chosen macOS Alloy service setup before
treating the pipeline as audit-grade.

See Grafana's documentation for
[`loki.source.file`](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.source.file/),
[`alloy run`](https://grafana.com/docs/alloy/latest/reference/cli/run/), and
[Loki label cardinality](https://grafana.com/docs/loki/latest/get-started/labels/cardinality/).

## Portable validation

From the repository root, create component virtual environments and run:

```bash
ac-proxy/venv/bin/python -m unittest discover -s ac-proxy/tests -v

bash -n macos-app/Scripts/build-app.sh \
  macos-app/Scripts/install-user.sh \
  macos-app/Scripts/sync-resources.sh
python3 -c 'import ast, pathlib; ast.parse(pathlib.Path("ac-proxy/ac-proxy.py").read_text())'
macos-app/Scripts/sync-resources.sh
cmp ac-proxy/ac-proxy.py macos-app/Sources/AgentContext/Resources/ac-proxy.py
cmp ac-proxy/requirements.txt macos-app/Sources/AgentContext/Resources/requirements.txt
plutil -lint macos-app/Packaging/Info.plist
alloy validate alloy/agentcontext.alloy
```

The Alloy validation command requires Alloy to be installed. The native menu
app still requires macOS 13+ and Xcode Command Line Tools for its build and
lifecycle validation.
