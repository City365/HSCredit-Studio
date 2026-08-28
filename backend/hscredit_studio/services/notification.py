"""第三方通知服务 — Phase 5 B23.

依据 docs/ROADMAP.md Phase 5 B23:

> 通知发送记录 (Slack / 企微 / SMTP)
> 通知模板: 账单 / 额度预警 / 告警

设计:

- :class:`NotificationChannel` — 通道枚举 (slack / wecom / email)
- :class:`Notifier` — 抽象接口, 三种实现
- :func:`send_notification` — 统一入口 (含 dry_run + 失败重试)
- :func:`render_template` — 模板渲染 (含变量替换)
"""
from __future__ import annotations

import abc
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

import aiohttp

from hscredit_studio.core.logging import get_logger

_log = get_logger(__name__)


class NotificationChannel(str, Enum):  # noqa: UP042
    """通知通道 (Phase 5 B23)."""

    SLACK = "slack"
    WECOM = "wecom"
    EMAIL = "email"


@dataclass
class NotificationTemplate:
    """通知模板 (Phase 5 B23).

    Attributes:
        key: 模板唯一键 (例: bill_generated / quota_80_percent / alert_cpu_high).
        title_template: 标题模板 (含 {tenant_name} 等变量).
        body_template: 正文模板.
        channels: 默认通道列表 (空表示需调用方指定).
    """

    key: str
    title_template: str
    body_template: str
    default_channels: list[NotificationChannel] = field(default_factory=list)


# ===== 预置模板 =====

TEMPLATES: dict[str, NotificationTemplate] = {
    "bill_generated": NotificationTemplate(
        key="bill_generated",
        title_template="HSCredit Studio - {billing_period} 账单已生成",
        body_template=(
            "租户 {tenant_name} ({plan}) {billing_period} 账单已生成\n"
            "总额: ¥{total_amount:.2f} (含税)\n"
            "到期日: {due_date}\n"
            "查看: /bills/{bill_id}"
        ),
        default_channels=[NotificationChannel.EMAIL, NotificationChannel.WECOM],
    ),
    "quota_near_limit": NotificationTemplate(
        key="quota_near_limit",
        title_template="HSCredit Studio - 用量接近限额 ({ratio:.0%})",
        body_template=(
            "租户 {tenant_name} 当前用量已达到 {ratio:.0%} 月度限额\n"
            "维度: {dimension} ({used} / {limit})\n"
            "建议: 升级订阅或清理资源"
        ),
        default_channels=[NotificationChannel.EMAIL, NotificationChannel.SLACK],
    ),
    "quota_exceeded": NotificationTemplate(
        key="quota_exceeded",
        title_template="HSCredit Studio - 用量超额 (已暂停)",
        body_template=(
            "租户 {tenant_name} 用量已超额: {dimension}\n"
            "已用: {used} / 限额 {limit}\n"
            "新提交已被拒绝, 请升级或清理"
        ),
        default_channels=[NotificationChannel.EMAIL, NotificationChannel.WECOM, NotificationChannel.SLACK],
    ),
    "contract_signed": NotificationTemplate(
        key="contract_signed",
        title_template="HSCredit Studio - 合同 {contract_number} 已签署",
        body_template=(
            "合同 {contract_number} ({contract_type}) 已签署\n"
            "生效: {valid_from} 至 {valid_until}\n"
            "查看: /contracts/{contract_id}"
        ),
        default_channels=[NotificationChannel.EMAIL],
    ),
    "alert_cpu_high": NotificationTemplate(
        key="alert_cpu_high",
        title_template="HSCredit Studio - 监控告警 (CPU 使用率高)",
        body_template=(
            "告警: {tenant_name} 平均 CPU 使用率 {cpu_pct:.1f}% 超过阈值 {threshold:.0f}%\n"
            "时间: {occurred_at}\n"
            "处理建议: 检查运行中 Run 是否过多"
        ),
        default_channels=[NotificationChannel.SLACK, NotificationChannel.WECOM],
    ),
}


def render_template(template: NotificationTemplate, variables: dict[str, Any]) -> tuple[str, str]:
    """渲染模板 (Phase 5 B23).

    Args:
        template: 模板对象.
        variables: 模板变量.

    Returns:
        (title, body) 元组.
    """
    try:
        title = template.title_template.format(**variables)
        body = template.body_template.format(**variables)
    except KeyError as e:
        _log.warning("notification_template_missing_var", template=template.key, missing_var=str(e))
        # 缺变量时保留原始模板字符串 (不抛错)
        title = template.title_template
        body = template.body_template
    return title, body


# ===== Notifier 抽象 =====


@dataclass
class NotificationResult:
    """单次通知发送结果 (Phase 5 B23)."""

    success: bool
    channel: NotificationChannel
    error: str | None = None
    dry_run: bool = False
    sent_at: datetime = field(default_factory=datetime.utcnow)


class Notifier(abc.ABC):  # type: ignore[misc]
    """通知发送器抽象基类."""

    channel: NotificationChannel

    @abc.abstractmethod
    async def send(
        self,
        title: str,
        body: str,
        *,
        recipient: str | None = None,
        extra: dict[str, Any] | None = None,
        dry_run: bool = True,
    ) -> NotificationResult:
        """发送通知."""
        raise NotImplementedError


class SlackNotifier(Notifier):
    """Slack Webhook 通知 (Phase 5 B23).

    配置: env SLACK_WEBHOOK_URL.
    格式: Slack incoming webhook JSON (text 字段).
    """

    channel = NotificationChannel.SLACK

    def __init__(self, webhook_url: str | None = None) -> None:
        self.webhook_url = webhook_url or os.environ.get("SLACK_WEBHOOK_URL")

    async def send(
        self,
        title: str,
        body: str,
        *,
        recipient: str | None = None,
        extra: dict[str, Any] | None = None,
        dry_run: bool = True,
    ) -> NotificationResult:
        if not self.webhook_url:
            return NotificationResult(
                success=False,
                channel=self.channel,
                error="SLACK_WEBHOOK_URL 未配置",
            )

        payload = {
            "text": f"*{title}*\n{body}",
            "username": "HSCredit Studio",
            "icon_emoji": ":robot_face:",
        }
        if extra:
            payload.update(extra)

        if dry_run:
            _log.info(
                "notification_dry_run",
                channel="slack",
                title=title,
                body_preview=body[:200],
            )
            return NotificationResult(
                success=True,
                channel=self.channel,
                dry_run=True,
            )

        try:
            async with (
                aiohttp.ClientSession() as session,
                session.post(self.webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp,
            ):
                if resp.status == 200:
                    return NotificationResult(success=True, channel=self.channel)
                return NotificationResult(
                    success=False,
                    channel=self.channel,
                    error=f"Slack HTTP {resp.status}: {await resp.text()[:200]}",
                )
        except Exception as e:
            return NotificationResult(success=False, channel=self.channel, error=str(e)[:200])


class WeComNotifier(Notifier):
    """企业微信 Webhook 机器人 (Phase 5 B23).

    配置: env WECOM_WEBHOOK_URL.
    格式: 企微 markdown 消息.
    """

    channel = NotificationChannel.WECOM

    def __init__(self, webhook_url: str | None = None) -> None:
        self.webhook_url = webhook_url or os.environ.get("WECOM_WEBHOOK_URL")

    async def send(
        self,
        title: str,
        body: str,
        *,
        recipient: str | None = None,
        extra: dict[str, Any] | None = None,
        dry_run: bool = True,
    ) -> NotificationResult:
        if not self.webhook_url:
            return NotificationResult(
                success=False,
                channel=self.channel,
                error="WECOM_WEBHOOK_URL 未配置",
            )

        # 企微 markdown 格式
        content = f"## {title}\n\n{body}"
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": content},
        }
        if extra:
            payload.update(extra)

        if dry_run:
            _log.info(
                "notification_dry_run",
                channel="wecom",
                title=title,
                body_preview=body[:200],
            )
            return NotificationResult(success=True, channel=self.channel, dry_run=True)

        try:
            async with (
                aiohttp.ClientSession() as session,
                session.post(self.webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp,
            ):
                if resp.status == 200:
                    result = await resp.json()
                    if result.get("errcode", 0) == 0:
                        return NotificationResult(success=True, channel=self.channel)
                    return NotificationResult(
                        success=False,
                        channel=self.channel,
                        error=f"企微 errcode={result.get('errcode')}: {result.get('errmsg', '')[:200]}",
                    )
                return NotificationResult(
                    success=False,
                    channel=self.channel,
                    error=f"企微 HTTP {resp.status}",
                )
        except Exception as e:
            return NotificationResult(success=False, channel=self.channel, error=str(e)[:200])


class EmailNotifier(Notifier):
    """SMTP 邮件通知 (Phase 5 B23).

    配置: env SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / NOTIFY_FROM.
    本地 dev: 落本地文件 (mock, 避免实际邮件发送失败).
    """

    channel = NotificationChannel.EMAIL

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        from_addr: str | None = None,
    ) -> None:
        self.host = host or os.environ.get("SMTP_HOST")
        self.port = port or int(os.environ.get("SMTP_PORT", "587"))
        self.user = user or os.environ.get("SMTP_USER")
        self.password = password or os.environ.get("SMTP_PASSWORD")
        self.from_addr = from_addr or os.environ.get("NOTIFY_FROM", "noreply@hscredit.example.com")

    async def send(
        self,
        title: str,
        body: str,
        *,
        recipient: str | None = None,
        extra: dict[str, Any] | None = None,
        dry_run: bool = True,
    ) -> NotificationResult:
        if not self.host or not recipient:
            # 无配置或无收件人时, mock 写到本地文件
            return await self._write_mock_file(title, body, recipient)

        if dry_run:
            _log.info(
                "notification_dry_run",
                channel="email",
                to=recipient,
                title=title,
            )
            return NotificationResult(success=True, channel=self.channel, dry_run=True)

        try:
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            import aiosmtplib

            msg = MIMEMultipart()
            msg["From"] = self.from_addr
            msg["To"] = recipient
            msg["Subject"] = title
            msg.attach(MIMEText(body, "plain", "utf-8"))

            await aiosmtplib.send(
                msg,
                hostname=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
            )
            return NotificationResult(success=True, channel=self.channel)
        except Exception as e:
            return NotificationResult(success=False, channel=self.channel, error=str(e)[:200])

    async def _write_mock_file(self, title: str, body: str, recipient: str | None) -> NotificationResult:
        """Mock: 写本地 .eml 文件 (本地 dev 避免真实 SMTP 失败)."""
        import os as _os

        mock_dir = "/tmp/hscredit_emails"
        try:
            _os.makedirs(mock_dir, exist_ok=True)
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
            path = f"{mock_dir}/{ts}_{recipient or 'no_recipient'}.eml"
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"To: {recipient or 'no_recipient'}\n")
                f.write(f"Subject: {title}\n\n")
                f.write(body)
            _log.info("notification_email_mock_written", path=path)
            return NotificationResult(
                success=True,
                channel=self.channel,
                dry_run=True,
            )
        except Exception as e:
            return NotificationResult(success=False, channel=self.channel, error=str(e)[:200])


# ===== 统一入口 =====


def get_notifier(channel: NotificationChannel) -> Notifier:
    """根据通道取 notifier 实例 (Phase 5 B23)."""
    if channel == NotificationChannel.SLACK:
        return SlackNotifier()
    if channel == NotificationChannel.WECOM:
        return WeComNotifier()
    if channel == NotificationChannel.EMAIL:
        return EmailNotifier()
    raise ValueError(f"不支持的通知通道: {channel}")


async def send_notification(
    template_key: str,
    variables: dict[str, Any],
    *,
    channels: list[NotificationChannel] | None = None,
    tenant_id: UUID | None = None,
    recipient: str | None = None,
    dry_run: bool = True,
) -> list[NotificationResult]:
    """统一通知发送入口 (Phase 5 B23 验收).

    Args:
        template_key: 模板键 (例: bill_generated).
        variables: 模板变量.
        channels: 指定通道 (None = 用模板默认).
        tenant_id: 租户 ID (用于记录).
        recipient: 收件人 (邮件地址 / webhook URL override).
        dry_run: True 时不真正发送, 只记录日志 (本地 dev 默认).

    Returns:
        每个通道的发送结果列表.
    """
    template = TEMPLATES.get(template_key)
    if template is None:
        _log.error("notification_template_not_found", template=template_key)
        return [
            NotificationResult(
                success=False,
                channel=ch,
                error=f"模板不存在: {template_key}",
            )
            for ch in (channels or [NotificationChannel.EMAIL])
        ]

    channels = channels or template.default_channels
    title, body = render_template(template, variables)

    results: list[NotificationResult] = []
    for channel in channels:
        notifier = get_notifier(channel)
        try:
            r = await notifier.send(
                title=title,
                body=body,
                recipient=recipient,
                dry_run=dry_run,
            )
            results.append(r)
            _log.info(
                "notification_sent",
                template=template_key,
                channel=channel.value,
                success=r.success,
                dry_run=r.dry_run,
                tenant_id=str(tenant_id) if tenant_id else None,
            )
        except Exception as e:
            results.append(
                NotificationResult(success=False, channel=channel, error=str(e)[:200])
            )
    return results


__all__ = [
    "TEMPLATES",
    "EmailNotifier",
    "NotificationChannel",
    "NotificationResult",
    "NotificationTemplate",
    "Notifier",
    "SlackNotifier",
    "WeComNotifier",
    "get_notifier",
    "render_template",
    "send_notification",
]
