"""Server tampilan kantor (tanpa dependency). Buka http://localhost:8000"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import db
from .config import CONFIG_DIR, UI_DIR


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, ctype="application/json", code=200):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            self._send((UI_DIR / "index.html").read_bytes(), "text/html")
        elif u.path == "/api/agents":
            self._send((CONFIG_DIR / "agents.json").read_bytes())
        elif u.path == "/api/events":
            if "recent" in qs:
                n = int(qs["recent"][0])
                rows = db.query("SELECT * FROM (SELECT * FROM events ORDER BY id DESC LIMIT ?) ORDER BY id", (n,))
            else:
                after = int(qs.get("after", ["0"])[0])
                rows = db.query("SELECT * FROM events WHERE id>? ORDER BY id LIMIT 100", (after,))
            self._send(rows)
        elif u.path == "/api/videos":
            self._send(db.query("SELECT id,idea,status,created_at FROM videos ORDER BY created_at DESC, id DESC LIMIT 20"))
        else:
            self._send({"error": "not found"}, code=404)

    def log_message(self, *a):
        pass


def serve(port=8000):
    db.init()
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Kantor AI jalan di http://localhost:{port}  (Ctrl+C untuk berhenti)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nBerhenti.")
