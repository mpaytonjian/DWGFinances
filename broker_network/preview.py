#!/usr/bin/env python3
"""Local preview for the DWG Broker Network artifact source.

Wraps index.html in the same page skeleton claude.ai adds at publish time,
writes it to .preview.html, and serves this directory so brokers.js and
logo.png resolve exactly as they do in the published artifact.

    python3 preview.py          ->  http://localhost:8765/.preview.html

The db ("Add Broker") and sample ("Ask AI") panels stay hidden locally; both
need the claude.ai runtime and appear only in the published artifact.
"""
import functools
import http.server
import pathlib
import socketserver

PORT = 8765
HERE = pathlib.Path(__file__).parent

SKELETON = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{ color-scheme: light dark; }}
  body {{ margin: 0; font: 14px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #fafaf9; }}
  img {{ max-width: 100%; }}
  [hidden] {{ display: none !important; }}
</style>
</head>
<body>
{page}
</body>
</html>
"""

page = (HERE / "index.html").read_text(encoding="utf-8")
(HERE / ".preview.html").write_text(SKELETON.format(page=page), encoding="utf-8")

handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(HERE))
socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("", PORT), handler) as httpd:
    print("Preview: http://localhost:%d/.preview.html   (Ctrl+C to stop)" % PORT)
    httpd.serve_forever()
