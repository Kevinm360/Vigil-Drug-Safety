"""Production WSGI transport for the existing dashboard routes.

Authenticated owner workspaces and optional isolated public visitor workspaces.
Local start.ps1 and the original HTTP API remain available without Flask.
"""
import base64
import binascii
import copy
import hmac
import io
import os
import re
import secrets
import threading
import time
from collections import deque
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, Response, g, request
from .server import APIError, DashboardRoutes, DashboardService, ROOT


class AccessPolicy:
    def __init__(self, origin="", username="", password="", public_demo=False):
        self.origin = origin.rstrip("/")
        self.username, self.password = username, password
        parsed = urlsplit(self.origin)
        if self.origin and (parsed.scheme != "https" or not parsed.hostname or parsed.username
                            or parsed.password or parsed.path or parsed.query or parsed.fragment):
            raise ValueError("VIGIL_PUBLIC_ORIGIN must be an HTTPS origin without a path or credentials.")
        if self.origin and not public_demo and (not username or ":" in username or len(password) < 20):
            raise ValueError("Hosted workspaces require VIGIL_AUTH_USER and VIGIL_AUTH_PASSWORD (at least 20 characters).")
        if bool(username) != bool(password):
            raise ValueError("Configure both workspace authentication variables together.")
        self.authority = parsed.netloc.lower()

    def check(self, headers, authenticate=True):
        host = headers.get("Host", "").lower()
        if self.origin:
            if host != self.authority:
                raise APIError("Unrecognized workspace host.", 403)
            if headers.get("Origin") and headers["Origin"].lower() != self.origin.lower():
                raise APIError("Cross-site requests are not allowed.", 403)
        else:
            host_name = host.split(":")[0]
            origin = urlsplit(headers.get("Origin", ""))
            if host_name not in {"localhost", "127.0.0.1"} or (origin.geturl() and
                    (origin.hostname not in {"localhost", "127.0.0.1"} or origin.scheme != "http")):
                raise APIError("Configure the hosted HTTPS origin before exposing this service.", 403)
        if not authenticate or not self.username:
            return
        try:
            scheme, token = headers.get("Authorization", "").split(" ", 1)
            if scheme.lower() != "basic":
                raise ValueError()
            username, password = base64.b64decode(token, validate=True).decode("utf-8").split(":", 1)
        except (ValueError, UnicodeDecodeError, binascii.Error):
            raise APIError("Sign in to this private workspace.", 401) from None
        valid_user = hmac.compare_digest(username.encode(), self.username.encode())
        valid_password = hmac.compare_digest(password.encode(), self.password.encode())
        if not (valid_user and valid_password):
            raise APIError("Sign in to this private workspace.", 401)


def create_app(settings=None, service=None):
    settings = dict(os.environ if settings is None else settings)
    demo = settings.get("VIGIL_PUBLIC_DEMO") == "1"
    visitors = settings.get("VIGIL_PUBLIC_VISITORS") == "1"
    if visitors and demo:
        raise ValueError("Choose public visitor workspaces or the read-only demo, not both.")
    if demo and (settings.get("VIGIL_AUTH_USER") or settings.get("VIGIL_AUTH_PASSWORD") or settings.get("VIGIL_DATABASE_URL")):
        raise ValueError("Public demo must use separate storage and no private workspace credentials or database.")
    if demo and not settings.get("VIGIL_PUBLIC_ORIGIN"):
        raise ValueError("Public demo requires an explicit HTTPS origin.")
    policy = AccessPolicy(settings.get("VIGIL_PUBLIC_ORIGIN") or settings.get("RENDER_EXTERNAL_URL", ""),
                          "" if visitors else settings.get("VIGIL_AUTH_USER", ""),
                          "" if visitors else settings.get("VIGIL_AUTH_PASSWORD", ""), demo or visitors)
    if visitors and not policy.origin:
        raise ValueError("Public visitor workspaces require an explicit HTTPS origin.")
    storage = settings.get("VIGIL_DATA_DIR")
    database_url = settings.get("VIGIL_DATABASE_URL")
    if settings.get("VIGIL_REQUIRE_REMOTE_STORE") == "1" and not database_url:
        raise ValueError("Free hosted workspaces require VIGIL_DATABASE_URL so saves survive restarts.")
    app = Flask(__name__, static_folder=None)
    demo_requests = deque()
    demo_lock = threading.Lock()
    demo_analysis = threading.BoundedSemaphore(1)
    app.config.update(MAX_CONTENT_LENGTH=2_000_000, PROPAGATE_EXCEPTIONS=False)
    app.extensions["vigil_service"] = service or DashboardService(storage_root=storage)
    app.extensions["vigil_service"].workspace_location = "hosted" if policy.origin else "local"
    if database_url:
        from .postgres_investigations import PostgresInvestigationStore
        from .server import validate_params
        app.extensions["vigil_service"].investigations = PostgresInvestigationStore(database_url, validate_params)
    if storage:
        Path(storage).mkdir(parents=True, exist_ok=True)
    # Fail startup if the mounted workspace cannot be initialized, rather than
    # reporting healthy and discovering a missing disk on the first save.
    app.extensions["vigil_service"].investigations.initialize()

    class WebRequest(DashboardRoutes):
        def __init__(self):
            self.command = request.method
            self.path = request.full_path.rstrip("?")
            self.headers = request.headers
            self.service = app.extensions["vigil_service"]
            self.static_dir = ROOT / "dist"
            self.response = None

        def allowed(self):
            policy.check(self.headers)

        def send_bytes(self, data, content_type, status=200, extra=None):
            headers = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
                       "X-Frame-Options": "DENY", "Cache-Control": "no-store" if
                       content_type.startswith("application/json") else "no-cache", **(extra or {})}
            if status == 401:
                headers["WWW-Authenticate"] = 'Basic realm="Vigil private workspace", charset="UTF-8"'
            self.response = Response(data, status=status, content_type=content_type, headers=headers)
            return self.response

    @app.route("/healthz", methods=["GET", "HEAD"], provide_automatic_options=False)
    def health():
        try:
            policy.check(request.headers, authenticate=False)
        except APIError as error:
            return {"status": "error", "error": str(error)}, error.status
        if not app.extensions["vigil_service"].investigations.healthy():
            return {"status": "unavailable"}, 503
        return {"status": "ok"}

    @app.route("/", defaults={"path": ""}, methods=["GET", "POST", "HEAD"], provide_automatic_options=False)
    @app.route("/<path:path>", methods=["GET", "POST", "HEAD"], provide_automatic_options=False)
    def dispatch(path):
        handler = WebRequest()
        # Authenticate before consuming a body or invoking any expensive FDA/model work.
        try:
            handler.allowed()
        except APIError as error:
            handler.send_json({"status": "error", "error": str(error)}, error.status)
            return handler.response
        if visitors:
            visitor = request.cookies.get("__Host-vigil-visitor", "")
            if not re.fullmatch(r"[0-9a-f]{64}", visitor):
                visitor = secrets.token_hex(32)
                g.new_visitor = visitor
        if path == "api/workspace-mode" and request.method in {"GET", "HEAD"}:
            handler.send_json({"public_demo": demo, "public_visitors": visitors})
            return handler.response
        if visitors and path.startswith("api/"):
            # FDA data/cache and training locks are shared; personal saved
            # research is selected solely from this browser's opaque cookie.
            handler.service = copy.copy(handler.service)
            handler.service.workspace_location = "visitor"
            from .server import validate_params
            if database_url:
                from .postgres_investigations import PostgresInvestigationStore
                handler.service.investigations = PostgresInvestigationStore(database_url, validate_params, "visitor:" + visitor)
            else:
                from .investigations import InvestigationStore
                visitor_root = Path(storage) if storage else ROOT / ".vigil-workspace"
                handler.service.investigations = InvestigationStore(visitor_root / "visitors" / visitor / "investigations.sqlite3", validate_params)
        if demo:
            if request.method not in {"GET", "HEAD"} or path.startswith("api/investigations"):
                handler.send_json({"error": "Public demo is read-only. Saved investigations, training and narrative submissions are available in the private workspace."}, 403)
                return handler.response
        acquired = False
        if (demo or visitors) and path.startswith("api/"):
            with demo_lock:
                now = time.monotonic()
                while demo_requests and demo_requests[0] <= now - 60:
                    demo_requests.popleft()
                limited = len(demo_requests) >= (120 if visitors else 60)
                if not limited:
                    demo_requests.append(now)
            expensive = demo or path in {"api/model/train", "api/narratives", "api/narratives/fetch"}
            acquired = not limited and expensive and demo_analysis.acquire(timeout=10)
            if limited or (expensive and not acquired):
                handler.send_json({"error": "The public workspace is busy. Please try again shortly."}, 429)
                handler.response.headers["Retry-After"] = "15"
                return handler.response
        handler.rfile = io.BytesIO(request.get_data(cache=False)) if request.method == "POST" else io.BytesIO()
        try:
            getattr(handler, "do_" + request.method)()
            return handler.response
        finally:
            if acquired:
                demo_analysis.release()

    @app.after_request
    def private_headers(response):
        if visitors and getattr(g, "new_visitor", None):
            response.set_cookie("__Host-vigil-visitor", g.new_visitor, max_age=180 * 86400,
                                secure=True, httponly=True, samesite="Lax", path="/")
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    return app
