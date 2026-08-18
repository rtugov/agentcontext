# Contributing

Thank you for helping improve AgentContext.

## Before opening an issue

- Search existing issues first.
- Remove prompts, source code, tokens, account IDs, and other private data from
  screenshots and logs.
- For vulnerabilities, follow [SECURITY.md](SECURITY.md) instead of opening a
  public issue.

## Development setup

```bash
git clone https://github.com/rtugov/agentcontext.git
cd agentcontext
python3 -m venv ac-proxy/venv
ac-proxy/venv/bin/pip install -r ac-proxy/requirements.txt
```

Run the checks:

```bash
ac-proxy/venv/bin/python -m unittest discover -s ac-proxy/tests -v
ac-proxy/venv/bin/python -m py_compile ac-proxy/ac-proxy.py
git diff --check
```

## Project boundaries

- Keep the proxy provider-neutral and protocol-preserving.
- Keep the web UI dependency-free and served by the same FastAPI process.
- Never log credentials, provider account headers, or query-string contents.
- Do not add real request logs or credentials as fixtures.
- Preserve streaming and duplicate end-to-end response headers.
- Add tests and README updates for behavior or configuration changes.

## Pull requests

Keep pull requests focused. Explain the user-visible change, security impact,
and validation performed. By contributing, you agree that your contribution is
licensed under the repository's MIT License.
