# AgentContext Contributor Guide

## Scope

AgentContext is a small, provider-neutral HTTP audit proxy and local Context
Timeline. Keep the repository proxy-focused. Do not add desktop applications,
remote collectors, hosted storage, or provider-specific protocol translation
without an explicit project decision.

## Proxy invariants

- Bind examples to `127.0.0.1:8090`. The proxy has no authentication and must
  not be exposed directly to an untrusted network.
- Default to `https://api.openai.com/v1`; preserve `UPSTREAM_URL` overrides.
- Preserve request paths, query strings, streaming, duplicate end-to-end
  headers, authorization headers, and provider account headers.
- Never write headers or query-string contents to audit logs.
- Treat request JSONL as sensitive: it can contain prompts, source code,
  instructions, images, tool arguments, and tool output.
- Do not record upstream response bodies. The Context Timeline may reconstruct
  events only from data observed in later request context.
- Keep `ac-proxy/ac-proxy.py` as the single application implementation.
- Keep the UI dependency-free and served by the same loopback FastAPI process.

## Validation

From the repository root:

```bash
python3 -m venv ac-proxy/venv
ac-proxy/venv/bin/pip install -r ac-proxy/requirements.txt
ac-proxy/venv/bin/python -m unittest discover -s ac-proxy/tests -v
ac-proxy/venv/bin/python -m py_compile ac-proxy/ac-proxy.py
git diff --check
```

Also validate the JavaScript embedded in `CONTEXT_HTML` with Node.js when it is
available.

## Change safety

- Never commit logs, credentials, tokens, virtual environments, or captured
  request fixtures from real users.
- Preserve unrelated user changes and do not rewrite Git history.
- Confirm public network exposure, credential changes, service interruption,
  destructive cleanup outside the requested scope, and force pushes.
