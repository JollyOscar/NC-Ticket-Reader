import logging
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOGGER_NAME = "office_ticket_backend"
_MAX_BYTES = 2_000_000
_BACKUP_COUNT = 5


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
