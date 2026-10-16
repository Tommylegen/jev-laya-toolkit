#!/usr/bin/env python3
"""Jev Dashboard — server lokal: menyajikan index.html dan mem-proxy request SystemOne.

Kenapa perlu proxy:
  Endpoint Jev (mis. opencode.ai/zen) tidak mengirim header CORS dan menolak
  preflight OPTIONS, jadi browser tidak bisa memanggilnya langsung dari origin lain.
  Proxy ini juga satu-satunya tempat yang sebaiknya memegang API key (env JEV_KEY).

Jalankan:
  python3 server.py                  # http://127.0.0.1:8791
  python3 server.py --port 9000
  JEV_KEY=sk-... python3 server.py   # key untuk provider ber-key (Zen paid, jevmodel.org)

Route:
  GET  /            -> index.html
  GET  /api/health  -> {"ok": true, "key_from_env": bool}
  POST /api/decide  -> {"url","model","body","key"?} -> forward `body` ke `url`,
                       balas body upstream verbatim + header X-Jev-Upstream-Ms,
                       X-Tokens-Remaining (diteruskan bila ada).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
UPSTREAM_TIMEOUT = 120
MAX_BODY = 16 * 1024 * 1024

# Key Laya self-host (dibuat oleh start-laya.sh). Dipakai otomatis HANYA untuk
# upstream loopback Laya, supaya route "Laya" di dashboard jalan tanpa mengisi key
# di browser. Upstream lain tidak pernah menerima key ini.
LAYA_KEY_FILE = Path(os.path.expanduser("~/.laya_key"))
LOOPBACK_LAYA_PREFIXES = ("http://127.0.0.1:8000/", "http://localhost:8000/")


def local_laya_key(url: str):
    if url.startswith(LOOPBACK_LAYA_PREFIXES) and LAYA_KEY_FILE.exists():
        return LAYA_KEY_FILE.read_text().strip() or None
    return None

# Cloudflare opencode.ai memblokir User-Agent default Python (error 1010
# "browser_signature_banned"), jadi proxy mengirim UA browser. Bisa di-override
# lewat env JEV_UA bila upstream lain justru mengharapkan UA sendiri.
USER_AGENT = os.environ.get(
    "JEV_UA",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
)


class Handler(BaseHTTPRequestHandler):
    server_version = "JevDashboard/1.0"

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}", flush=True)

    # ---------- helpers ----------
    def _send(self, status: int, body: bytes, ctype="application/json", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if "Cache-Control" not in (extra or {}):
            self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj, extra=None):
        self._send(status, json.dumps(obj).encode(), "application/json", extra)

    def _err(self, status: int, type_: str, message: str):
        self._json(status, {"error": {"type": type_, "message": message}})

    # ---------- routes ----------
    def do_GET(self):  # noqa: N802
        path = self.path.split("?")[0]
        if path in ("/", "/app.html", "/index.html"):
            # app.html = UI yang kita kelola sendiri; index.html dipertahankan sebagai cadangan.
            for name in ("app.html", "index.html") if path != "/index.html" else ("index.html", "app.html"):
                try:
                    html = (HERE / name).read_bytes()
                    return self._send(200, html, "text/html; charset=utf-8")
                except FileNotFoundError:
                    continue
            return self._err(500, "server_error", "app.html / index.html tidak ditemukan di folder ini.")
        if path == "/api/health":
            return self._json(200, {
                "ok": True,
                "key_from_env": bool(os.environ.get("JEV_KEY")),
                "laya_key_file": LAYA_KEY_FILE.exists(),
            })
        if path.startswith("/fonts/"):
            name = path[len("/fonts/"):]
            if not re.fullmatch(r"[a-z0-9._-]+\.woff2", name):
                return self._err(404, "not_found", "Font tidak dikenal.")
            try:
                data = (HERE / "fonts" / name).read_bytes()
            except FileNotFoundError:
                return self._err(404, "not_found", "Font tidak ada.")
            return self._send(200, data, "font/woff2", {"Cache-Control": "public, max-age=31536000, immutable"})
        return self._err(404, "not_found", "Rute tidak dikenal.")

    def do_POST(self):  # noqa: N802
        if self.path.split("?")[0] != "/api/decide":
            return self._err(404, "not_found", "Rute tidak dikenal.")
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if not 0 < n <= MAX_BODY:
                raise ValueError(f"ukuran body tidak wajar ({n} byte)")
            req = json.loads(self.rfile.read(n))
        except Exception as e:
            return self._err(400, "invalid_request_error", f"Body proxy tidak valid: {e}")

        url = (req.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            return self._err(400, "invalid_request_error", "url harus http(s)://")
        payload = req.get("body")
        if not isinstance(payload, dict):
            return self._err(400, "invalid_request_error", "field `body` (payload SystemOne) wajib ada.")
        if req.get("model"):
            payload = {**payload, "model": req["model"]}

        key = os.environ.get("JEV_KEY") or req.get("key") or local_laya_key(url)
        headers = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": USER_AGENT}
        if key:
            headers["Authorization"] = f"Bearer {key}"

        up = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(up, timeout=UPSTREAM_TIMEOUT) as r:
                raw, status, tok = r.read(), r.status, r.headers.get("X-Tokens-Remaining")
        except urllib.error.HTTPError as e:
            raw, status = e.read(), e.code
            tok = e.headers.get("X-Tokens-Remaining") if e.headers else None
        except Exception as e:
            return self._err(502, "proxy_error", f"Gagal menghubungi upstream: {e}")
        upstream_ms = round((time.perf_counter() - t0) * 1000)

        extra = {"X-Jev-Upstream-Ms": str(upstream_ms)}
        if tok:
            extra["X-Tokens-Remaining"] = tok
        ctype = "application/json"
        try:
            json.loads(raw)
        except Exception:
            ctype = "text/plain; charset=utf-8"
        self._send(status, raw, ctype, extra)


def main():
    ap = argparse.ArgumentParser(description="Jev Dashboard lokal (proxy SystemOne)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8791)
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(
        f"Jev Dashboard → http://{args.host}:{args.port} "
        f"(JEV_KEY={'set' if os.environ.get('JEV_KEY') else 'unset'})",
        flush=True,
    )
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
