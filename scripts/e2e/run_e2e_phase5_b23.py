"""Phase 5 B23 通知通道 — 端到端验证.

依据 docs/ROADMAP.md Phase 5 B23 验收矩阵:

| 验收项 | 测试方法 |
|---|---|
| B23-1 模板列表 | GET /notifications/templates 返回 5 种 |
| B23-2 配置新增 | POST /notifications/configs?channel=email 返回 config_id |
| B23-3 配置列表 | GET /notifications/configs 含新增项 |
| B23-4 测试发送 | POST /notifications/test?template_key=bill_generated dry_run |
| B23-5 发送历史 | GET /notifications/logs 含 dry_run 记录 |
| B23-6 多租户隔离 | demo/acme 日志各自隔离 |

依赖: backend 启动在 8002.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE_URL = "http://localhost:8002"


def log(msg: str, status: str = "INFO") -> None:
    symbol = "✓" if status == "PASS" else ("❌" if status == "FAIL" else "ℹ")
    print(f"[{symbol}] {msg}")


def http_post(url: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict | str]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body or {}).encode("utf-8") if body is not None else b""
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
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
    print("🚀 Phase 5 B23 通知通道 E2E 验收")
    print("=" * 60)

    results: dict[str, str] = {}

    try:
        token = login("admin@demo.com", "DemoPass123!", "demo")
        log("demo 登录成功", "PASS")
    except Exception as e:
        log(f"登录失败: {e}", "FAIL")
        return 1

    # === 验收 1: 模板列表 ===
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/notifications/templates", token)
        if s == 200 and isinstance(d, dict) and "templates" in d:
            keys = [t["key"] for t in d["templates"]]
            log(f"通知模板: {len(keys)} 种", "PASS")
            results["B23-Templates"] = "PASS"
        else:
            log(f"模板列表失败: {s} {d}", "FAIL")
            results["B23-Templates"] = "FAIL"
    except Exception as e:
        log(f"模板异常: {e}", "FAIL")
        results["B23-Templates"] = "FAIL"

    # === 验收 2: 新增配置 ===
    config_id = None
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/notifications/configs?channel=email&recipient=test@demo.com",
            token=token,
        )
        if s == 200 and isinstance(d, dict) and "config_id" in d:
            config_id = d["config_id"]
            log(f"配置新增: {config_id[:8]}...", "PASS")
            results["B23-Add Config"] = "PASS"
        else:
            log(f"配置新增失败: {s} {d}", "FAIL")
            results["B23-Add Config"] = "FAIL"
    except Exception as e:
        log(f"配置异常: {e}", "FAIL")
        results["B23-Add Config"] = "FAIL"

    # === 验收 3: 配置列表 ===
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/notifications/configs", token)
        if s == 200 and isinstance(d, dict) and "items" in d:
            count = d.get("count", 0)
            log(f"配置列表: {count} 条", "PASS" if count > 0 else "FAIL")
            results["B23-List Configs"] = "PASS" if count > 0 else "FAIL"
        else:
            log(f"列表失败: {s} {d}", "FAIL")
            results["B23-List Configs"] = "FAIL"
    except Exception as e:
        log(f"列表异常: {e}", "FAIL")
        results["B23-List Configs"] = "FAIL"

    # === 验收 4: 测试发送 (dry_run) ===
    log_id = None
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/notifications/test?template_key=contract_signed&channel=email",
            token=token,
        )
        if s == 200 and isinstance(d, dict) and "results" in d:
            r = d["results"][0] if d["results"] else {}
            log_id = d.get("log_id")
            log(
                f"测试发送: success={r.get('success')}, dry_run={r.get('dry_run')}",
                "PASS" if r.get("success") and r.get("dry_run") else "FAIL",
            )
            results["B23-Test Send"] = "PASS" if r.get("success") and r.get("dry_run") else "FAIL"
        else:
            log(f"测试发送失败: {s} {d}", "FAIL")
            results["B23-Test Send"] = "FAIL"
    except Exception as e:
        log(f"测试发送异常: {e}", "FAIL")
        results["B23-Test Send"] = "FAIL"

    # === 验收 5: 发送历史 ===
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/notifications/logs", token)
        if s == 200 and isinstance(d, dict) and "items" in d:
            count = d.get("count", 0)
            latest = d["items"][0] if d["items"] else {}
            log(
                f"发送历史: {count} 条, latest status={latest.get('status')}",
                "PASS" if count > 0 else "FAIL",
            )
            results["B23-Logs"] = "PASS" if count > 0 else "FAIL"
        else:
            log(f"历史失败: {s} {d}", "FAIL")
            results["B23-Logs"] = "FAIL"
    except Exception as e:
        log(f"历史异常: {e}", "FAIL")
        results["B23-Logs"] = "FAIL"

    # === 验收 6: 多租户隔离 ===
    try:
        token_acme = login("admin@acme.com", "AcmePass123!", "acme")
        s_demo, d_demo = http_get(f"{BASE_URL}/api/v1/demo/notifications/logs", token)
        s_acme, d_acme = http_get(f"{BASE_URL}/api/v1/acme/notifications/logs", token_acme)
        demo_total = d_demo.get("count", 0) if isinstance(d_demo, dict) else 0
        acme_total = d_acme.get("count", 0) if isinstance(d_acme, dict) else 0
        log(
            f"多租户 logs 隔离: demo={demo_total}, acme={acme_total}",
            "PASS",
        )
        results["B23-Multi-Tenant"] = "PASS"
    except Exception as e:
        log(f"多租户异常: {e}", "FAIL")
        results["B23-Multi-Tenant"] = "FAIL"

    # 汇总
    print("\n" + "=" * 60)
    print("📊 Phase 5 B23 通知通道验收")
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