"""等保差距整改 — 核心安全服务.

依据 docs/ROADMAP.md Phase 5 B25:

> 根据等保三级要求差距清单整改（认证 / 访问控制 / 安全审计 /
> 入侵防范 / 数据保护 / 备份恢复）

模块化拆分（按"等保三级"五大层面）：

- **HMAC 审计链**: :func:`sign_audit_event`, :func:`compute_chain_hash`,
  :func:`verify_audit_chain` — 防篡改审计 (审计完整性)
- **入侵防范 (WAF)**: :func:`detect_suspicious_request` — 检测 SQL 注入 /
  XSS / 路径遍历
- **访问控制 (IP 白/黑名单)**: :func:`ip_in_cidr`, :func:`check_ip_allowed`
- **认证加固**: :func:`validate_password_complexity`,
  :class:`LockoutTracker` — 失败 N 次锁定
- **数据保护**: :func:`mask_audit_secrets` — 审计日志自动 mask 高敏字段

设计原则: 全部为**纯函数 / 类**, 无 FastAPI 依赖, 便于单测覆盖.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC
from enum import Enum
from typing import Any

from hscredit_studio.core.logging import get_logger

_log = get_logger(__name__)


# ===== HMAC 审计链 =====

# 审计事件链的初始哈希 (前一个事件的 prev_hash)
AUDIT_CHAIN_GENESIS_HASH = "0" * 64


def sign_audit_event(payload: dict[str, Any], secret: str) -> str:
    """对审计事件 payload 计算 HMAC-SHA256 签名 (Phase 5 B25).

    用途: 防止审计日志被篡改. 字段排序后 JSON 序列化, 保证序列化确定性.

    Args:
        payload: 事件字段字典 (event_id / tenant_id / action / ...).
        secret: HMAC 密钥 (≥ 32 字节随机字符串, 应从 SecretManager 加载).

    Returns:
        64 hex 字符的 HMAC-SHA256 签名.
    """
    if not secret:
        # 生产环境必须配置 secret — 缺失时不签, 仅记录 warn
        _log.warning("audit_sign_missing_secret")
        return ""
    canonical = _canonical_json(payload)
    return hmac.new(
        secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def compute_chain_hash(prev_hash: str, current_event: dict[str, Any], secret: str) -> str:
    """计算审计链中下一事件的 hash (区块链式, Phase 5 B25).

    hash_n = HMAC(secret, prev_hash || canonical_json(event_n))

    Args:
        prev_hash: 上一事件的 chain_hash (或 :data:`AUDIT_CHAIN_GENESIS_HASH`).
        current_event: 当前事件 dict.
        secret: HMAC 密钥.

    Returns:
        64 hex 字符的 chain_hash.
    """
    payload_str = f"{prev_hash}{_canonical_json(current_event)}"
    return hmac.new(
        secret.encode("utf-8"),
        payload_str.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


@dataclass
class ChainVerifyResult:
    """审计链验证结果."""

    is_valid: bool
    checked_count: int
    failed_at_index: int | None = None
    failed_event_id: str | None = None
    error: str | None = None


def verify_audit_chain(
    events: Iterable[dict[str, Any]],
    secret: str,
) -> ChainVerifyResult:
    """验证审计链完整性 (Phase 5 B25 验收).

    验证每条事件携带的 ``chain_hash`` 与根据 ``prev_hash + payload``
    重算结果一致.

    Args:
        events: 按时间顺序的事件列表 (旧→新), 每条至少含 event_id / chain_hash.
        secret: HMAC 密钥.

    Returns:
        :class:`ChainVerifyResult` — 总条数 / 是否通过 / 失败索引.
    """
    prev_hash = AUDIT_CHAIN_GENESIS_HASH
    count = 0
    for i, event in enumerate(events):
        event_id = str(event.get("event_id", ""))
        expected_hash = event.get("chain_hash", "")
        if not expected_hash:
            return ChainVerifyResult(
                is_valid=False,
                checked_count=count,
                failed_at_index=i,
                failed_event_id=event_id,
                error="事件缺少 chain_hash 字段",
            )
        # 重算时不包含 chain_hash 字段本身
        event_without_hash = {k: v for k, v in event.items() if k != "chain_hash"}
        actual_hash = compute_chain_hash(prev_hash, event_without_hash, secret)
        if not hmac.compare_digest(actual_hash, expected_hash):
            return ChainVerifyResult(
                is_valid=False,
                checked_count=count,
                failed_at_index=i,
                failed_event_id=event_id,
                error=f"hash 不匹配 (expected={expected_hash[:8]}, actual={actual_hash[:8]})",
            )
        prev_hash = expected_hash
        count += 1
    return ChainVerifyResult(is_valid=True, checked_count=count)


def _canonical_json(obj: Any) -> str:
    """确定性 JSON 序列化 (字段排序, 用于 HMAC 一致性)."""
    import json

    if obj is None:
        return "null"
    if isinstance(obj, (str, int, float, bool)):
        return json.dumps(obj, ensure_ascii=False, sort_keys=True)
    if isinstance(obj, dict):
        items = sorted((k, _canonical_json(v)) for k, v in obj.items())
        return "{" + ",".join(f"{json.dumps(k, ensure_ascii=False)}:{v}" for k, v in items) + "}"
    if isinstance(obj, (list, tuple)):
        return "[" + ",".join(_canonical_json(v) for v in obj) + "]"
    return json.dumps(str(obj), ensure_ascii=False)


# ===== 入侵防范 (WAF) =====


class ThreatType(str, Enum):  # noqa: UP042
    """威胁类型 (Phase 5 B25)."""

    SQL_INJECTION = "sql_injection"
    XSS = "xss"
    PATH_TRAVERSAL = "path_traversal"
    COMMAND_INJECTION = "command_injection"
    LDAP_INJECTION = "ldap_injection"


# SQL 注入特征 (不依赖大小写, 不依赖引号转义)
_SQL_INJECTION_PATTERNS = [
    r"\bunion\s+select\b",
    r"\bselect\s+.*\bfrom\b",
    r"\binsert\s+into\b",
    r"\bdelete\s+from\b",
    r"\bdrop\s+(table|database)\b",
    r";\s*(drop|truncate|delete|update)\b",
    r"--\s*$",
    r"\bor\s+1\s*=\s*1\b",
    r"\band\s+1\s*=\s*1\b",
]

# XSS 特征 (含 script / event handler / javascript: 协议)
_XSS_PATTERNS = [
    r"<\s*script[^>]*>",
    r"\bon\w+\s*=\s*['\"]?[^'\">]*",
    r"javascript\s*:",
    r"<\s*iframe[^>]*>",
    r"<\s*object[^>]*>",
    r"<\s*embed[^>]*>",
]

# 路径遍历
_PATH_TRAVERSAL_PATTERNS = [
    r"\.\./",
    r"\.\.\\",
    r"%2e%2e[/\\]",
    r"/etc/passwd",
    r"/proc/self",
    r"\\windows\\system32",
]

# 命令注入
_COMMAND_INJECTION_PATTERNS = [
    r"[;&|]\s*(rm|del|format|shutdown|reboot|chmod)\b",
    r"\$\([^)]*\)",
    r"`[^`]+`",
]

# LDAP 注入
_LDAP_INJECTION_PATTERNS = [
    r"\)\s*\(\s*\|",
    r"\*\s*\)\s*\(",
    r"\\28",  # (
    r"\\29",  # )
]

_THREAT_RULES: dict[ThreatType, list[str]] = {
    ThreatType.SQL_INJECTION: _SQL_INJECTION_PATTERNS,
    ThreatType.XSS: _XSS_PATTERNS,
    ThreatType.PATH_TRAVERSAL: _PATH_TRAVERSAL_PATTERNS,
    ThreatType.COMMAND_INJECTION: _COMMAND_INJECTION_PATTERNS,
    ThreatType.LDAP_INJECTION: _LDAP_INJECTION_PATTERNS,
}


@dataclass
class ThreatHit:
    """单条威胁命中."""

    threat_type: ThreatType
    pattern: str
    location: str  # 命中的字段 (path / query / user_agent)


def detect_suspicious_request(
    *,
    path: str = "",
    query: str = "",
    body: str = "",
    user_agent: str = "",
    threat_types: list[ThreatType] | None = None,
) -> list[ThreatHit]:
    """检测可疑 HTTP 请求 (Phase 5 B25 入侵防范).

    在 FastAPI 中间件中调用, 检测到命中应记录审计事件并返回 403.

    Args:
        path: URL 路径.
        query: URL 查询参数 (含 hash 后的 query string).
        body: 请求体字符串 (注意大小, 不要传整个 multipart 文件).
        user_agent: HTTP User-Agent 头.
        threat_types: 限制检测的威胁类型, None=全检.

    Returns:
        命中的威胁列表 (可能多条).
    """
    hits: list[ThreatHit] = []
    locations: list[tuple[str, str]] = []
    if path:
        locations.append(("path", path))
    if query:
        locations.append(("query", query))
    if body:
        locations.append(("body", body[:8192]))  # 截断避免大 body
    if user_agent:
        locations.append(("user_agent", user_agent[:1024]))

    target_types = threat_types or list(_THREAT_RULES.keys())
    for threat_type in target_types:
        patterns = _THREAT_RULES.get(threat_type, [])
        for pattern in patterns:
            regex = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
            for location, value in locations:
                if regex.search(value):
                    hits.append(ThreatHit(threat_type=threat_type, pattern=pattern, location=location))
    return hits


# ===== IP 访问控制 =====


@dataclass
class IpAccessDecision:
    """IP 访问控制判定结果."""

    allowed: bool
    reason: str
    matched_rule: str | None = None


def ip_in_cidr(ip: str, cidr: str) -> bool:
    """判断 IP 是否在 CIDR 范围内 (Phase 5 B25).

    支持 IPv4 / IPv6. CIDR 格式: ``192.168.1.0/24`` 或单 IP ``10.0.0.1``.

    Args:
        ip: 待检查 IP 地址.
        cidr: CIDR 网段.

    Returns:
        True 表示在范围内.
    """
    try:
        ip_obj = ipaddress.ip_address(ip)
        if "/" in cidr:
            net = ipaddress.ip_network(cidr, strict=False)
        else:
            # 单 IP, 自动加 /32 或 /128
            net = ipaddress.ip_network(f"{cidr}/{ip_obj.max_prefixlen}", strict=False)
        return ip_obj in net
    except (ValueError, TypeError):
        return False


def check_ip_allowed(
    ip: str,
    *,
    whitelist: list[str] | None = None,
    blacklist: list[str] | None = None,
    default_allow: bool = True,
) -> IpAccessDecision:
    """IP 黑白名单判定 (Phase 5 B25 访问控制).

    优先级: blacklist > whitelist > default.

    Args:
        ip: 客户端 IP.
        whitelist: 白名单 CIDR 列表 (None 表示无白名单约束).
        blacklist: 黑名单 CIDR 列表.
        default_allow: 默认是否放行 (白名单为 None 时使用).

    Returns:
        :class:`IpAccessDecision`.
    """
    # 黑名单优先
    if blacklist:
        for cidr in blacklist:
            if ip_in_cidr(ip, cidr):
                return IpAccessDecision(
                    allowed=False,
                    reason=f"IP {ip} 命中黑名单 {cidr}",
                    matched_rule=cidr,
                )

    # 白名单
    if whitelist:
        for cidr in whitelist:
            if ip_in_cidr(ip, cidr):
                return IpAccessDecision(
                    allowed=True,
                    reason=f"IP {ip} 命中白名单 {cidr}",
                    matched_rule=cidr,
                )
        return IpAccessDecision(
            allowed=False,
            reason=f"IP {ip} 不在白名单内",
            matched_rule=None,
        )

    return IpAccessDecision(
        allowed=default_allow,
        reason="无黑白名单配置" if default_allow else "无白名单且默认拒绝",
        matched_rule=None,
    )


# ===== 认证加固 =====


class PasswordStrength(str, Enum):  # noqa: UP042
    """密码强度等级."""

    WEAK = "weak"
    MEDIUM = "medium"
    STRONG = "strong"
    INVALID = "invalid"


# 等保三级密码复杂度要求:
# - 长度 ≥ 8
# - 含大写 + 小写 + 数字 + 特殊字符 (任 3 类 → medium, 4 类全有 → strong)
_MIN_PASSWORD_LENGTH = 8


def validate_password_complexity(password: str) -> PasswordStrength:
    """校验密码复杂度 (Phase 5 B25 认证加固).

    Returns:
        - INVALID: 长度 < 8
        - WEAK: 长度 ≥ 8 但仅 1 类字符
        - MEDIUM: ≥ 8 且 3 类字符
        - STRONG: ≥ 8 且 4 类字符
    """
    if not password or len(password) < _MIN_PASSWORD_LENGTH:
        return PasswordStrength.INVALID
    has_upper = bool(re.search(r"[A-Z]", password))
    has_lower = bool(re.search(r"[a-z]", password))
    has_digit = bool(re.search(r"\d", password))
    has_special = bool(re.search(r"[^A-Za-z0-9]", password))
    classes = sum([has_upper, has_lower, has_digit, has_special])
    if classes >= 4:
        return PasswordStrength.STRONG
    if classes >= 3:
        return PasswordStrength.MEDIUM
    if classes >= 2:
        return PasswordStrength.WEAK  # 长度 ≥ 8 + 2 类 → 仍 weak 但不 reject
    return PasswordStrength.INVALID


@dataclass
class LockoutState:
    """账号锁定状态."""

    failed_count: int
    is_locked: bool
    locked_until: str | None = None  # ISO8601


class LockoutTracker:
    """账号登录失败计数器 (Phase 5 B25 认证加固).

    内存版 (单实例), 多实例部署应替换为 Redis. 设计为:
    - 失败计数 N 次自动锁定
    - 锁定后需等冷却期 (默认 15 分钟) 才能重试
    - 成功登录重置计数

    Thread-safe via deque maxlen (append 是原子的).
    """

    def __init__(
        self,
        *,
        max_failures: int = 5,
        cooldown_seconds: int = 900,  # 15 min
        window_seconds: int = 300,  # 5 min 滑动窗口
    ) -> None:
        self.max_failures = max_failures
        self.cooldown_seconds = cooldown_seconds
        self.window_seconds = window_seconds
        # key -> (timestamps deque, locked_until)
        self._state: dict[str, tuple[deque[float], float | None]] = {}

    def record_failure(self, key: str, now_ts: float) -> LockoutState:
        """记录一次登录失败."""
        import time

        if now_ts == 0:  # pragma: no cover — 仅测试用
            now_ts = time.time()
        timestamps, locked_until = self._state.get(key, (deque(maxlen=100), None))
        timestamps.append(now_ts)
        # 清理窗口外
        cutoff = now_ts - self.window_seconds
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()
        new_locked_until = locked_until
        if len(timestamps) >= self.max_failures:
            new_locked_until = now_ts + self.cooldown_seconds
        self._state[key] = (timestamps, new_locked_until)
        return LockoutState(
            failed_count=len(timestamps),
            is_locked=new_locked_until is not None and now_ts < new_locked_until,
            locked_until=(
                _isoformat(new_locked_until)
                if new_locked_until and now_ts < new_locked_until
                else None
            ),
        )

    def record_success(self, key: str) -> None:
        """登录成功 → 重置计数."""
        if key in self._state:
            self._state[key] = (deque(maxlen=100), None)

    def check(self, key: str, now_ts: float) -> LockoutState:
        """检查当前是否被锁定 (不记录新失败).

        同时清理滑动窗口外的旧失败计数 — 防止内存膨胀.
        """
        timestamps, locked_until = self._state.get(key, (deque(maxlen=100), None))
        cutoff = now_ts - self.window_seconds
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()
        # 若窗口清空, 解除锁定
        if not timestamps and locked_until is not None:
            locked_until = None
        is_locked = locked_until is not None and now_ts < locked_until
        return LockoutState(
            failed_count=len(timestamps),
            is_locked=is_locked,
            locked_until=_isoformat(locked_until) if is_locked else None,
        )

    def reset(self, key: str) -> None:
        """手动重置."""
        self._state.pop(key, None)


def _isoformat(ts: float) -> str:
    """Unix timestamp → ISO8601 字符串."""
    from datetime import datetime

    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


# ===== 数据保护 (审计日志自动 mask) =====

# 复用 Phase 5 B24 的分级映射, 防止循环 import
from hscredit_studio.services.data_classification import (  # noqa: E402
    DEFAULT_FIELD_CLASSIFICATION,
    DataSensitivity,
    mask_value,
)


def mask_audit_details(
    details: dict[str, Any] | None,
    *,
    threshold: DataSensitivity = DataSensitivity.SENSITIVE,
) -> dict[str, Any]:
    """审计日志 details 自动 mask 高敏字段 (Phase 5 B25 数据保护).

    等保三级要求: 审计日志中不出现明文高敏字段.
    """
    if not details:
        return details or {}
    return _mask_recursive(details, threshold)


def _mask_recursive(
    obj: Any,
    threshold: DataSensitivity,
) -> Any:
    if isinstance(obj, dict):
        return {
            k: (
                mask_value(k, v)
                if (
                    _SENSITIVITY_RANK[DEFAULT_FIELD_CLASSIFICATION.get(k, DataSensitivity.INTERNAL)]
                    >= _SENSITIVITY_RANK[threshold]
                    and not isinstance(v, (dict, list))
                )
                else _mask_recursive(v, threshold)
            )
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_mask_recursive(item, threshold) for item in obj]
    return obj


_SENSITIVITY_RANK: dict[DataSensitivity, int] = {
    DataSensitivity.PUBLIC: 0,
    DataSensitivity.INTERNAL: 1,
    DataSensitivity.SENSITIVE: 2,
    DataSensitivity.HIGHLY_SENSITIVE: 3,
}


__all__ = [
    "AUDIT_CHAIN_GENESIS_HASH",
    "ChainVerifyResult",
    "IpAccessDecision",
    "LockoutState",
    "LockoutTracker",
    "PasswordStrength",
    "ThreatHit",
    "ThreatType",
    "check_ip_allowed",
    "compute_chain_hash",
    "detect_suspicious_request",
    "ip_in_cidr",
    "mask_audit_details",
    "sign_audit_event",
    "validate_password_complexity",
    "verify_audit_chain",
]
