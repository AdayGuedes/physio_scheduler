import hashlib
import secrets

from flask import abort, g, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import current_user
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from werkzeug.exceptions import HTTPException

from app.extensions import csrf, db, login_manager

ROLES = {"student": "client", "physio": "physio", "api": "physio"}
ERROR_CODES = {
    400: "invalid_request",
    401: "authentication_required",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    413: "request_too_large",
    429: "rate_limited",
    500: "internal_error",
    503: "unavailable",
}


def _login_email_digest():
    if request.mimetype not in {
        "application/x-www-form-urlencoded",
        "multipart/form-data",
    }:
        return None
    emails = request.form.getlist("email")
    if len(emails) != 1 or not 1 <= len(emails[0]) <= 254:
        return None
    normalized = emails[0].strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def login_limit_key():
    address = get_remote_address()
    digest = _login_email_digest()
    return f"{address}:{digest}" if digest else address


def login_account_limit_key():
    digest = _login_email_digest()
    return f"account:{digest}" if digest else f"ip:{get_remote_address()}"


def init_security(app):
    if not isinstance(app.secret_key, str) or not app.secret_key.strip():
        raise RuntimeError("Configure SECRET_KEY before starting the application.")
    if not app.config.get("TRUSTED_HOSTS"):
        raise RuntimeError("Configure at least one TRUSTED_HOSTS entry.")
    limiter = (
        Limiter(get_remote_address, app=app)
        if app.config.get("RATELIMIT_ENABLED", True)
        else None
    )
    if (
        limiter is not None
        and app.config.get("RATELIMIT_STORAGE_URI") == "memory://"
        and not app.debug
        and not app.testing
    ):
        app.logger.warning("Rate limits use per-process memory storage.")

    @app.before_request
    def protect_browser_routes():
        g.csp_nonce = secrets.token_urlsafe(16)
        role = ROLES.get(request.blueprint)
        if role is not None or request.endpoint == "auth.logout":
            if not current_user.is_authenticated:
                if request.blueprint == "api":
                    return {
                        "error": "Authentication required.",
                        "code": "authentication_required",
                    }, 401
                return login_manager.unauthorized()
            if role is not None and current_user.role != role:
                if request.blueprint == "api":
                    return {
                        "error": "Physiotherapist access required.",
                        "code": "forbidden",
                    }, 403
                abort(403)

    @app.before_request
    def validate_submitted_form():
        if (
            request.method not in {"POST", "PUT", "PATCH", "DELETE"}
            or request.endpoint is None
        ):
            return
        if request.blueprint == "api":
            return
        if request.mimetype not in {
            "application/x-www-form-urlencoded",
            "multipart/form-data",
        }:
            abort(400, description="Submit a form with valid fields.")
        if request.files:
            abort(400, description="File uploads are not supported.")
        if any("\x00" in value for value in request.form.values()):
            abort(400, description="Form fields must not contain NUL characters.")
        if len(request.form) > 50 or any(
            len(request.form.getlist(key)) != 1 for key in request.form
        ):
            abort(
                400, description="Submit each field only once, with at most 50 fields."
            )

    csrf.init_app(app)

    if limiter is not None:
        for endpoint, limit in [
            ("auth.login", "RATELIMIT_LOGIN"),
            ("auth.register", "RATELIMIT_REGISTER"),
        ]:
            options = (
                {
                    "key_func": login_limit_key,
                    "deduct_when": lambda response: response.status_code != 302,
                }
                if endpoint == "auth.login"
                else {}
            )
            app.view_functions[endpoint] = limiter.limit(
                app.config[limit], methods=["POST"], override_defaults=False, **options
            )(app.view_functions[endpoint])
        app.view_functions["auth.login"] = limiter.limit(
            app.config["RATELIMIT_LOGIN_ACCOUNT"],
            methods=["POST"],
            override_defaults=False,
            key_func=login_account_limit_key,
            deduct_when=lambda response: response.status_code != 302,
        )(app.view_functions["auth.login"])

    @app.context_processor
    def security_template_context():
        return {"csp_nonce": g.get("csp_nonce", "")}

    @app.after_request
    def set_security_headers(response):
        nonce = g.get("csp_nonce") or secrets.token_urlsafe(16)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net; "
            "style-src 'self' https://cdn.jsdelivr.net; "
            "img-src 'self' data:; font-src 'self' data:; connect-src 'self'; "
            "base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "private, no-store"
            response.vary.add("Cookie")
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.errorhandler(HTTPException)
    def safe_http_error(error):
        response = error.get_response()
        if request.path.startswith("/api/"):
            response.set_data(
                app.json.dumps(
                    {
                        "error": (
                            "Request limit exceeded."
                            if error.code == 429
                            else error.description
                        ),
                        "code": ERROR_CODES.get(error.code, "request_failed"),
                    }
                )
            )
            response.content_type = "application/json"
        return response

    @app.errorhandler(500)
    def safe_server_error(error):
        if request.path.startswith("/api/"):
            return {
                "error": "Unable to process the request.",
                "code": "internal_error",
            }, 500
        return "Unable to process the request. Please try again later.", 500

    @app.errorhandler(SQLAlchemyError)
    def safe_database_error(error):
        try:
            db.session.rollback()
        except SQLAlchemyError:
            app.logger.exception("Database rollback failed at %s", request.endpoint)
        app.logger.exception("Database error at %s", request.endpoint)
        if not isinstance(error, OperationalError):
            return safe_server_error(error)
        if request.path.startswith("/api/"):
            return {
                "error": "Data is temporarily unavailable.",
                "code": "unavailable",
            }, 503
        return "Data is temporarily unavailable. Please try again later.", 503
