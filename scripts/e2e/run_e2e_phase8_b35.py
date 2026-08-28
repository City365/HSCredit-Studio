"""Phase 8 B35 Webhook 投递系统 — 端到端验收.

依据 docs/ROADMAP.md Phase 8 B35 验收矩阵:

| 验收项 | 测试方法 |
|---|---|
| B35-1 列出事件 | GET /webhooks/events → 13 个事件类型 |
| B35-2 创建订阅 | POST /webhooks/subscriptions → 含 secret |
| B35-3 列出订阅 | GET /webhooks/subscriptions → 含刚创建 |
| B35-4 签名验证工具 | POST /webhooks/verify-signature → valid=true |
| B35-5 订阅详情 | GET /webhooks/subscriptions/{id} |
| B35-6 更新订阅 | PATCH /webhooks/subscriptions/{id} → active=false |
| B35-7 测试 webhook | POST /webhooks/test (URL=httpbin 替代) |
| B35-8 签名不匹配 | verify-signature with wrong sig → valid=false |
| B35-9 发布事件 | POST /webhooks/publish → enqueued_count |
| B35-10 投递日志 | GET /webhooks/subscriptions/{id}/deliveries |
| B35-11 删除订阅 | DELETE /webhooks/subscriptions/{id} → 204 |
| B35-12 viewer 受限 | viewer 操作 → 可能 403/200 (端点权限配置) |

依赖: backend 启动在 8003 (避免占用 6002), 已执行 alembic upgrade head + seed.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE_URL = "http://localhost:8003"


def log(msg: str, status: str = "INFO") -> None:
    symbol = "✓" if status == "PASS" else ("❌" if status == "FAIL" else "ℹ")
    print(f"[{symbol}] {msg}")


def http_get(url: str, token: str | None = None) -> tuple[int, dict | str]:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else ""
        try:
            return e.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return e.code, raw


def http_post(url: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict | str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body or {}).encode("utf-8") if body is not None else b""
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else ""
        try:
            return e.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return e.code, raw


def http_patch(url: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict | str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body or {}).encode("utf-8") if body is not None else b""
    req = urllib.request.Request(url, data=data, headers=headers, method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else ""
        try:
            return e.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return e.code, raw


def http_delete(url: str, token: str | None = None) -> tuple[int, dict | str]:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else ""
        try:
            return e.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return e.code, raw


def login(email: str, password: str, tenant_slug: str) -> str:
    s, d = http_post(
        f"{BASE_URL}/api/v1/auth/login",
        {"email": email, "password": password, "tenant_slug": tenant_slug},
    )
    if s != 200 or not isinstance(d, dict):
        raise RuntimeError(f"Login failed: {s} {d}")
    return d["tokens"]["access_token"]


def main() -> int:
    print("=" * 60)
    print("🚀 Phase 8 B35 Webhook 投递系统 E2E 验收")
    print("=" * 60)

    results: dict[str, str] = {}

    try:
        admin_token = login("admin@demo.com", "DemoPass123!", "demo")
        viewer_token = login("viewer@demo.com", "DemoPass123!", "demo")
        log("登录成功 (admin/viewer)", "PASS")
    except Exception as e:
        log(f"登录失败: {e}", "FAIL")
        return 1

    # === 验收 1: 列出事件类型 ===
    try:
        s, d = http_get(
            f"{BASE_URL}/api/v1/demo/webhooks/events",
            admin_token,
        )
        if s == 200 and isinstance(d, dict) and d.get("total", 0) >= 13:
            events = [e["event"] for e in d.get("events", [])]
            log(f"事件类型: total={d['total']}, 含 run.completed={'run.completed' in events}", "PASS")
            results["B35-List Events"] = "PASS"
        else:
            log(f"列出事件失败: {s} {d}", "FAIL")
            results["B35-List Events"] = "FAIL"
    except Exception as e:
        log(f"列出事件异常: {e}", "FAIL")
        results["B35-List Events"] = "FAIL"

    # === 验收 2: 创建订阅 ===
    subscription_id = None
    subscription_secret = None
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/webhooks/subscriptions",
            {
                "url": f"https://httpbin.org/post/e2e-{int(time.time())}",
                "events": ["run.completed", "alert.fired"],
                "active": True,
                "description": "E2E B35 测试订阅",
            },
            admin_token,
        )
        if (
            s == 201
            and isinstance(d, dict)
            and d.get("subscription_id")
            and d.get("secret")
            and len(d["secret"]) == 64  # 32 字节 hex
        ):
            subscription_id = d["subscription_id"]
            subscription_secret = d["secret"]
            log(
                f"创建订阅: id={subscription_id[:8]}..., secret_len={len(d['secret'])}, events={d['events']}",
                "PASS",
            )
            results["B35-Create Subscription"] = "PASS"
        else:
            log(f"创建订阅失败: {s} {d}", "FAIL")
            results["B35-Create Subscription"] = "FAIL"
    except Exception as e:
        log(f"创建订阅异常: {e}", "FAIL")
        results["B35-Create Subscription"] = "FAIL"

    if not subscription_id:
        log("订阅未创建, 跳过后续", "FAIL")
        return 1

    # === 验收 3: 列出订阅 ===
    try:
        s, d = http_get(
            f"{BASE_URL}/api/v1/demo/webhooks/subscriptions",
            admin_token,
        )
        if (
            s == 200
            and isinstance(d, dict)
            and any(
                it["subscription_id"] == subscription_id
                for it in d.get("items", [])
            )
            # secret 不应在列表中泄露
            and all("secret" not in it or it.get("secret") is None for it in d.get("items", []))
        ):
            log(f"列出订阅: total={d['total']}, secret 未泄露 ✓", "PASS")
            results["B35-List Subscriptions"] = "PASS"
        else:
            log(f"列出订阅失败: {s} {d}", "FAIL")
            results["B35-List Subscriptions"] = "FAIL"
    except Exception as e:
        log(f"列出订阅异常: {e}", "FAIL")
        results["B35-List Subscriptions"] = "FAIL"

    # === 验收 4: 订阅详情 ===
    try:
        s, d = http_get(
            f"{BASE_URL}/api/v1/demo/webhooks/subscriptions/{subscription_id}",
            admin_token,
        )
        if s == 200 and isinstance(d, dict) and d.get("subscription_id") == subscription_id:
            log(f"订阅详情: url={d['url'][:40]}..., events={d['events']}", "PASS")
            results["B35-Get Subscription"] = "PASS"
        else:
            log(f"订阅详情失败: {s} {d}", "FAIL")
            results["B35-Get Subscription"] = "FAIL"
    except Exception as e:
        log(f"订阅详情异常: {e}", "FAIL")
        results["B35-Get Subscription"] = "FAIL"

    # === 验收 5: 签名验证工具 (正确签名) ===
    try:
        import base64
        import hashlib
        import hmac as _hmac

        ts = int(time.time())
        payload_str = '{"event":"run.completed"}'
        signed_payload = f"{ts}.".encode("utf-8") + payload_str.encode("utf-8")
        digest = _hmac.new(
            subscription_secret.encode("utf-8"),
            signed_payload,
            hashlib.sha256,
        ).hexdigest()
        sig = f"sha256={digest}"

        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/webhooks/verify-signature",
            {
                "secret": subscription_secret,
                "payload": payload_str,
                "signature": sig,
                "timestamp": ts,
            },
            admin_token,
        )
        if s == 200 and isinstance(d, dict) and d.get("valid") is True:
            log("签名验证 (正确签名) → valid=true ✓", "PASS")
            results["B35-Signature Verify"] = "PASS"
        else:
            log(f"签名验证失败: {s} {d}", "FAIL")
            results["B35-Signature Verify"] = "FAIL"
    except Exception as e:
        log(f"签名验证异常: {e}", "FAIL")
        results["B35-Signature Verify"] = "FAIL"

    # === 验收 6: 签名验证工具 (错误签名) ===
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/webhooks/verify-signature",
            {
                "secret": subscription_secret,
                "payload": '{"event":"run.completed"}',
                "signature": "sha256=" + "0" * 64,  # 错误签名
                "timestamp": int(time.time()),
            },
            admin_token,
        )
        if s == 200 and isinstance(d, dict) and d.get("valid") is False:
            log("签名验证 (错误签名) → valid=false ✓", "PASS")
            results["B35-Signature Invalid"] = "PASS"
        else:
            log(f"错误签名验证失败: {s} {d}", "FAIL")
            results["B35-Signature Invalid"] = "FAIL"
    except Exception as e:
        log(f"错误签名验证异常: {e}", "FAIL")
        results["B35-Signature Invalid"] = "FAIL"

    # === 验收 7: 发布事件 (匹配订阅) ===
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/webhooks/publish",
            {
                "event": "run.completed",
                "payload": {"run_id": "test-123", "status": "success"},
            },
            admin_token,
        )
        if (
            s == 200
            and isinstance(d, dict)
            and "event_id" in d
            and d.get("enqueued_count", 0) >= 1
        ):
            log(f"发布事件: enqueued={d['enqueued_count']}", "PASS")
            results["B35-Publish Event"] = "PASS"
        else:
            log(f"发布事件失败: {s} {d}", "FAIL")
            results["B35-Publish Event"] = "FAIL"
    except Exception as e:
        log(f"发布事件异常: {e}", "FAIL")
        results["B35-Publish Event"] = "FAIL"

    # === 验收 8: 投递日志 ===
    try:
        s, d = http_get(
            f"{BASE_URL}/api/v1/demo/webhooks/subscriptions/{subscription_id}/deliveries",
            admin_token,
        )
        if s == 200 and isinstance(d, dict) and d.get("total", 0) >= 1:
            items = d.get("items", [])
            log(f"投递日志: total={d['total']}, 第一条 status={items[0].get('status')}", "PASS")
            results["B35-Delivery Log"] = "PASS"
        else:
            log(f"投递日志失败: {s} {d}", "FAIL")
            results["B35-Delivery Log"] = "FAIL"
    except Exception as e:
        log(f"投递日志异常: {e}", "FAIL")
        results["B35-Delivery Log"] = "FAIL"

    # === 验收 9: 更新订阅 (停用) ===
    try:
        s, d = http_patch(
            f"{BASE_URL}/api/v1/demo/webhooks/subscriptions/{subscription_id}",
            {"active": False, "description": "已停用 - E2E 测试"},
            admin_token,
        )
        if (
            s == 200
            and isinstance(d, dict)
            and d.get("active") is False
            and d.get("description") == "已停用 - E2E 测试"
        ):
            log(f"更新订阅: active={d['active']}", "PASS")
            results["B35-Update Subscription"] = "PASS"
        else:
            log(f"更新订阅失败: {s} {d}", "FAIL")
            results["B35-Update Subscription"] = "FAIL"
    except Exception as e:
        log(f"更新订阅异常: {e}", "FAIL")
        results["B35-Update Subscription"] = "FAIL"

    # === 验收 10: viewer 受限 (可读, 写可能受限) ===
    try:
        s, d = http_get(
            f"{BASE_URL}/api/v1/demo/webhooks/events",
            viewer_token,
        )
        if s == 200:
            log("viewer 可列出事件 (读权限) ✓", "PASS")
            results["B35-Viewer Read"] = "PASS"
        else:
            log(f"viewer 期望 200, 实际 {s}", "FAIL")
            results["B35-Viewer Read"] = "FAIL"
    except Exception as e:
        log(f"viewer 异常: {e}", "FAIL")
        results["B35-Viewer Read"] = "FAIL"

    # === 验收 11: 删除订阅 ===
    try:
        s, _ = http_delete(
            f"{BASE_URL}/api/v1/demo/webhooks/subscriptions/{subscription_id}",
            admin_token,
        )
        if s == 204:
            log("删除订阅 → 204 ✓", "PASS")
            results["B35-Delete Subscription"] = "PASS"
        else:
            log(f"删除订阅期望 204, 实际 {s}", "FAIL")
            results["B35-Delete Subscription"] = "FAIL"
    except Exception as e:
        log(f"删除订阅异常: {e}", "FAIL")
        results["B35-Delete Subscription"] = "FAIL"

    # 汇总
    print("\n" + "=" * 60)
    print("📊 Phase 8 B35 Webhook 投递系统验收")
    print("=" * 60)
    pass_count = sum(1 for v in results.values() if v == "PASS")
    fail_count = len(results) - pass_count
    for k, v in results.items():
        symbol = "✅" if v == "PASS" else "❌"
        print(f"  {symbol} {k}: {v}")
    print("=" * 60)
    print(f"📈 总计: {pass_count} 通过 / {fail_count} 失败 / {len(results)} 项")
    print("=" * 60)

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
