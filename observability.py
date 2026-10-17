"""Observability and Sentry-compatible Ichnoscope SDK telemetry initialization."""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import sentry_sdk
import sentry_sdk.utils
from sentry_sdk.integrations.flask import FlaskIntegration
from urllib.parse import urlsplit

# Ensure Sentry DSN parser supports Ichnoscope project slugs (e.g. proj_c76fccfd95bd)
_orig_dsn_init = sentry_sdk.utils.Dsn.__init__


def _ichnoscope_dsn_init(self: Any, value: Any, org_id: Any = None) -> None:
    if isinstance(value, sentry_sdk.utils.Dsn):
        self.__dict__ = dict(value.__dict__)
        return
    try:
        _orig_dsn_init(self, value, org_id)
    except sentry_sdk.utils.BadDsn:
        parts = urlsplit(str(value))
        if parts.scheme not in ("http", "https") or not parts.hostname or not parts.username:
            raise
        self.scheme = parts.scheme
        self.host = parts.hostname
        self.org_id = org_id
        self.port = parts.port or (443 if self.scheme == "https" else 80)
        self.public_key = parts.username
        self.secret_key = parts.password
        segments = [s for s in parts.path.split("/") if s]
        if segments and segments[0] == "api":
            segments.pop(0)
        self.project_id = segments[-1] if segments else ""
        self.path = "/"


sentry_sdk.utils.Dsn.__init__ = _ichnoscope_dsn_init
try:
    import sentry_sdk.transport

    sentry_sdk.transport.Dsn.__init__ = _ichnoscope_dsn_init
except Exception:
    pass


def get_ichnoscope_dsn() -> str:
    """Resolve DSN for Ichnoscope / Sentry SDK from environment variables."""
    return (
        os.environ.get("ICHNOSCOPE_DSN", "").strip()
        or os.environ.get("SENTRY_DSN", "").strip()
    )


def get_environment() -> str:
    """Resolve environment tag from environment variables with fallback to production."""
    return (
        os.environ.get("ENVIRONMENT", "").strip()
        or os.environ.get("SENTRY_ENVIRONMENT", "").strip()
        or "production"
    )


def get_traces_sample_rate() -> float:
    """Resolve traces sample rate from environment variables, defaulting to 1.0 (or 0.1 for high-traffic)."""
    rate_str = os.environ.get("TRACES_SAMPLE_RATE", "").strip()
    if rate_str:
        try:
            return float(rate_str)
        except ValueError:
            pass
    return 1.0


def resolve_release_identifier() -> str:
    """Resolve full 40-character git commit SHA for release tracking."""
    env_rel = os.environ.get("RELEASE", "").strip()
    if env_rel:
        return env_rel
    try:
        raw_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if len(raw_sha) == 40:
            return raw_sha
    except Exception:  # noqa: BLE001
        pass
    return "0000000000000000000000000000000000000000"


def _capture_hook(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """Intercept error events and optionally mirror payload to local capture directory."""
    capture_dir = os.environ.get("CAPTURE_DIR")
    if capture_dir:
        out_dir = Path(capture_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        event_name = os.environ.get("CAPTURE_NAME", "captured_event")
        out_file = out_dir / f"{event_name}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(event, f, default=str, indent=2)
    return event


def init_observability() -> None:
    """Initialize Sentry-compatible Ichnoscope SDK before route handlers are loaded."""
    # Ensure fresh environment variables from .env are loaded
    try:
        from dotenv import load_dotenv

        load_dotenv(override=False)
    except ImportError:
        pass

    dsn = get_ichnoscope_dsn()
    release = resolve_release_identifier()
    environment = get_environment()
    traces_sample_rate = get_traces_sample_rate()

    sentry_sdk.init(
        dsn=dsn,
        release=release,
        environment=environment,
        traces_sample_rate=traces_sample_rate,
        send_default_pii=False,
        integrations=[FlaskIntegration()],
        in_app_include=["app", "routes", "services"],
        before_send=_capture_hook,
    )
    print(f"[Observability] Ichnoscope SDK initialized successfully (env: {environment}, traces: {traces_sample_rate})")


