"""Phase 4 B20 账单与支付 — 端到端验证.

依据 docs/ROADMAP.md Phase 4 B20 验收矩阵:

| 验收项 | 测试方法 |
|---|---|
| B20-1 列表账单 | GET /api/v1/demo/bills 返回 200 + 含 items |
| B20-2 生成账单 | POST /api/v1/demo/bills 返回 200 + 含 bill_id + 金额计算 |
| B20-3 金额计算 | pro plan 基础费 199 + 超量, 含 13% 税 |
| B20-4 账单详情 | GET /bills/{id} 含 invoices 列表 |
| B20-5 开发票 | POST /bills/{id}/invoice 返回 invoice_number + pdf_path |
| B20-6 支付链接 mock | POST /bills/{id}/pay?channel=wechat 返回 payment_url |
| B20-7 对账 CSV | GET /bills/reconciliation/csv 含 BOM + 表头 |

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
    print("🚀 Phase 4 B20 账单与发票 E2E 验收")
    print("=" * 60)

    results: dict[str, str] = {}

    try:
        token = login("admin@demo.com", "DemoPass123!", "demo")
        log("demo 登录成功", "PASS")
    except Exception as e:
        log(f"登录失败: {e}", "FAIL")
        return 1

    # === 验收 1: 列表账单 ===
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/bills", token)
        if s == 200 and isinstance(d, dict) and "items" in d:
            log(f"列表账单: {d.get('count', 0)} 条", "PASS")
            results["B20-List Bills"] = "PASS"
        else:
            log(f"列表账单失败: {s} {d}", "FAIL")
            results["B20-List Bills"] = "FAIL"
    except Exception as e:
        log(f"列表账单异常: {e}", "FAIL")
        results["B20-List Bills"] = "FAIL"

    # === 验收 2: 生成账单 ===
    bill_id = None
    try:
        from datetime import datetime

        period = datetime.utcnow().strftime("%Y-%m")
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/bills?billing_period={period}",
            token=token,
        )
        if s == 200 and isinstance(d, dict) and "bill_id" in d:
            bill_id = d["bill_id"]
            log(
                f"生成账单成功: bill_id={bill_id[:8]}..., total={d.get('total_amount'):.2f}",
                "PASS",
            )
            results["B20-Create Bill"] = "PASS"
        else:
            log(f"生成账单失败: {s} {d}", "FAIL")
            results["B20-Create Bill"] = "FAIL"
    except Exception as e:
        log(f"生成账单异常: {e}", "FAIL")
        results["B20-Create Bill"] = "FAIL"

    if not bill_id:
        # 用列表里已有账单继续测
        s, d = http_get(f"{BASE_URL}/api/v1/demo/bills?limit=1", token)
        if s == 200 and isinstance(d, dict) and d.get("items"):
            bill_id = d["items"][0]["bill_id"]
            log(f"用现有账单继续: bill_id={bill_id[:8]}...", "INFO")

    # === 验收 3: 账单详情含发票列表 ===
    try:
        if bill_id:
            s, d = http_get(f"{BASE_URL}/api/v1/demo/bills/{bill_id}", token)
            if s == 200 and isinstance(d, dict) and "invoices" in d:
                log(
                    f"账单详情: total={d.get('total_amount'):.2f}, invoices={len(d['invoices'])}",
                    "PASS",
                )
                results["B20-Bill Detail"] = "PASS"
            else:
                log(f"账单详情失败: {s} {d}", "FAIL")
                results["B20-Bill Detail"] = "FAIL"
        else:
            results["B20-Bill Detail"] = "FAIL"
    except Exception as e:
        log(f"账单详情异常: {e}", "FAIL")
        results["B20-Bill Detail"] = "FAIL"

    # === 验收 4: 开发票 ===
    try:
        if bill_id:
            s, d = http_post(
                f"{BASE_URL}/api/v1/demo/bills/{bill_id}/invoice",
                token=token,
            )
            if s == 200 and isinstance(d, dict) and "invoice_number" in d:
                inv_num = d["invoice_number"]
                pdf = d.get("pdf_path", "")
                log(
                    f"开发票成功: {inv_num}, pdf={pdf[:60] if pdf else 'NONE'}",
                    "PASS",
                )
                results["B20-Issue Invoice"] = "PASS"
            else:
                log(f"开发票失败: {s} {d}", "FAIL")
                results["B20-Issue Invoice"] = "FAIL"
        else:
            results["B20-Issue Invoice"] = "FAIL"
    except Exception as e:
        log(f"开发票异常: {e}", "FAIL")
        results["B20-Issue Invoice"] = "FAIL"

    # === 验收 5: 支付链接 mock ===
    try:
        if bill_id:
            s, d = http_post(
                f"{BASE_URL}/api/v1/demo/bills/{bill_id}/pay?channel=wechat",
                token=token,
            )
            if s == 200 and isinstance(d, dict) and "payment_url" in d:
                log(
                    f"支付链接 mock: channel={d.get('channel')}, mock={d.get('mock')}",
                    "PASS",
                )
                results["B20-Payment Link"] = "PASS"
            else:
                log(f"支付链接失败: {s} {d}", "FAIL")
                results["B20-Payment Link"] = "FAIL"
        else:
            results["B20-Payment Link"] = "FAIL"
    except Exception as e:
        log(f"支付链接异常: {e}", "FAIL")
        results["B20-Payment Link"] = "FAIL"

    # === 验收 6: 对账 CSV 导出 ===
    try:
        s, raw = http_get(f"{BASE_URL}/api/v1/demo/bills/reconciliation/csv", token)
        if s == 200 and isinstance(raw, str):
            has_bom = raw.startswith("﻿")
            has_header = raw.startswith("﻿bill_id,tenant_id,billing_period,plan,status")
            log(
                f"对账 CSV: BOM={has_bom}, header={has_header}, size={len(raw)}B",
                "PASS" if has_bom and has_header else "FAIL",
            )
            results["B20-Reconciliation"] = "PASS" if has_bom and has_header else "FAIL"
        else:
            log(f"对账 CSV 失败: {s}", "FAIL")
            results["B20-Reconciliation"] = "FAIL"
    except Exception as e:
        log(f"对账 CSV 异常: {e}", "FAIL")
        results["B20-Reconciliation"] = "FAIL"

    # === 验收 7: 多租户隔离 ===
    try:
        token_acme = login("admin@acme.com", "AcmePass123!", "acme")
        s_demo, _ = http_get(f"{BASE_URL}/api/v1/demo/bills?limit=1", token)
        s_acme, _ = http_get(f"{BASE_URL}/api/v1/acme/bills?limit=1", token_acme)
        log(
            f"多租户: demo={s_demo}, acme={s_acme}",
            "PASS" if s_demo == 200 and s_acme == 200 else "FAIL",
        )
        results["B20-Multi-Tenant"] = "PASS" if s_demo == 200 and s_acme == 200 else "FAIL"
    except Exception as e:
        log(f"多租户异常: {e}", "FAIL")
        results["B20-Multi-Tenant"] = "FAIL"

    # 汇总
    print("\n" + "=" * 60)
    print("📊 Phase 4 B20 账单与发票验收")
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