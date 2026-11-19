"""统一日志配置：backend/logs/diy.log，每日 24 小时轮转，文件/控制台双写。

轮转后旧文件命名为 diy.log_年月日（如 diy.log_20261119）。
控制台格式比文件更详细：额外带文件名、行号、函数名。
"""
from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent.parent.parent   # backend/
_LOG_DIR = _BASE_DIR / "logs"
_LOG_FILE = _LOG_DIR / "diy.log"

# 文件：精简，便于长期归档
_FILE_FORMAT = "%(asctime)s [%(levelname)s] %(name)s | %(message)s"
# 控制台：详细，带代码位置，便于开发排查
_CONSOLE_FORMAT = (
    "%(asctime)s [%(levelname)s] %(name)s "
    "%(filename)s:%(lineno)d %(funcName)s() | %(message)s"
)
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_initialized = False


def _backup_namer(path: str) -> str:
    """把 TimedRotatingFileHandler 的 diy.log.20261119 改成 diy.log_20261119。"""
    return path.replace("diy.log.", "diy.log_", 1)


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """初始化根日志；重复调用安全（热重载时会重置 handler）。"""
    global _initialized
    if _initialized:
        return logging.getLogger("diy")

    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    file_handler = TimedRotatingFileHandler(
        _LOG_FILE,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.suffix = "%Y%m%d"
    file_handler.namer = _backup_namer
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT, _DATE_FORMAT))

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT, _DATE_FORMAT))

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # uvicorn 访问日志是噪声：完全静音；错误级保留，便于排查故障
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False
    access.addHandler(logging.NullHandler())

    error = logging.getLogger("uvicorn.error")
    error.handlers.clear()
    error.propagate = True
    error.setLevel(logging.WARNING)

    _initialized = True
    logger = logging.getLogger("diy")
    logger.info("日志已初始化 -> %s（每日轮转，控制台详细输出）", _LOG_FILE)
    return logger
