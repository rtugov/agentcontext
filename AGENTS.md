# AgentContext Contributor Guide

## Purpose

AgentContext (AC) is a multi-application repository for observing local AI-agent
traffic and runtime health. Keep each application independently runnable and
keep shared contracts explicit.

## Repository Layout

- `macos-app` contains the native macOS 13+ Swift menu-bar application.
- `proxy-server` contains the standalone Python request audit proxy and is the
  source of truth for proxy behavior and Python dependencies.
- `prometheus-exporter` is reserved for a separate metrics application.
- `README.md` is the only user-facing README. Update it when commands,
  directories, runtime behavior, or configuration change.

## Proxy Invariants

- Bind locally to `127.0.0.1:8090` by default. Do not expose the unauthenticated
  proxy publicly.
- Forward authorization and account headers but never write them to logs.
- Request audit logs may contain prompts, source code, system/developer
  instructions, conversation context, and tool definitions. Treat them as
  sensitive.
- The current scope logs requests sent to the upstream API. Responses are
  streamed without recording response bodies. Document and test any future
  change to that contract.
- Preserve streaming and remove hop-by-hop HTTP headers in both directions.
- Keep `proxy-server/proxy.py` as the only maintained implementation. Do not
  edit the staged copies under `macos-app/Sources/AgentContext/Resources`.
- Run `macos-app/Scripts/sync-resources.sh` after changing `proxy-server` and
  before opening/building the Swift package directly.

## macOS Runtime Layout

- Managed runtime files: `~/Library/Application Support/AgentContext/`
- Sensitive request and operational logs: `~/Library/Logs/AgentContext/`
- Runtime directories must use mode `0700`; source and log files must use mode
  `0600`.
- Request JSONL rotates at 25 MiB with five backups. The operational app log
  rotates at 5 MiB with one backup.
- The menu app may stop only the child process it started. If another process
  owns port `8090`, report it as external and do not terminate it.

## Prometheus Exporter Boundaries

- Keep exporter code and dependencies under `prometheus-exporter`.
- Export derived counters, gauges, and histograms only. Never expose raw
  prompts, request bodies, authorization material, or arbitrary tool output as
  metric labels.
- Avoid unbounded labels such as request IDs, conversation IDs, paths with user
  input, model output, or exception messages.

## Validation

Run portable checks from the repository root:

```bash
bash -n macos-app/Scripts/build-app.sh \
  macos-app/Scripts/install-user.sh \
  macos-app/Scripts/sync-resources.sh

python3 -c 'import ast, pathlib; ast.parse(pathlib.Path("proxy-server/proxy.py").read_text())'
macos-app/Scripts/sync-resources.sh
cmp proxy-server/proxy.py macos-app/Sources/AgentContext/Resources/proxy.py
cmp proxy-server/requirements.txt macos-app/Sources/AgentContext/Resources/requirements.txt
plutil -lint macos-app/Packaging/Info.plist
```

On macOS, also build and test the application:

```bash
cd macos-app
Scripts/build-app.sh
open "dist/AgentContext.app"
curl http://127.0.0.1:8090/_audit/healthz
```

Verify Start/Stop, status transitions, first-run venv creation, log opening,
request-log rotation, handling of an occupied port `8090`, and process cleanup
on Quit.

## Current Work State

- The Python proxy syntax, shell scripts, staged resources, and Info.plist XML
  have been validated on Linux.
- Swift/AppKit compilation cannot be verified in the current Linux workspace.
  The next required milestone is a macOS build with Xcode Command Line Tools,
  followed by the menu and lifecycle checks listed above.
- The repository is initialized locally on branch `main`; no commit or remote
  has been created.

## Change Safety

- Never commit request logs, credentials, tokens, virtual environments, build
  products, or generated staged resources.
- Preserve unrelated user changes and do not rewrite Git history.
- Explain and confirm destructive cleanup, credential changes, public network
  exposure, or service interruption before executing it.
