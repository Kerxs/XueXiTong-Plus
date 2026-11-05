# -*- coding: utf-8 -*-
"""Local video proxy for the read-only preview.

The preview page is loaded with WebView2's loadHtml(), which cannot give it a
chaoxing.com origin, so the browser sends no Referer and the video CDN refuses the
request. The proxy listens on 127.0.0.1 only and forwards the request with the
Referer / User-Agent the CDN expects, passing Range through so the <video> element
can stream and seek.

Only URLs the app registered are served (each under a random token) and only for
*.chaoxing.com / *.cldisk.com (the video CDN), so this is not an open proxy.
"""

from __future__ import annotations

import secrets
import threading
import urllib.error
import urllib.request
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

REFERER = "https://mooc1.chaoxing.com/ananas/modules/video/index.html?v=2025-0725-1842"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/118.0.0.0 Safari/537.36")
PASS_REQUEST = ("Range", "If-Range", "Accept")
PASS_RESPONSE = ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges", "Last-Modified", "ETag")
MAX_ENTRIES = 32
CHUNK = 256 * 1024


def allowed(url: str, hosts: tuple[str, ...]) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return parts.scheme in ("http", "https") and any(host == h or host.endswith("." + h) for h in hosts)


class _QuietServer(ThreadingHTTPServer):
    """The <video> element drops connections all the time (seeking, a new preview, the view being
    recreated); socketserver would print a traceback into gui.log for each one."""

    daemon_threads = True

    def handle_error(self, request, client_address):
        import sys

        if isinstance(sys.exc_info()[1], (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, TimeoutError)):
            return
        super().handle_error(request, client_address)


class VideoProxy:
    # Statuses that mean the video server will not serve this address any more (expired / gone):
    # the app then asks the task for a fresh one.
    REFUSED = (401, 403, 404, 410)

    def __init__(self, allowed_hosts: tuple[str, ...] = ("chaoxing.com", "cldisk.com"), referer: str = REFERER,
                 on_problem=None) -> None:
        self.allowed_hosts = allowed_hosts
        self.referer = referer
        # on_problem(url, status): called from the proxy thread when the video server refuses the
        # address (status in REFUSED) or cannot be reached twice in a row (status 502).
        self.on_problem = on_problem
        self._urls: OrderedDict[str, str] = OrderedDict()
        self._pages: OrderedDict[str, bytes] = OrderedDict()
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if self._server is not None:
            return
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_HEAD(self):
                proxy._serve(self, head=True)

            def do_GET(self):
                proxy._serve(self, head=False)

        self._server = _QuietServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, name="video-proxy", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    @property
    def port(self) -> int:
        return self._server.server_address[1] if self._server else 0

    # ------------------------------------------------------------ registry
    def register(self, url: str) -> str:
        """Local URL for ``url``; raises ValueError for hosts outside the allow-list."""
        if not allowed(url, self.allowed_hosts):
            raise ValueError("只能代理学习通的视频地址")
        self.start()
        token = secrets.token_urlsafe(12)
        with self._lock:
            self._urls[token] = url
            while len(self._urls) > MAX_ENTRIES:
                self._urls.popitem(last=False)
        return f"http://127.0.0.1:{self.port}/v/{token}"

    def register_page(self, html: str) -> str:
        """Serve a preview page from the proxy, so the WebView loads a real http URL.

        (WebView2 implements loadHtml() as a data: URL navigation, which is unreliable;
        a page on the same 127.0.0.1 origin as the proxied video just works.)
        """
        self.start()
        token = secrets.token_urlsafe(12)
        with self._lock:
            self._pages[token] = html.encode("utf-8")
            while len(self._pages) > MAX_ENTRIES:
                self._pages.popitem(last=False)
        return f"http://127.0.0.1:{self.port}/p/{token}"

    def _lookup(self, path: str) -> str | None:
        if not path.startswith("/v/"):
            return None
        with self._lock:
            return self._urls.get(path[3:].split("?", 1)[0])

    def _report(self, url: str, status: int) -> None:
        if self.on_problem is not None:
            try:
                self.on_problem(url, status)
            except Exception:  # noqa: BLE001 - a report must never break serving
                pass

    # ------------------------------------------------------------ forwarding
    def _serve(self, handler: BaseHTTPRequestHandler, head: bool) -> None:
        if handler.path.startswith("/p/"):
            with self._lock:
                page = self._pages.get(handler.path[3:].split("?", 1)[0])
            if page is None:
                handler.send_error(404)
                return
            handler.send_response(200)
            handler.send_header("Content-Type", "text/html; charset=utf-8")
            handler.send_header("Content-Length", str(len(page)))
            handler.send_header("Cache-Control", "no-store")
            handler.end_headers()
            if not head:
                handler.wfile.write(page)
            return
        if handler.path.startswith("/f/"):
            # The preview page failed several times in a row: let the app fetch a fresh address.
            with self._lock:
                failed = self._urls.get(handler.path[3:].split("?", 1)[0])
            if failed is not None:
                self._report(failed, 0)
            handler.send_response(204)
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return
        target = self._lookup(handler.path)
        if target is None:
            handler.send_error(404)
            return
        headers = {"Referer": self.referer, "User-Agent": USER_AGENT}
        for name in PASS_REQUEST:
            if handler.headers.get(name):
                headers[name] = handler.headers[name]
        upstream = None
        for attempt in range(2):         # a dropped / slow connection is tried once more
            request = urllib.request.Request(target, headers=headers, method="HEAD" if head else "GET")
            try:
                upstream = urllib.request.urlopen(request, timeout=20)  # noqa: S310 - allow-listed chaoxing URL
                break
            except urllib.error.HTTPError as exc:
                upstream = exc           # forward the CDN's status (e.g. 403 / 416)
                if exc.code in self.REFUSED:
                    self._report(target, exc.code)
                break
            except (urllib.error.URLError, TimeoutError, OSError):
                upstream = None
        if upstream is None:
            self._report(target, 502)
            handler.send_error(502)
            return
        with upstream:
            handler.send_response(upstream.status if hasattr(upstream, "status") else upstream.code)
            for name in PASS_RESPONSE:
                value = upstream.headers.get(name)
                if value:
                    handler.send_header(name, value)
            if not upstream.headers.get("Content-Length"):
                handler.send_header("Connection", "close")
                handler.close_connection = True
            handler.end_headers()
            if head:
                return
            try:
                while True:
                    chunk = upstream.read(CHUNK)
                    if not chunk:
                        break
                    handler.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass                     # the <video> element closed or seeked; normal
