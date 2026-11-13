import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


def parse_secure_cookie(value):
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("SESSION_COOKIE_SECURE must be a boolean value.")


def parse_trusted_hosts(value):
    return tuple(host.strip() for host in value.split(",") if host.strip())


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    ENABLE_DEV_SEED = os.environ.get("ENABLE_DEV_SEED") == "1"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = parse_secure_cookie(
        os.environ.get("SESSION_COOKIE_SECURE", "0")
    )
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    MAX_CONTENT_LENGTH = 256 * 1024
    MAX_FORM_MEMORY_SIZE = 256 * 1024
    MAX_FORM_PARTS = 50
    TRUSTED_HOSTS = parse_trusted_hosts(
        os.environ.get("TRUSTED_HOSTS") or "localhost,127.0.0.1,[::1]"
    )
    RATELIMIT_ENABLED = True
    RATELIMIT_DEFAULT = "120 per minute"
    RATELIMIT_LOGIN = "5 per minute;30 per hour"
    RATELIMIT_REGISTER = "5 per hour"
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI") or "memory://"
    RATELIMIT_HEADERS_ENABLED = True
