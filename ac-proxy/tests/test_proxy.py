from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import stat
import tempfile
import unittest
from pathlib import Path

import httpx


MODULE_PATH = Path(__file__).resolve().parents[1] / "ac-proxy.py"
os.environ["UPSTREAM_URL"] = "https://provider.example.test/api"
SPEC = importlib.util.spec_from_file_location("agentcontext_ac_proxy", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
proxy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(proxy)


class HeaderFilteringTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
