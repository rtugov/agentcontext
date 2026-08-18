# Security policy

## Supported versions

AgentContext is a pre-1.0 project. Security fixes are applied to the latest
release.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting for this repository. Do not open a
public issue containing a vulnerability, token, captured request, or private
log excerpt.

Include the affected version, deployment topology, reproduction steps, and the
smallest possible redacted example. Never send live credentials.

## Deployment boundary

AgentContext is an unauthenticated debugging proxy. It is designed for:

- `127.0.0.1` on the same machine as the client;
- loopback on a VPN host reached through an SSH local forward; or
- an equivalently trusted and authenticated private transport.

Do not bind it to a public or untrusted interface. Anyone who can reach the
proxy can send requests through the client's configured upstream path, and
anyone who can reach the Context API can read sensitive captured request data.

Audit JSONL can contain prompts, instructions, source code, tool arguments,
tool output, and images. Store it with restrictive permissions, short
retention, and the same security boundary as the source workstation.

AgentContext deliberately does not log request headers or query-string
contents and does not record upstream response bodies. Changes to those
boundaries require explicit documentation, tests, and security review.
