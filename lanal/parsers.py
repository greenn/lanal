from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus


META_PREFIX = "__LANAL_META__"


@dataclass
class ParsedHeaders:
    blocks: list[list[tuple[str, str]]]
    status_code: int | None
    status_text: str
    server: str | None


def parse_headers(raw: str) -> ParsedHeaders:
    blocks: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    status_code: int | None = None
    status_text = ""
    server: str | None = None

    for original_line in raw.replace("\r\n", "\n").split("\n"):
        line = original_line.rstrip("\r")
        if not line:
            if current:
                blocks.append(current)
                current = []
            continue
        if line.startswith("HTTP/"):
            if current:
                blocks.append(current)
                current = []
            parts = line.split(" ", 2)
            current.append((":status-line", line))
            if len(parts) >= 2:
                try:
                    status_code = int(parts[1])
                except ValueError:
                    pass
            if len(parts) >= 3:
                status_text = parts[2].strip()
            continue
        if ":" in line:
            name, value = line.split(":", 1)
            name = name.strip()
            value = value.strip()
            current.append((name, value))
            if name.lower() == "server":
                server = value
        else:
            current.append(("", line))

    if current:
        blocks.append(current)

    if status_code and not status_text:
        try:
            status_text = HTTPStatus(status_code).phrase
        except ValueError:
            status_text = f"HTTP {status_code}"

    return ParsedHeaders(blocks, status_code, status_text, server)


def parse_meta(stdout: str) -> dict[str, str]:
    for line in reversed(stdout.replace("\r\n", "\n").split("\n")):
        if not line.startswith(META_PREFIX + "\t"):
            continue
        parts = line.split("\t")
        keys = [
            "http_code",
            "remote_ip",
            "remote_port",
            "http_version",
            "num_redirects",
            "url_effective",
            "time_namelookup",
            "time_connect",
            "time_appconnect",
            "time_starttransfer",
            "time_total",
        ]
        values = parts[1:]
        return {key: values[index] if index < len(values) else "" for index, key in enumerate(keys)}
    return {}


def timing_from_meta(meta: dict[str, str]) -> dict[str, float]:
    result: dict[str, float] = {}
    mapping = {
        "dns": "time_namelookup",
        "connect": "time_connect",
        "tls": "time_appconnect",
        "ttfb": "time_starttransfer",
        "total": "time_total",
    }
    for name, key in mapping.items():
        try:
            result[name] = float(meta.get(key, ""))
        except (TypeError, ValueError):
            continue
    return result


def strip_meta(stdout: str) -> str:
    return "\n".join(
        line for line in stdout.replace("\r\n", "\n").split("\n") if not line.startswith(META_PREFIX + "\t")
    ).rstrip()
