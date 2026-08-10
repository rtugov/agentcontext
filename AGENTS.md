# AgentContext Contributor Guide

## Purpose

AgentContext (AC) is a multi-application repository for observing local AI-agent
traffic and runtime health. Keep each application independently runnable and
keep shared contracts explicit.

## Repository Layout

- `macos-app` contains the native macOS 13+ Swift menu-bar application.
- `ac-proxy` contains the standalone Python request audit proxy and is the
  source of truth for proxy behavior and Python dependencies.
- `alloy` contains the optional Alloy-to-Loki log shipping configuration.
- `README.md` is the only user-facing README. Update it when commands,
  directories, runtime behavior, or configuration change.

## Proxy Invariants

- Bind locally to `127.0.0.1:8090` by default. Do not expose the unauthenticated
  proxy publicly.
- Default to `https://api.openai.com/v1` when `UPSTREAM_URL` is unset. Preserve
  `UPSTREAM_URL` overrides so the standalone proxy remains provider-neutral.
- Forward authorization and account headers but never write them to logs.
- Request audit logs may contain prompts, source code, system/developer
  instructions, conversation context, and tool definitions. Treat them as
  sensitive.
- The current scope logs requests sent to the upstream API. Responses are
  streamed without recording response bodies. Document and test any future
  change to that contract.
- Preserve streaming and remove hop-by-hop HTTP headers in both directions.
- Keep `ac-proxy/ac-proxy.py` as the only maintained implementation. Do not
  edit the staged copies under `macos-app/Sources/AgentContext/Resources`.
- Run `macos-app/Scripts/sync-resources.sh` after changing `ac-proxy` and
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

## Alloy Integration Boundaries

- Require explicit `AC_REQUEST_LOG` and `LOKI_URL` values. Do not embed remote
  credentials or provider-specific endpoints in the configuration.
- Run Alloy with permission to read the private request log and persist its
  position data across restarts.
- Treat Loki as having the same security boundary as the raw audit log unless
  a future pipeline explicitly redacts request bodies.
- Keep labels bounded. Request IDs, conversation IDs, paths, model names,
  commands, output, and exception messages must remain JSON fields rather than
  Loki index labels.

## Validation

Run portable checks from the repository root:

```bash
bash -n macos-app/Scripts/build-app.sh \
  macos-app/Scripts/install-user.sh \
  macos-app/Scripts/sync-resources.sh

python3 -c 'import ast, pathlib; ast.parse(pathlib.Path("ac-proxy/ac-proxy.py").read_text())'
macos-app/Scripts/sync-resources.sh
cmp ac-proxy/ac-proxy.py macos-app/Sources/AgentContext/Resources/ac-proxy.py
cmp ac-proxy/requirements.txt macos-app/Sources/AgentContext/Resources/requirements.txt
plutil -lint macos-app/Packaging/Info.plist
```

After installing each component's dependencies, also run:

```bash
ac-proxy/venv/bin/python -m unittest discover -s ac-proxy/tests -v
alloy validate alloy/agentcontext.alloy
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

- The Python proxy syntax and tests, shell scripts, staged resources, and
  Info.plist XML have been validated on Linux. Alloy configuration validation
  requires an Alloy installation.
- Swift/AppKit compilation cannot be verified in the current Linux workspace.
  The next required milestone is a macOS build with Xcode Command Line Tools,
  followed by the menu and lifecycle checks listed above.
- The repository uses branch `main` and has a configured `origin` remote.

## Change Safety

- Never commit request logs, credentials, tokens, virtual environments, build
  products, or generated staged resources.
- Preserve unrelated user changes and do not rewrite Git history.
- Explain and confirm destructive cleanup, credential changes, public network
  exposure, or service interruption before executing it.
