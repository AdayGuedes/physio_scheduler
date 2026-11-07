import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    ENABLE_DEV_SEED = os.environ.get("ENABLE_DEV_SEED") == "1"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE") == "1"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    MAX_CONTENT_LENGTH = 256 * 1024
    MAX_FORM_MEMORY_SIZE = 256 * 1024
    MAX_FORM_PARTS = 50
    TRUSTED_HOSTS = tuple(
        host.strip()
        for host in (
            os.environ.get("TRUSTED_HOSTS") or "localhost,127.0.0.1,[::1]"
        ).split(",")
        if host.strip()
    )
    RATELIMIT_ENABLED = True
    RATELIMIT_DEFAULT = "120 per minute"
    RATELIMIT_LOGIN = "5 per minute;30 per hour"
    RATELIMIT_REGISTER = "5 per hour"
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI") or "memory://"
    RATELIMIT_HEADERS_ENABLED = True
