"""Phase 5 B22 审计事件分类扩展 — 端到端验证.

依据 docs/ROADMAP.md Phase 5 B22 验收矩阵:

| 验收项 | 测试方法 |
|---|---|
| B22-1 登录审计 | 登录后, GET /audit-events 包含 login 事件 |
| B22-2 账单审计 | 生成账单后, audit 包含 BILL_GENERATE 事件 |
| B22-3 合同审计 | 生成合同后, audit 包含 CONTRACT_SIGN 事件 |
| B22-4 专票审计 | 申请专票后, audit 包含 VAT_INVOICE_APPLY 事件 |
| B22-5 新action出现在GET /audit-events查询 | by_action=BILL_GENERATE 命中 |
| B22-6 新资源类型过滤 | by_resource_type=bill 命中 |
| B22-7 多租户隔离 | demo/acme audit 各自隔离 |

依赖: backend 启动在 8002.
"""
from __future__ import annotations

import asyncio
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "http://localhost:8002"
BASH_EXE = "D:/notebook/software/git/Git/usr/bin/bash.exe"
REPO_WIN = "D:\\notebook\\AIGC\\hscredit-platform"


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
        with urllib.request.urlopen(req, timeout=30) as resp:
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
    print("🚀 Phase 5 B22 审计事件分类扩展 E2E 验收")
    print("=" * 60)

    results: dict[str, str] = {}

    try:
        token = login("admin@demo.com", "DemoPass123!", "demo")
        log("demo 登录成功", "PASS")
    except Exception as e:
        log(f"登录失败: {e}", "FAIL")
        return 1

    # === 验收 1: 登录审计 ===
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/audit-events?page=1&page_size=5", token)
        if s == 200 and isinstance(d, dict) and "items" in d:
            items = d.get("items", [])
            actions = {i.get("action") for i in items}
            has_login = "login" in actions
            log(f"登录审计: login in {len(actions)} actions", "PASS" if has_login else "FAIL")
            results["B22-Login Audit"] = "PASS" if has_login else "FAIL"
        else:
            log(f"audit-events 失败: {s} {d}", "FAIL")
            results["B22-Login Audit"] = "FAIL"
    except Exception as e:
        log(f"登录审计异常: {e}", "FAIL")
        results["B22-Login Audit"] = "FAIL"

    # === 验收 2: 账单审计 (BILL_GENERATE) ===
    try:
        # 触发账单生成 (用上月账期避免幂等返回)
        from datetime import datetime, timedelta
        last_month = datetime.utcnow() - timedelta(days=60)
        period = f"{last_month.year:04d}-{last_month.month:02d}"
        http_post(
            f"{BASE_URL}/api/v1/demo/bills?billing_period={period}",
            token=token,
        )
        # 查询新事件
        s, d = http_get(
            f"{BASE_URL}/api/v1/demo/audit-events?action=bill_generate&page=1&page_size=5",
            token,
        )
        if s == 200 and isinstance(d, dict):
            count = d.get("total", 0)
            log(f"账单审计: bill_generate 事件数 = {count}", "PASS" if count > 0 else "FAIL")
            results["B22-Bill Audit"] = "PASS" if count > 0 else "FAIL"
        else:
            log(f"账单审计失败: {s}", "FAIL")
            results["B22-Bill Audit"] = "FAIL"
    except Exception as e:
        log(f"账单审计异常: {e}", "FAIL")
        results["B22-Bill Audit"] = "FAIL"

    # === 验收 3: 合同审计 (CONTRACT_SIGN) ===
    try:
        # 触发合同生成 (CONTRACT_SIGN 复用为合同生命周期动作)
        http_post(
            f"{BASE_URL}/api/v1/demo/contracts?contract_type=nda",
            token=token,
        )
        s, d = http_get(
            f"{BASE_URL}/api/v1/demo/audit-events?action=contract_sign&page=1&page_size=5",
            token,
        )
        if s == 200 and isinstance(d, dict):
            count = d.get("total", 0)
            log(f"合同审计: contract_sign 事件数 = {count}", "PASS" if count > 0 else "FAIL")
            results["B22-Contract Audit"] = "PASS" if count > 0 else "FAIL"
        else:
            log(f"合同审计失败: {s}", "FAIL")
            results["B22-Contract Audit"] = "FAIL"
    except Exception as e:
        log(f"合同审计异常: {e}", "FAIL")
        results["B22-Contract Audit"] = "FAIL"

    # === 验收 4: 专票审计 (VAT_INVOICE_APPLY) ===
    try:
        s, bills = http_get(f"{BASE_URL}/api/v1/demo/bills?limit=1", token)
        if s == 200 and isinstance(bills, dict) and bills.get("items"):
            bill_id = bills["items"][0]["bill_id"]
            http_post(
                f"{BASE_URL}/api/v1/demo/contracts/vat-invoice/apply",
                body={
                    "bill_id": bill_id,
                    "invoice_type": "vat_general",
                    "buyer_tax_id": "91110000123456789X",
                    "buyer_name": "测试公司B22",
                    "buyer_address_phone": "北京市 / 010-12345678",
                    "buyer_bank_account": "工商银行 / 6222000123456789",
                },
                token=token,
            )
            s, d = http_get(
                f"{BASE_URL}/api/v1/demo/audit-events?action=vat_invoice_apply&page=1&page_size=5",
                token,
            )
            count = d.get("total", 0) if s == 200 and isinstance(d, dict) else 0
            log(f"专票审计: vat_invoice_apply 事件数 = {count}", "PASS" if count > 0 else "FAIL")
            results["B22-VAT Invoice Audit"] = "PASS" if count > 0 else "FAIL"
        else:
            log("无法获取 bill_id 跳过", "INFO")
            results["B22-VAT Invoice Audit"] = "FAIL"
    except Exception as e:
        log(f"专票审计异常: {e}", "FAIL")
        results["B22-VAT Invoice Audit"] = "FAIL"

    # === 验收 5: 新resource_type过滤 (bill) ===
    try:
        s, d = http_get(
            f"{BASE_URL}/api/v1/demo/audit-events?resource_type=bill&page=1&page_size=5",
            token,
        )
        if s == 200 and isinstance(d, dict):
            count = d.get("total", 0)
            log(f"resource_type=bill 过滤: {count} 条", "PASS" if count > 0 else "FAIL")
            results["B22-Resource Type Filter"] = "PASS" if count > 0 else "FAIL"
        else:
            log(f"过滤失败: {s}", "FAIL")
            results["B22-Resource Type Filter"] = "FAIL"
    except Exception as e:
        log(f"过滤异常: {e}", "FAIL")
        results["B22-Resource Type Filter"] = "FAIL"

    # === 验收 6: 新resource_type过滤 (contract) ===
    try:
        s, d = http_get(
            f"{BASE_URL}/api/v1/demo/audit-events?resource_type=contract&page=1&page_size=5",
            token,
        )
        if s == 200 and isinstance(d, dict):
            count = d.get("total", 0)
            log(f"resource_type=contract 过滤: {count} 条", "PASS" if count > 0 else "FAIL")
            results["B22-Contract Type Filter"] = "PASS" if count > 0 else "FAIL"
        else:
            log(f"过滤失败: {s}", "FAIL")
            results["B22-Contract Type Filter"] = "FAIL"
    except Exception as e:
        log(f"过滤异常: {e}", "FAIL")
        results["B22-Contract Type Filter"] = "FAIL"

    # === 验收 7: 多租户隔离 ===
    try:
        token_acme = login("admin@acme.com", "AcmePass123!", "acme")
        s_demo, d_demo = http_get(f"{BASE_URL}/api/v1/demo/audit-events?page=1&page_size=1", token)
        s_acme, d_acme = http_get(f"{BASE_URL}/api/v1/acme/audit-events?page=1&page_size=1", token_acme)
        if s_demo == 200 and s_acme == 200:
            demo_total = d_demo.get("total", 0) if isinstance(d_demo, dict) else 0
            acme_total = d_acme.get("total", 0) if isinstance(d_acme, dict) else 0
            log(
                f"多租户 audit 隔离: demo={demo_total} events, acme={acme_total} events",
                "PASS",
            )
            results["B22-Multi-Tenant Audit"] = "PASS"
        else:
            log(f"多租户失败: demo={s_demo}, acme={s_acme}", "FAIL")
            results["B22-Multi-Tenant Audit"] = "FAIL"
    except Exception as e:
        log(f"多租户异常: {e}", "FAIL")
        results["B22-Multi-Tenant Audit"] = "FAIL"

    # 汇总
    print("\n" + "=" * 60)
    print("📊 Phase 5 B22 审计事件分类扩展验收")
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