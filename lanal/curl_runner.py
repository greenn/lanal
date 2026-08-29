from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .curl_presets import RequestOptions, build_curl_args, display_command, normalized_domain, option_summary
from .database import StoredRequest
from .parsers import META_PREFIX, parse_headers, parse_meta, strip_meta, timing_from_meta


BODY_STORE_LIMIT = 5 * 1024 * 1024
META_FORMAT = (
    "\n"
    + META_PREFIX
    + "\t%{http_code}\t%{remote_ip}\t%{remote_port}\t%{http_version}"
    + "\t%{num_redirects}\t%{url_effective}\t%{time_namelookup}"
    + "\t%{time_connect}\t%{time_appconnect}\t%{time_starttransfer}\t%{time_total}\n"
)


@dataclass(frozen=True)
class CurlInfo:
    executable: str | None
    version: str


def find_curl() -> CurlInfo:
    executable = shutil.which("curl.exe") or shutil.which("curl")
    if not executable:
        return CurlInfo(None, "curl not found")
    try:
        result = subprocess.run(
            [executable, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=5,
            creationflags=_creation_flags(),
        )
        first_line = _decode(result.stdout).splitlines()[0] if result.stdout else "curl"
        return CurlInfo(executable, first_line)
    except Exception as exc:  # startup diagnostics must never crash the GUI
        return CurlInfo(executable, f"curl detected ({exc})")


def execute_curl(executable: str, url: str, options: RequestOptions) -> StoredRequest:
    base_args = build_curl_args(url, options)
    shown_command = display_command(executable, url, options)
    started = time.time()
    started_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    with tempfile.TemporaryDirectory(prefix="lanal-") as temp_dir:
        header_path = Path(temp_dir) / "headers.bin"
        body_path = Path(temp_dir) / "body.bin"

        # Keep the request options identical to the displayed command. These extra
        # flags only redirect/capture curl output so Lanal can present it in tabs.
        actual_args = [executable, *base_args[:-1]]
        actual_args.extend(
            [
                "--dump-header",
                str(header_path),
                "--output",
                str(body_path),
                "--write-out",
                META_FORMAT,
                base_args[-1],
            ]
        )

        try:
            process = subprocess.run(
                actual_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                creationflags=_creation_flags(),
            )
            exit_code = int(process.returncode)
            stdout = _decode(process.stdout)
            stderr = _decode(process.stderr)
        except OSError as exc:
            exit_code = -1
            stdout = ""
            stderr = str(exc)

        elapsed_ms = int(round((time.time() - started) * 1000))
        header_bytes = _read_limited(header_path, BODY_STORE_LIMIT)
        body_bytes = _read_limited(body_path, BODY_STORE_LIMIT)

    headers_raw = _decode(header_bytes)
    parsed_headers = parse_headers(headers_raw)
    meta = parse_meta(stdout)
    timing = timing_from_meta(meta)

    body = _body_to_text(body_bytes, headers_raw)
    if options.method == "HEAD":
        body = "HEAD request: no response body expected."
    elif body_bytes.startswith(header_bytes) and header_bytes:
        body = _body_to_text(body_bytes[len(header_bytes) :], headers_raw)

    status_code = _to_int(meta.get("http_code")) or parsed_headers.status_code
    server = parsed_headers.server

    return StoredRequest(
        id=None,
        domain=normalized_domain(url),
        url=url,
        preset_name=option_summary(options),
        display_command=shown_command,
        started_at=started_iso,
        duration_ms=elapsed_ms,
        exit_code=exit_code,
        stdout=strip_meta(stdout),
        stderr=stderr,
        status_code=status_code,
        remote_ip=meta.get("remote_ip") or None,
        remote_port=meta.get("remote_port") or None,
        http_version=meta.get("http_version") or None,
        final_url=meta.get("url_effective") or url,
        server=server,
        headers_raw=headers_raw,
        body=body,
        timing=timing,
        note="",
        is_sample=False,
    )


def _read_limited(path: Path, limit: int) -> bytes:
    if not path.exists():
        return b""
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        return data[:limit] + b"\n\n[Lanal: response display truncated at 5 MB]"
    return data


def _body_to_text(data: bytes, headers_raw: str) -> str:
    if not data:
        return ""
    lower_headers = headers_raw.lower()
    textual = any(
        marker in lower_headers
        for marker in (
            "content-type: text/",
            "application/json",
            "application/xml",
            "application/javascript",
            "application/xhtml+xml",
        )
    )
    if b"\x00" in data[:4096] and not textual:
        return f"Binary or unsupported response body ({len(data)} bytes captured)."
    text = data.decode("utf-8", errors="replace")
    if not textual and text[:4096].count("\ufffd") > 20:
        return f"Binary or unsupported response body ({len(data)} bytes captured)."
    return text


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _to_int(value: str | None) -> int | None:
    try:
        number = int(value or "")
        return number or None
    except ValueError:
        return None


def _creation_flags() -> int:
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
