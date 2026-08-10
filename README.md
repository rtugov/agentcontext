# AgentContext (AC)

AgentContext is a collection of small applications for observing local
AI-agent traffic and runtime health.

**AC — Observability for AI agents.**

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
`ac-collector`, `ac-api`, `ac-ui`, and `ac-exporter`.

```text
AgentContext/
├── macos-app/            macOS menu-bar controller
├── proxy-server/         standalone Codex request audit proxy
└── prometheus-exporter/  metrics exporter (planned)
```

The current proxy records requests sent from Codex to the ChatGPT Codex
backend. It streams responses back to Codex without recording response bodies
and never records authorization headers.

## Proxy server

`proxy-server` is the standalone FastAPI application used by the macOS app. It
can also be run directly on macOS or Linux with Python 3.9 or newer:

```bash
cd proxy-server
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

UPSTREAM_URL=https://chatgpt.com/backend-api/codex \
LLM_LOG_FILE="$PWD/requests.jsonl" \
./venv/bin/uvicorn proxy:app --host 127.0.0.1 --port 8090
```

Verify it locally:

```bash
curl http://127.0.0.1:8090/_audit/healthz
```

The expected response is `{"status":"ok"}`.

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
cd AgentContext/macos-app
chmod +x Scripts/build-app.sh Scripts/install-user.sh
Scripts/build-app.sh
Scripts/install-user.sh
open "$HOME/Applications/AgentContext.app"
```

The app is ad-hoc signed for personal use. On first launch, macOS may require
approval in **System Settings → Privacy & Security**. The first proxy start
creates a private virtual environment and installs the pinned dependencies, so
it requires internet access and can take a minute.

The build script copies its bundled Python resources from `proxy-server`,
keeping the standalone service as the source of truth for the app-managed
service. Run `Scripts/sync-resources.sh` before opening the Swift package
directly in Xcode.

## Codex configuration

Choose **Copy Codex configuration** from the AgentContext menu and merge the
copied text into the top-level user file at `~/.codex/config.toml`:

```toml
model_provider = "agentcontext"

[model_providers.agentcontext]
name = "AgentContext local audit proxy"
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
  proxy.py
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

## Prometheus exporter

`prometheus-exporter` is reserved for a separate metrics application. It
should consume derived, non-sensitive metrics rather than exposing raw request
bodies or authorization data.
