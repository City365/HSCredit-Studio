"""结构化日志配置（JSON 格式）."""

import logging
import sys
from datetime import UTC, datetime
from typing import Any

from pythonjsonlogger import jsonlogger

from hscredit_studio.core.config import settings


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """自定义 JSON 日志格式器."""

    def add_fields(self, log_record: dict[str, Any], record: logging.LogRecord, message_dict: dict[str, Any]) -> None:
        super().add_fields(log_record, record, message_dict)
        # 必备字段（用 datetime 而非 time.strftime 以支持微秒）
        log_record["timestamp"] = datetime.fromtimestamp(record.created, tz=UTC).isoformat()
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        log_record["service"] = settings.otel_service_name
        log_record["environment"] = settings.environment
        log_record["pathname"] = record.pathname
        log_record["lineno"] = record.lineno


def setup_logging(level: str = "INFO") -> None:
    """初始化日志配置."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        CustomJsonFormatter(
            "%(timestamp)s %(level)s %(name)s %(message)s",
            rename_fields={"levelname": "level"},
        )
    )

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level.upper())

    # 降低第三方库的日志级别
    logging.getLogger("uvicorn.access").setLevel("INFO")
    logging.getLogger("sqlalchemy.engine").setLevel("WARNING")
    logging.getLogger("celery").setLevel("INFO")


class KwargLogger:
    """薄包装让 logger 支持 kwargs（自动转 extra）.

    支持调用方式：``logger.info("event_name", key1=value1, key2=value2)``
    内部把 ``**kwargs`` 传给 ``logger.info(..., extra=kwargs)``。

    保留字段（``message`` / ``asctime`` / ``name`` / ``levelname`` 等）会从
    kwargs 中过滤掉，避免与 :class:`logging.LogRecord` 内置字段冲突。

    Phase 1 仅实现 :meth:`info` / :meth:`warning` / :meth:`error` / :meth:`debug`
    / :meth:`exception`；其他 logging 能力仍可通过 ``._logger`` 访问。
    """

    # logging.LogRecord 内置字段（不可作为 extra key 覆盖）
    _RESERVED_KEYS = frozenset(
        {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "message",
            "asctime",
        }
    )

    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def _call(self, method: str, msg: object, *args: Any, **kwargs: Any) -> Any:
        extra = {k: v for k, v in kwargs.items() if k not in self._RESERVED_KEYS}
        return getattr(self._logger, method)(msg, *args, extra=extra)

    def debug(self, msg: object, *args: Any, **kwargs: Any) -> Any:
        return self._call("debug", msg, *args, **kwargs)

    def info(self, msg: object, *args: Any, **kwargs: Any) -> Any:
        return self._call("info", msg, *args, **kwargs)

    def warning(self, msg: object, *args: Any, **kwargs: Any) -> Any:
        return self._call("warning", msg, *args, **kwargs)

    def error(self, msg: object, *args: Any, **kwargs: Any) -> Any:
        return self._call("error", msg, *args, **kwargs)

    def exception(self, msg: object, *args: Any, **kwargs: Any) -> Any:
        return self._logger.exception(msg, *args, exc_info=True, extra=kwargs)

    def critical(self, msg: object, *args: Any, **kwargs: Any) -> Any:
        return self._call("critical", msg, *args, **kwargs)

    @property
    def level(self) -> int:
        return self._logger.level


def get_logger(name: str) -> KwargLogger:
    """获取支持 kwargs 的 logger."""
    return KwargLogger(name)


# 测试日志输出是否正常
if __name__ == "__main__":
    setup_logging("DEBUG")
    log = get_logger("test")
    log.info("test message", extra={"user_id": "123", "tenant_id": "abc"})
    log.info("kwarg style", user_id="123", tenant_id="abc")
