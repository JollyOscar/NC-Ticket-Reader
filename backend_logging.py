import logging
import os
import time
import uuid
from collections import deque
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterator, Optional

_LOGGER_NAME = "office_ticket_backend"
_MAX_BYTES = 2_000_000
_BACKUP_COUNT = 5

_sentry_configured = False


def get_log_path() -> Path:
    base_dir = Path(__file__).resolve().parent
    log_dir = base_dir / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "backend.log"


def get_logger(component: str) -> logging.Logger:
    root_logger = logging.getLogger(_LOGGER_NAME)
    root_logger.setLevel(logging.INFO)
    root_logger.propagate = False

    log_path = get_log_path()
    handler_exists = any(
        isinstance(handler, RotatingFileHandler)
        and Path(getattr(handler, "baseFilename", "")) == log_path
        for handler in root_logger.handlers
    )

    if not handler_exists:
        handler = RotatingFileHandler(
            log_path,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    return root_logger.getChild(component)


def tail_log_lines(max_lines: int = 200) -> str:
    log_path = get_log_path()
    if not log_path.exists():
        return ""

    with log_path.open("r", encoding="utf-8", errors="replace") as fh:
        lines = deque(fh, maxlen=max_lines)

    return "".join(lines)


def configure_sentry() -> bool:
    """Initialize the Sentry SDK for error tracking and performance monitoring.

    This is entirely optional: it only activates when the SENTRY_DSN
    environment variable is set, so the app behaves identically when Sentry
    is not configured. Safe to call multiple times (no-op after the first).
    """
    global _sentry_configured
    if _sentry_configured:
        return True

    sentry_dsn = os.getenv("SENTRY_DSN", "").strip()
    if not sentry_dsn:
        return False

    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=sentry_dsn,
            traces_sample_rate=0.1,  # 10% of transactions for performance monitoring
            environment=os.getenv("ENVIRONMENT", "production"),
        )
        _sentry_configured = True
        get_logger("sentry").info("sentry_configured environment=%s", os.getenv("ENVIRONMENT", "production"))
        return True
    except ImportError:
        get_logger("sentry").warning("sentry_sdk_not_installed dsn_set=true")
        return False
    except Exception as exc:  # pragma: no cover - defensive
        get_logger("sentry").warning("sentry_init_failed error=%s", exc)
        return False


def new_correlation_id() -> str:
    """Generate a short unique id to correlate a request/operation across
    log lines and, when running multiple replicas, across instances."""
    return uuid.uuid4().hex[:12]


@contextmanager
def log_performance(component: str, operation: str, slow_threshold_ms: int = 1000) -> Iterator[None]:
    """Context manager that times a block of code and logs its duration.

    Logs at WARNING level (with a "(slow)" marker) when the operation exceeds
    slow_threshold_ms, otherwise logs at INFO level. Re-raises any exception
    that occurs inside the block after logging its duration.
    """
    logger = get_logger(component)
    start = time.time()
    try:
        yield
    except Exception:
        elapsed_ms = (time.time() - start) * 1000
        logger.error(f"{operation} failed after {elapsed_ms:.0f}ms")
        raise
    else:
        elapsed_ms = (time.time() - start) * 1000
        if elapsed_ms > slow_threshold_ms:
            logger.warning(f"{operation} took {elapsed_ms:.0f}ms (slow)")
        else:
            logger.info(f"{operation} completed in {elapsed_ms:.0f}ms")


def log_error(
    component: str,
    message: str,
    exc: Optional[BaseException] = None,
    **context: object,
) -> None:
    """Log an error with structured context and, when Sentry is configured,
    capture it (along with a breadcrumb trail) for alerting.

    context kwargs are appended to the log line as key=value pairs and also
    attached as Sentry tags/extras when Sentry is active.
    """
    logger = get_logger(component)
    context_str = " ".join(f"{key}={value}" for key, value in context.items())
    full_message = f"{message} {context_str}".strip()

    if exc is not None:
        logger.error(f"{full_message} error={type(exc).__name__}: {exc}")
    else:
        logger.error(full_message)

    if not _sentry_configured:
        return

    try:
        import sentry_sdk

        sentry_sdk.add_breadcrumb(category=component, message=message, data=context, level="error")
        with sentry_sdk.push_scope() as scope:
            for key, value in context.items():
                scope.set_extra(key, value)
            scope.set_tag("component", component)
            if exc is not None:
                sentry_sdk.capture_exception(exc)
            else:
                sentry_sdk.capture_message(full_message, level="error")
    except Exception:  # pragma: no cover - never let telemetry break the app
        pass
