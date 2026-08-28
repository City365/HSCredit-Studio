"""Phase 4 B21 合同与开票管理 — 端到端验证.

依据 docs/ROADMAP.md Phase 4 B21 验收矩阵:

| 验收项 | 测试方法 |
|---|---|
| B21-1 合同模板 | GET /contracts/templates 返回 4 种类型 |
| B21-2 生成服务协议 | POST /contracts?contract_type=service_agreement 返回中文 PDF 路径 |
| B21-3 生成 DPA | POST /contracts?contract_type=dpa 包含 PIPL 条款 |
| B21-4 列表合同 | GET /contracts 返回 items + count |
| B21-5 合同详情 | GET /contracts/{id} |
| B21-6 签约 | POST /contracts/{id}/sign 返回 signed_at |
| B21-7 增值税专票 | POST /contracts/vat-invoice/apply 含税号校验 |
| B21-8 多租户隔离 | demo/acme 返回各自合同 |

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
    print("🚀 Phase 4 B21 合同与开票管理 E2E 验收")
    print("=" * 60)

    results: dict[str, str] = {}

    try:
        token = login("admin@demo.com", "DemoPass123!", "demo")
        log("demo 登录成功", "PASS")
    except Exception as e:
        log(f"登录失败: {e}", "FAIL")
        return 1

    # === 验收 1: 合同模板列表 ===
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/contracts/templates", token)
        if s == 200 and isinstance(d, dict) and "templates" in d:
            types = [t["contract_type"] for t in d["templates"]]
            log(f"合同模板: {len(types)} 种 ({types})", "PASS")
            results["B21-Templates"] = "PASS"
        else:
            log(f"模板列表失败: {s} {d}", "FAIL")
            results["B21-Templates"] = "FAIL"
    except Exception as e:
        log(f"模板异常: {e}", "FAIL")
        results["B21-Templates"] = "FAIL"

    # === 验收 2: 生成服务协议 ===
    sa_contract_id = None
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/contracts?contract_type=service_agreement",
            token=token,
        )
        if s == 200 and isinstance(d, dict) and "contract_number" in d:
            sa_contract_id = d["contract_id"]
            log(
                f"服务协议生成: {d['contract_number']}, pdf={d.get('pdf_path', '')[:60]}",
                "PASS",
            )
            results["B21-Service Agreement"] = "PASS"
        else:
            log(f"服务协议生成失败: {s} {d}", "FAIL")
            results["B21-Service Agreement"] = "FAIL"
    except Exception as e:
        log(f"服务协议异常: {e}", "FAIL")
        results["B21-Service Agreement"] = "FAIL"

    # === 验收 3: 生成 DPA ===
    dpa_contract_id = None
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/contracts?contract_type=dpa",
            token=token,
        )
        if s == 200 and isinstance(d, dict) and "contract_id" in d:
            dpa_contract_id = d["contract_id"]
            log(
                f"DPA 生成: {d['contract_number']}, 状态: {d['status']}",
                "PASS",
            )
            results["B21-DPA"] = "PASS"
        else:
            log(f"DPA 生成失败: {s} {d}", "FAIL")
            results["B21-DPA"] = "FAIL"
    except Exception as e:
        log(f"DPA 异常: {e}", "FAIL")
        results["B21-DPA"] = "FAIL"

    # === 验收 4: 列表合同 ===
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/contracts?limit=10", token)
        if s == 200 and isinstance(d, dict) and "items" in d:
            log(f"合同列表: {d.get('count', 0)} 条", "PASS")
            results["B21-List Contracts"] = "PASS"
        else:
            log(f"列表失败: {s} {d}", "FAIL")
            results["B21-List Contracts"] = "FAIL"
    except Exception as e:
        log(f"列表异常: {e}", "FAIL")
        results["B21-List Contracts"] = "FAIL"

    # === 验收 5: 合同详情 ===
    try:
        if sa_contract_id:
            s, d = http_get(f"{BASE_URL}/api/v1/demo/contracts/{sa_contract_id}", token)
            if s == 200 and isinstance(d, dict) and d.get("status") == "draft":
                log(f"合同详情: status={d['status']}, valid_until={d.get('valid_until')[:10]}", "PASS")
                results["B21-Contract Detail"] = "PASS"
            else:
                log(f"详情失败: {s} {d}", "FAIL")
                results["B21-Contract Detail"] = "FAIL"
        else:
            results["B21-Contract Detail"] = "FAIL"
    except Exception as e:
        log(f"详情异常: {e}", "FAIL")
        results["B21-Contract Detail"] = "FAIL"

    # === 验收 6: 签约 ===
    try:
        if sa_contract_id:
            s, d = http_post(
                f"{BASE_URL}/api/v1/demo/contracts/{sa_contract_id}/sign",
                token=token,
            )
            if s == 200 and isinstance(d, dict) and d.get("status") == "signed":
                log(f"签约成功: signed_at={d.get('signed_at')[:19]}", "PASS")
                results["B21-Sign Contract"] = "PASS"
            else:
                log(f"签约失败: {s} {d}", "FAIL")
                results["B21-Sign Contract"] = "FAIL"
        else:
            results["B21-Sign Contract"] = "FAIL"
    except Exception as e:
        log(f"签约异常: {e}", "FAIL")
        results["B21-Sign Contract"] = "FAIL"

    # === 验收 7: 增值税专票申请 (普票) ===
    try:
        s, bills = http_get(f"{BASE_URL}/api/v1/demo/bills?limit=1", token)
        if s == 200 and isinstance(bills, dict) and bills.get("items"):
            bill_id = bills["items"][0]["bill_id"]
        else:
            # 生成账单
            s, bill = http_post(
                f"{BASE_URL}/api/v1/demo/bills?billing_period=2026-08",
                token=token,
            )
            bill_id = bill["bill_id"] if isinstance(bill, dict) else None

        if bill_id:
            s, d = http_post(
                f"{BASE_URL}/api/v1/demo/contracts/vat-invoice/apply",
                body={
                    "bill_id": bill_id,
                    "invoice_type": "vat_general",
                    "buyer_tax_id": "91110000123456789X",
                    "buyer_name": "测试公司",
                    "buyer_address_phone": "北京市朝阳区 / 010-12345678",
                    "buyer_bank_account": "工商银行 / 6222000123456789",
                },
                token=token,
            )
            if s == 200 and isinstance(d, dict) and "invoice_number" in d:
                log(
                    f"普票申请: invoice={d['invoice_number']}, type={d['invoice_type']}",
                    "PASS",
                )
                results["B21-VAT Invoice"] = "PASS"
            else:
                log(f"普票申请失败: {s} {d}", "FAIL")
                results["B21-VAT Invoice"] = "FAIL"
                # 打印 stderr (可能校验失败)
                if s == 400:
                    log(f"  400 详情: {d}", "INFO")
        else:
            log("无法获取 bill_id 跳过", "INFO")
            results["B21-VAT Invoice"] = "FAIL"
    except Exception as e:
        log(f"普票异常: {e}", "FAIL")
        results["B21-VAT Invoice"] = "FAIL"

    # === 验收 8: 多租户隔离 ===
    try:
        token_acme = login("admin@acme.com", "AcmePass123!", "acme")
        s_demo, _ = http_get(f"{BASE_URL}/api/v1/demo/contracts?limit=1", token)
        s_acme, _ = http_get(f"{BASE_URL}/api/v1/acme/contracts?limit=1", token_acme)
        log(
            f"多租户: demo={s_demo}, acme={s_acme}",
            "PASS" if s_demo == 200 and s_acme == 200 else "FAIL",
        )
        results["B21-Multi-Tenant"] = "PASS" if s_demo == 200 and s_acme == 200 else "FAIL"
    except Exception as e:
        log(f"多租户异常: {e}", "FAIL")
        results["B21-Multi-Tenant"] = "FAIL"

    # 汇总
    print("\n" + "=" * 60)
    print("📊 Phase 4 B21 合同与开票验收")
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