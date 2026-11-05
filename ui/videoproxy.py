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
        # on_problem(url, status, reason): called from the proxy thread when every address of a
        # video was refused (status in REFUSED) or could not be reached (502), or the page gave up (0).
        self.on_problem = on_problem
        self._urls: OrderedDict[str, list[str]] = OrderedDict()
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
    def register(self, url, *more: str) -> str:
        """Local URL for one video: ``url`` (or a list) plus backup addresses, tried in order.

        Raises ValueError when none of them is on an allowed host.
        """
        candidates = list(url) if isinstance(url, (list, tuple)) else [url, *more]
        usable = []
        for candidate in candidates:
            if candidate and candidate not in usable and allowed(candidate, self.allowed_hosts):
                usable.append(candidate)
        if not usable:
            raise ValueError("只能代理学习通的视频地址")
        self.start()
        token = secrets.token_urlsafe(12)
        with self._lock:
            self._urls[token] = usable
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

    def _lookup(self, path: str) -> list[str] | None:
        if not path.startswith("/v/") and not path.startswith("/f/"):
            return None
        with self._lock:
            found = self._urls.get(path[3:].split("?", 1)[0])
        return list(found) if found else None

    def _promote(self, path: str, working: str) -> None:
        """The address that worked goes first, so the next Range request uses it straight away."""
        token = path[3:].split("?", 1)[0]
        with self._lock:
            urls = self._urls.get(token)
            if urls and urls[0] != working and working in urls:
                urls.remove(working)
                urls.insert(0, working)

    def _report(self, url: str, status: int, reason: str = "") -> None:
        if self.on_problem is not None:
            try:
                self.on_problem(url, status, reason)
            except Exception:  # noqa: BLE001 - a report must never break serving
                pass

    # ------------------------------------------------------------ upstream
    @staticmethod
    def _open_with(opener, url: str, headers: dict, head: bool):
        request = urllib.request.Request(url, headers=headers, method="HEAD" if head else "GET")
        try:
            resp = opener.open(request, timeout=20)  # noqa: S310 - allow-listed chaoxing URL
        except urllib.error.HTTPError as exc:
            resp = exc
        status = getattr(resp, "status", None) or resp.code

        def chunks():
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    return
                yield chunk

        return status, resp.headers, chunks(), resp.close

    def _open_system(self, url: str, headers: dict, head: bool):
        """Way 1, like the task process: the system proxy settings and the certifi certificates."""
        return self._open_with(_opener("system"), url, headers, head)

    def _open_direct(self, url: str, headers: dict, head: bool):
        """Way 2: no proxy at all, Windows' own certificate store."""
        return self._open_with(_opener("direct"), url, headers, head)

    def _upstream(self, url: str, headers: dict, head: bool):
        """Try both ways. Returns (opened, reason): opened is None when both failed."""
        reasons = []
        for opener in (self._open_system, self._open_direct):
            try:
                return opener(url, headers, head), ""
            except Exception as exc:  # noqa: BLE001 - every failure means: try the next way
                reasons.append(f"{type(exc).__name__}: {str(exc)[:80]}")
        return None, "；".join(reasons)

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
            urls = self._lookup(handler.path)
            if urls:
                self._report(urls[0], 0, "页面多次加载失败")
            handler.send_response(204)
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return
        urls = self._lookup(handler.path)
        if not urls:
            handler.send_error(404)
            return
        headers = {"Referer": self.referer, "User-Agent": USER_AGENT}
        for name in PASS_REQUEST:
            if handler.headers.get(name):
                headers[name] = handler.headers[name]

        # Each address in turn (each both ways: system settings + certifi, then direct); the first that answers is used.
        last_status, last_reason, opened = 502, "", None
        for url in urls:
            got, reason = self._upstream(url, headers, head)
            if got is None:
                last_status, last_reason = 502, reason
                continue
            status = got[0]
            if status in self.REFUSED or status >= 500:
                got[3]()
                last_status, last_reason = status, f"HTTP {status}"
                continue
            opened = got
            self._promote(handler.path, url)
            break
        if opened is None:
            self._report(urls[0], last_status if last_status in self.REFUSED else 502, last_reason)
            handler.send_error(last_status if last_status in self.REFUSED else 502)
            return

        status, upstream_headers, chunks, close = opened
        try:
            handler.send_response(status)
            for name in PASS_RESPONSE:
                value = upstream_headers.get(name)
                if value:
                    handler.send_header(name, value)
            if not upstream_headers.get("Content-Length"):
                handler.send_header("Connection", "close")
                handler.close_connection = True
            handler.end_headers()
            if head:
                return
            for chunk in chunks:
                handler.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass                         # the <video> element closed or seeked; normal
        except Exception:  # noqa: BLE001 - upstream dropped mid-stream: the page retries
            handler.close_connection = True
        finally:
            try:
                close()
            except Exception:  # noqa: BLE001
                pass


_OPENERS: dict = {}
_OPENERS_LOCK = threading.Lock()


def _opener(kind: str):
    """urllib openers for the two ways (built once). Kept free of requests: the GUI bundle would
    otherwise carry requests and its dependencies a second time."""
    with _OPENERS_LOCK:
        if kind not in _OPENERS:
            import ssl

            if kind == "system":
                try:
                    import certifi

                    context = ssl.create_default_context(cafile=certifi.where())
                except Exception:  # noqa: BLE001 - no certifi: the default store
                    context = ssl.create_default_context()
                handlers = [urllib.request.ProxyHandler(), urllib.request.HTTPSHandler(context=context)]
            else:
                handlers = [urllib.request.ProxyHandler({}),
                            urllib.request.HTTPSHandler(context=ssl.create_default_context())]
            _OPENERS[kind] = urllib.request.build_opener(*handlers)
        return _OPENERS[kind]
