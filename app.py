"""Serve the local EvidenceDesk UI and a small JSON API on loopback only."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import traceback
from urllib.parse import parse_qs, urlparse

from evidencedesk.agent import EvidenceAgent
from evidencedesk.config import ROOT, SETTINGS
from evidencedesk.llm import ModelUnavailable
from evidencedesk.tools import audit_claims

AGENT = None


class Handler(BaseHTTPRequestHandler):
    def send_json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            return self.send_json({"models": AGENT.models.health(),
                "corpus_size": len(AGENT.library.documents), "model": SETTINGS.model_name,
                "embedding": SETTINGS.embedding_name, "version": "1.0.0"})
        if parsed.path == "/api/library":
            return self.send_json({"documents": AGENT.library.public_documents()})
        if parsed.path == "/api/history":
            session = parse_qs(parsed.query).get("session_id", [""])[0]
            return self.send_json({"turns": AGENT.store.history(session)})
        static_root = (ROOT / "static").resolve()
        requested = "index.html" if parsed.path == "/" else parsed.path.lstrip("/")
        path = (static_root / requested).resolve()
        if not path.is_relative_to(static_root) or not path.is_file():
            return self.send_json({"error": "File not found."}, 404)
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(path))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 20_000:
                return self.send_json({"error": "Invalid request size."}, 400)
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("A JSON object is required.")
            if self.path == "/api/chat":
                session = str(payload.get("session_id", ""))
                if session and not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", session):
                    raise ValueError("Invalid conversation identifier.")
                return self.send_json(AGENT.ask(
                    payload.get("message", ""), session or None,
                    payload.get("mode", "agent"), payload.get("use_cache", True),
                ))
            if self.path == "/api/audit":
                claims = payload.get("claims", [])
                if not isinstance(claims, list) or len(claims) > 10 or not all(isinstance(c, dict) for c in claims):
                    raise ValueError("Provide a list of at most ten claims.")
                sources = [AGENT.library.by_id[i] for i in payload.get("source_ids", [])
                           if i in AGENT.library.by_id]
                return self.send_json(audit_claims(claims, sources))
            return self.send_json({"error": "Endpoint not found."}, 404)
        except (ValueError, TypeError, KeyError, UnicodeDecodeError) as error:
            return self.send_json({"error": str(error)}, 400)
        except ModelUnavailable as error:
            return self.send_json({"error": str(error)}, 503)
        except Exception:
            traceback.print_exc()
            self.log_error("Unexpected backend error")
            return self.send_json({"error": "The request could not be completed. Check the server log and retry."}, 500)

    def log_message(self, fmt, *args, **kwargs):
        print(f"[EvidenceDesk] {fmt % args}", flush=True)


def main():
    global AGENT
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    AGENT = EvidenceAgent()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"EvidenceDesk: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
