from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lanal.curl_presets import RequestOptions, build_curl_args, display_command, normalized_domain, validate_url
from lanal.database import Database, StoredRequest
from lanal.parsers import parse_headers, parse_meta, timing_from_meta


class UrlAndPresetTests(unittest.TestCase):
    def test_normalized_domain(self) -> None:
        self.assertEqual(normalized_domain("https://NovelCrow.com/a"), "novelcrow.com")
        self.assertEqual(normalized_domain("https://localhost:8443/a"), "localhost:8443")
        self.assertEqual(normalized_domain("https://example.com:443/a"), "example.com")

    def test_rejects_unsupported_scheme(self) -> None:
        with self.assertRaises(ValueError):
            validate_url("file:///C:/Windows/win.ini")

    def test_default_arguments(self) -> None:
        options = RequestOptions()
        args = build_curl_args("https://example.com/", options)
        self.assertEqual(args[0], "-I")
        self.assertIn("-4", args)
        self.assertIn("--http2", args)
        self.assertIn("Mozilla/5.0", args)
        self.assertEqual(args[-1], "https://example.com/")

    def test_ipv6_get_verbose_redirects(self) -> None:
        options = RequestOptions(
            method="GET",
            verbose=True,
            ip_version="IPv6",
            http_version="HTTP/1.1",
            browser_like=False,
            extra="Redirects",
        )
        args = build_curl_args("https://example.com/", options)
        for expected in ("-i", "-v", "-6", "--http1.1", "-L"):
            self.assertIn(expected, args)
        self.assertNotIn("-4", args)

    def test_command_formatting(self) -> None:
        command = display_command("curl.exe", "https://example.com/", RequestOptions())
        self.assertTrue(command.startswith("curl.exe -I"))
        self.assertTrue(command.endswith("https://example.com/"))


class ParserTests(unittest.TestCase):
    def test_headers_preserve_duplicates(self) -> None:
        parsed = parse_headers(
            "HTTP/2 403\r\nserver: cloudflare\r\nset-cookie: a=1\r\nset-cookie: b=2\r\n\r\n"
        )
        self.assertEqual(parsed.status_code, 403)
        self.assertEqual(parsed.server, "cloudflare")
        cookies = [pair for block in parsed.blocks for pair in block if pair[0] == "set-cookie"]
        self.assertEqual(len(cookies), 2)

    def test_meta_and_timing(self) -> None:
        raw = (
            "__LANAL_META__\t403\t104.21.1.2\t443\t2\t0\thttps://example.com/"
            "\t0.01\t0.02\t0.03\t0.04\t0.05\n"
        )
        meta = parse_meta(raw)
        self.assertEqual(meta["http_code"], "403")
        timing = timing_from_meta(meta)
        self.assertEqual(timing["total"], 0.05)


class DatabaseTests(unittest.TestCase):
    def test_insert_read_note_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "test.db")
            item = StoredRequest(
                id=None,
                domain="example.com",
                url="https://example.com/",
                preset_name="HEAD",
                display_command="curl -I https://example.com/",
                started_at="2026-08-29T10:00:00+03:00",
                duration_ms=12,
                exit_code=0,
                stdout="",
                stderr="",
                status_code=200,
                remote_ip="93.184.216.34",
                remote_port="443",
                http_version="2",
                final_url="https://example.com/",
                server="example",
                headers_raw="HTTP/2 200\nserver: example\n",
                body="",
                timing={"total": 0.012},
            )
            request_id = db.add_request(item)
            loaded = db.get_request(request_id)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.status_code, 200)
            db.update_note(request_id, "test note")
            self.assertEqual(db.get_request(request_id).note, "test note")
            db.delete_request(request_id)
            self.assertIsNone(db.get_request(request_id))

    def test_seed_uses_novelcrow(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "seed.db")
            db.seed_demo_if_empty()
            items = db.list_requests()
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].domain, "novelcrow.com")
            self.assertTrue(items[0].is_sample)


if __name__ == "__main__":
    unittest.main()
