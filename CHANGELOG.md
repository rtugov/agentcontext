# Changelog

All notable changes to AgentContext are documented here.

The project follows [Semantic Versioning](https://semver.org/).

## [0.0.1] - 2026-08-18

First public preview.

### Added

- Provider-neutral streaming HTTP audit proxy.
- Private rotating JSONL request logs.
- Dependency-free Context Timeline with live polling.
- Deduplicated message, reasoning, tool-call, and tool-result events.
- Search, event filters, per-call filtering, and context-growth summaries.
- Local, VPN, SSH tunnel, two-port MCP, and Docker usage documentation.
- Automated tests and GitHub Actions validation.

### Security

- Authorization and provider account headers are forwarded but never logged.
- Query-string presence is recorded without storing query-string contents.
- Encrypted reasoning content is excluded from the Context API.

[0.0.1]: https://github.com/rtugov/agentcontext/releases/tag/0.0.1
