from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import stat
import tempfile
import unittest
from pathlib import Path

import httpx


MODULE_PATH = Path(__file__).resolve().parents[1] / "ac-proxy.py"
os.environ["UPSTREAM_URL"] = "https://provider.example.test/api"
os.environ["LLM_LOG_FILE"] = ""
SPEC = importlib.util.spec_from_file_location("agentcontext_ac_proxy", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
proxy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(proxy)


class HeaderFilteringTests(unittest.TestCase):
    def test_release_version(self) -> None:
        self.assertEqual(proxy.__version__, "0.0.1")
        self.assertEqual(proxy.app.version, "0.0.1")

    def test_openai_default_and_provider_neutral_override(self) -> None:
        self.assertEqual(
            proxy.configured_upstream_url(None),
            "https://api.openai.com/v1",
        )
        self.assertEqual(
            proxy.configured_upstream_url("https://provider.example/v1/"),
            "https://provider.example/v1",
        )

    def test_filters_fixed_and_connection_nominated_headers(self) -> None:
        headers = [
            (b"host", b"127.0.0.1:8090"),
            (b"connection", b"keep-alive, X-Internal-Hop"),
            (b"x-internal-hop", b"remove-me"),
            (b"authorization", b"forward-me"),
            (b"chatgpt-account-id", b"forward-me-too"),
        ]

        self.assertEqual(
            proxy.filtered_headers(headers),
            [
                (b"authorization", b"forward-me"),
                (b"chatgpt-account-id", b"forward-me-too"),
            ],
        )

    def test_preserves_duplicate_end_to_end_headers(self) -> None:
        headers = [
            (b"set-cookie", b"first=1"),
            (b"set-cookie", b"second=2"),
        ]
        self.assertEqual(proxy.filtered_headers(headers), headers)


class ProxyIntegrationTests(unittest.TestCase):
    def test_forwards_sensitive_headers_without_logging_or_hop_headers(self) -> None:
        captured_request: dict[str, httpx.Request] = {}
        audit_records: list[str] = []

        class AuditCapture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                audit_records.append(record.getMessage())

        class TestStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b"data: done\n\n"

        def upstream_handler(request: httpx.Request) -> httpx.Response:
            captured_request["request"] = request
            return httpx.Response(
                200,
                headers=[
                    ("content-type", "text/event-stream"),
                    ("set-cookie", "first=1"),
                    ("set-cookie", "second=2"),
                    ("connection", "x-upstream-hop"),
                    ("x-upstream-hop", "remove-me"),
                ],
                stream=TestStream(),
            )

        async def exercise_proxy() -> httpx.Response:
            upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(upstream_handler))
            proxy.app.state.client = upstream_client
            app_transport = httpx.ASGITransport(app=proxy.app)
            try:
                async with httpx.AsyncClient(
                    transport=app_transport,
                    base_url="http://127.0.0.1:8090",
                ) as client:
                    return await client.post(
                        "/deployments/model%2Fversion/responses?api_key=secret-query",
                        headers={
                            "authorization": "Bearer test-token",
                            "chatgpt-account-id": "test-account",
                            "connection": "x-client-hop",
                            "x-client-hop": "remove-me",
                        },
                        json={"stream": True},
                    )
            finally:
                await upstream_client.aclose()

        old_handlers = proxy.logger.handlers
        proxy.logger.handlers = [AuditCapture()]
        try:
            response = asyncio.run(exercise_proxy())
        finally:
            proxy.logger.handlers = old_handlers

        forwarded = captured_request["request"]
        self.assertEqual(
            str(forwarded.url),
            f"{proxy.UPSTREAM_URL}/deployments/model%2Fversion/responses?api_key=secret-query",
        )
        self.assertEqual(forwarded.headers["authorization"], "Bearer test-token")
        self.assertEqual(forwarded.headers["chatgpt-account-id"], "test-account")
        self.assertNotIn("x-client-hop", forwarded.headers)
        self.assertEqual(response.content, b"data: done\n\n")
        self.assertEqual(response.headers.get_list("set-cookie"), ["first=1", "second=2"])
        self.assertNotIn("x-upstream-hop", response.headers)
        self.assertEqual(len(audit_records), 1)
        self.assertNotIn("test-token", audit_records[0])
        self.assertNotIn("test-account", audit_records[0])
        self.assertNotIn("secret-query", audit_records[0])


class PrivateRotatingFileHandlerTests(unittest.TestCase):
    def test_active_and_rotated_logs_remain_private(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "requests.jsonl"
            old_umask = os.umask(0o022)
            try:
                handler = proxy.PrivateRotatingFileHandler(
                    log_path,
                    maxBytes=1,
                    backupCount=1,
                    encoding="utf-8",
                )
                record = logging.LogRecord(
                    "test",
                    logging.INFO,
                    __file__,
                    1,
                    "sensitive audit record",
                    (),
                    None,
                )
                handler.emit(record)
                handler.emit(record)
                handler.close()
            finally:
                os.umask(old_umask)

            self.assertEqual(stat.S_IMODE(log_path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(log_path.with_suffix(".jsonl.1").stat().st_mode), 0o600)


class ContextTimelineTests(unittest.TestCase):
    def test_reads_lines_backward_across_small_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "requests.jsonl"
            log_path.write_text("first\nsecond value\nтретий\n", encoding="utf-8")

            lines = list(proxy.reverse_log_lines(log_path, block_size=5))

            self.assertEqual(lines, ["третий", "second value", "first"])

    def test_reads_latest_requests_across_rotation_and_merges_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "requests.jsonl"
            rotated_path = Path(f"{log_path}.1")
            rotated_path.write_text(
                json.dumps(
                    {
                        "timestamp": "2026-08-18T10:00:00Z",
                        "request_id": "old",
                        "method": "POST",
                        "path": "/responses",
                        "request": {"model": "old-model"},
                        "request_bytes": 20,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            log_path.write_text(
                "not-json\n"
                + json.dumps(
                    {
                        "timestamp": "2026-08-18T10:01:00Z",
                        "request_id": "new",
                        "method": "POST",
                        "path": "/responses",
                        "request": {"model": "new-model"},
                        "request_bytes": 20,
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "timestamp": "2026-08-18T10:01:01Z",
                        "request_id": "new",
                        "proxy_error": "ConnectError",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            records = proxy.read_audit_records(str(log_path), limit=2)

            self.assertEqual([record["request_id"] for record in records], ["old", "new"])
            self.assertEqual(records[1]["proxy_error"], "ConnectError")

    def test_limit_keeps_only_latest_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "requests.jsonl"
            log_path.write_text(
                "\n".join(
                    json.dumps({"request_id": str(index), "request": {}})
                    for index in range(3)
                )
                + "\n",
                encoding="utf-8",
            )

            records = proxy.read_audit_records(str(log_path), limit=2)

            self.assertEqual([record["request_id"] for record in records], ["1", "2"])

    def test_context_page_is_local_and_does_not_embed_log_contents(self) -> None:
        async def exercise_page() -> httpx.Response:
            app_transport = httpx.ASGITransport(app=proxy.app)
            async with httpx.AsyncClient(
                transport=app_transport,
                base_url="http://127.0.0.1:8090",
            ) as client:
                return await client.get("/_audit/context")

        response = asyncio.run(exercise_page())

        self.assertEqual(response.status_code, 200)
        self.assertIn("AgentContext · Context Timeline", response.text)
        self.assertIn("setInterval", response.text)
        self.assertIn("2500", response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn("default-src 'none'", response.headers["content-security-policy"])

    def test_audit_api_returns_captured_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "requests.jsonl"
            log_path.write_text(
                json.dumps({"request_id": "visible", "request": {"model": "test-model"}})
                + "\n",
                encoding="utf-8",
            )

            async def exercise_api() -> httpx.Response:
                app_transport = httpx.ASGITransport(app=proxy.app)
                async with httpx.AsyncClient(
                    transport=app_transport,
                    base_url="http://127.0.0.1:8090",
                ) as client:
                    return await client.get("/_audit/api/requests?limit=1")

            old_log_file = proxy.LOG_FILE
            proxy.LOG_FILE = str(log_path)
            try:
                response = asyncio.run(exercise_api())
            finally:
                proxy.LOG_FILE = old_log_file

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["records"][0]["request_id"], "visible")
            self.assertEqual(response.headers["cache-control"], "no-store")

    def test_builds_deduplicated_messages_tools_results_and_reasoning(self) -> None:
        message = {
            "type": "message",
            "id": "message-1",
            "role": "user",
            "content": [{"type": "input_text", "text": "Inspect the workspace"}],
        }
        reasoning = {
            "type": "reasoning",
            "id": "reasoning-1",
            "encrypted_content": "must-not-be-returned",
            "summary": [],
        }
        tool_call = {
            "type": "custom_tool_call",
            "id": "tool-1",
            "call_id": "call-1",
            "name": "exec",
            "status": "completed",
            "input": '{"cmd":"pwd"}',
        }
        tool_result = {
            "type": "custom_tool_call_output",
            "id": "result-1",
            "call_id": "call-1",
            "output": "/workspace",
        }
        records = [
            {
                "timestamp": "2026-08-18T10:00:00Z",
                "request_id": "request-1",
                "method": "POST",
                "path": "/responses",
                "request_bytes": 100,
                "request": {"model": "test-model", "input": [message, reasoning, tool_call]},
            },
            {
                "timestamp": "2026-08-18T10:01:00Z",
                "request_id": "request-2",
                "method": "POST",
                "path": "/responses",
                "request_bytes": 120,
                "request": {
                    "model": "test-model",
                    "input": [message, reasoning, tool_call, tool_result],
                },
            },
        ]

        context = proxy.build_context_timeline(records)

        self.assertEqual(context["summary"]["call_count"], 2)
        self.assertEqual(context["summary"]["event_count"], 4)
        self.assertEqual(context["calls"][0]["new_event_count"], 3)
        self.assertEqual(context["calls"][1]["new_event_count"], 1)
        self.assertEqual(
            [event["kind"] for event in context["events"]],
            ["message", "reasoning", "tool_call", "tool_result"],
        )
        self.assertEqual(context["events"][0]["body"], "Inspect the workspace")
        self.assertEqual(context["events"][2]["tool_name"], "exec")
        self.assertEqual(context["events"][3]["call_id"], "call-1")
        self.assertNotIn("must-not-be-returned", json.dumps(context))

    def test_context_api_returns_normalized_events(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "requests.jsonl"
            log_path.write_text(
                json.dumps(
                    {
                        "timestamp": "2026-08-18T10:00:00Z",
                        "request_id": "visible",
                        "method": "POST",
                        "path": "/responses",
                        "request": {
                            "model": "test-model",
                            "input": [
                                {
                                    "type": "message",
                                    "id": "message-1",
                                    "role": "user",
                                    "content": [{"type": "input_text", "text": "hello"}],
                                }
                            ],
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            async def exercise_api() -> httpx.Response:
                app_transport = httpx.ASGITransport(app=proxy.app)
                async with httpx.AsyncClient(
                    transport=app_transport,
                    base_url="http://127.0.0.1:8090",
                ) as client:
                    return await client.get("/_audit/api/context?limit=1")

            old_log_file = proxy.LOG_FILE
            proxy.LOG_FILE = str(log_path)
            try:
                response = asyncio.run(exercise_api())
            finally:
                proxy.LOG_FILE = old_log_file

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["summary"]["event_count"], 1)
            self.assertEqual(response.json()["events"][0]["kind"], "message")


if __name__ == "__main__":
    unittest.main()
