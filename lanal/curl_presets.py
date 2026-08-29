from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class RequestOptions:
    method: str = "HEAD"
    verbose: bool = False
    ip_version: str = "IPv4"
    http_version: str = "HTTP/2"
    browser_like: bool = True
    extra: str = "Info"


def validate_url(url: str) -> str:
    value = url.strip()
    if not value:
        raise ValueError("Enter a URL.")
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Only http:// and https:// URLs are supported.")
    if not parsed.hostname:
        raise ValueError("URL must contain a hostname.")
    return value


def normalized_domain(url: str) -> str:
    parsed = urlsplit(validate_url(url))
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.port:
        default = (parsed.scheme.lower() == "https" and parsed.port == 443) or (
            parsed.scheme.lower() == "http" and parsed.port == 80
        )
        if not default:
            return f"{host}:{parsed.port}"
    return host


def build_curl_args(url: str, options: RequestOptions) -> list[str]:
    target = validate_url(url)
    args: list[str] = []

    if options.method == "HEAD":
        args.append("-I")
    elif options.method == "GET":
        args.append("-i")
    else:
        raise ValueError(f"Unsupported method preset: {options.method}")

    if options.verbose:
        args.append("-v")

    if options.ip_version == "IPv4":
        args.append("-4")
    elif options.ip_version == "IPv6":
        args.append("-6")
    else:
        raise ValueError(f"Unsupported IP preset: {options.ip_version}")

    if options.http_version == "HTTP/1.1":
        args.append("--http1.1")
    elif options.http_version == "HTTP/2":
        args.append("--http2")
    else:
        raise ValueError(f"Unsupported HTTP preset: {options.http_version}")

    if options.browser_like:
        args.extend(["-A", "Mozilla/5.0", "--compressed"])

    if options.extra == "Redirects":
        args.append("-L")
    elif options.extra == "Raw":
        args.append("--raw")
    elif options.extra not in {"Info", "None"}:
        raise ValueError(f"Unsupported extra preset: {options.extra}")

    args.append(target)
    return args


def _quote_windows(value: str) -> str:
    if not value or any(ch.isspace() for ch in value) or '"' in value:
        return '"' + value.replace('"', '\\"') + '"'
    return value


def display_command(executable: str, url: str, options: RequestOptions) -> str:
    return " ".join(_quote_windows(part) for part in [executable, *build_curl_args(url, options)])


def option_summary(options: RequestOptions) -> str:
    parts = [options.method, options.ip_version, options.http_version]
    if options.verbose:
        parts.append("Verbose")
    if options.browser_like:
        parts.append("Browser-like")
    if options.extra not in {"Info", "None"}:
        parts.append(options.extra)
    return " · ".join(parts)
