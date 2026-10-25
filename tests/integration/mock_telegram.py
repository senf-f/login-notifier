"""Minimal stand-in for the Telegram Bot API: appends each sendMessage text to a file."""
import json
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

OUT = sys.argv[1]


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        text = urllib.parse.parse_qs(body).get("text", [""])[0]
        with open(OUT, "a") as f:
            f.write(json.dumps({"path": self.path, "text": text}) + "\n")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true, "result": {}}')


HTTPServer(("127.0.0.1", 8081), Handler).serve_forever()
