# Lanal

**Lanal 0.0.1** is a local Windows desktop utility for running and inspecting real `curl.exe` HTTP/HTTPS diagnostics.

It is designed for quick comparisons such as IPv4 vs IPv6, HTTP/1.1 vs HTTP/2, normal vs browser-like requests, redirects, verbose connection diagnostics, headers, response body, timings, and local notes.

The desktop application is based on the visual prototype kept in `blank/ui`.

## Current version

```text
0.0.1
```

## Main features

- runs the local Windows `curl.exe` rather than replacing it with another HTTP client;
- supports HEAD and GET presets;
- IPv4 / IPv6 selector;
- HTTP/1.1 / HTTP/2 selector;
- Verbose mode;
- Browser-like User-Agent + compression option;
- Redirect and raw-output options;
- Overview, Headers, Body, Debug, Timing and Command tabs;
- exact readable curl command shown before execution;
- response history grouped by domain and sorted newest first;
- SQLite local storage;
- notes stored per request;
- request execution runs off the UI thread;
- curl failures are preserved as diagnostic results;
- only `http://` and `https://` URLs are accepted.

## First-run sample

On an empty database Lanal creates one clearly marked **sample** history item for:

```text
https://novelcrow.com/
```

It reflects the initial investigation where the site returned a Cloudflare `403 Forbidden` page. The sample is not treated as current network data. Run the request from your own connection to create a real result.

The URL field also starts with `https://novelcrow.com/` so it can be used as the first live test.

## Requirements

- Windows 10 or Windows 11;
- Python 3.12+ recommended;
- `curl.exe` available in `PATH` (normally already included with current Windows 10/11);
- PySide6.

## Installation

Clone the repository and enter it:

```bat
git clone https://github.com/greenn/lanal.git
cd lanal
```

Create a virtual environment:

```bat
py -m venv .venv
.venv\Scripts\activate
```

Install dependencies:

```bat
python -m pip install -r requirements.txt
```

## Run

```bat
python run.py
```

On startup the status bar shows the detected curl version. If `curl.exe` is missing, the Run button is disabled.

## Recommended first test

1. Start Lanal.
2. Keep the default URL:

```text
https://novelcrow.com/
```

3. Run the default request.
4. Compare IPv4 and IPv6.
5. Enable `Verbose` and inspect the Debug tab.
6. Compare HTTP/1.1 and HTTP/2.
7. Open Headers and check values such as `server` and `cf-ray` when present.

For a direct command-line comparison outside Lanal you can also use:

```bat
curl -I https://novelcrow.com/
curl -v https://novelcrow.com/
curl -4 -v https://novelcrow.com/
curl -6 -v https://novelcrow.com/
curl -L -v https://novelcrow.com/
```

## Local data

Request history is stored in SQLite in the user's writable application-data area, normally similar to:

```text
%APPDATA%\Lanal\lanal.db
```

The database contains request metadata, captured headers/body/debug output, timings, commands, and notes.

The response display/storage limit is 5 MB per captured headers/body file in version 0.0.1.

## How curl is executed

The request options shown in the Command tab are passed to the real local curl executable with `shell=False`.

Lanal additionally adds temporary `--dump-header`, `--output`, and `--write-out` arguments internally so it can separate and display headers, body, and connection metrics. These capture arguments do not come from response content and are not interpreted through a shell.

## Tests

Tests are offline and do not depend on NovelCrow or another website being available.

Run:

```bat
python -m unittest discover -s tests -v
```

## Prototype UI

The HTML/CSS/JS visual prototype is retained in:

```text
blank/ui/
```

An additional layout reference is retained in:

```text
blank/ui0/
```

## Current limitations

- Windows is the primary target for 0.0.1;
- no geolocation lookup is performed for remote IPs;
- no automatic Cloudflare bypass behavior;
- no vulnerability scanning;
- no credential testing;
- no automatic retries;
- response content is displayed as untrusted text and is never executed as HTML/JavaScript.
