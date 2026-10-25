"""Production WSGI transport for the existing dashboard routes.

One authenticated owner workspace. This is deliberately not a multi-user service.
Local start.ps1 and the original HTTP API remain available without Flask.
"""
import base64
import binascii
import hmac
import io
import os
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, Response, request
from .server import APIError, DashboardRoutes, DashboardService, ROOT


class AccessPolicy:
    def __init__(self, origin="", username="", password=""):
        self.origin = origin.rstrip("/")
        self.username, self.password = username, password
        parsed = urlsplit(self.origin)
        if self.origin and (parsed.scheme != "https" or not parsed.hostname or parsed.username
                            or parsed.password or parsed.path or parsed.query or parsed.fragment):
            raise ValueError("VIGIL_PUBLIC_ORIGIN must be an HTTPS origin without a path or credentials.")
        if self.origin and (not username or ":" in username or len(password) < 20):
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
    policy = AccessPolicy(settings.get("VIGIL_PUBLIC_ORIGIN") or settings.get("RENDER_EXTERNAL_URL", ""),
                          settings.get("VIGIL_AUTH_USER", ""), settings.get("VIGIL_AUTH_PASSWORD", ""))
    storage = settings.get("VIGIL_DATA_DIR")
    database_url = settings.get("VIGIL_DATABASE_URL")
    if settings.get("VIGIL_REQUIRE_REMOTE_STORE") == "1" and not database_url:
        raise ValueError("Free hosted workspaces require VIGIL_DATABASE_URL so saves survive restarts.")
    app = Flask(__name__, static_folder=None)
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
        handler.rfile = io.BytesIO(request.get_data(cache=False)) if request.method == "POST" else io.BytesIO()
        getattr(handler, "do_" + request.method)()
        return handler.response

    @app.after_request
    def private_headers(response):
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    return app
