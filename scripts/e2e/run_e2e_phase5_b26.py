"""Phase 5 B26 PIPL 数据保护 — 端到端验证.

依据 docs/ROADMAP.md Phase 5 B26 验收矩阵:

| 验收项 | 测试方法 |
|---|---|
| B26-1 隐私政策 | GET /pipl/privacy-policy 返回中文版 |
| B26-2 法律基础列表 | GET /pipl/legal-basis 返回 4 种 PIPL 第 38 条 |
| B26-3 同意授予 | POST /pipl/consent 返回 consent_id |
| B26-4 同意检查 | GET /pipl/consent/check 验证状态 |
| B26-5 同意撤回 | DELETE /pipl/consent 撤回 |
| B26-6 DSR 提交 | POST /pipl/dsr 返回 request_id + due_at |
| B26-7 DSR 列表 | GET /pipl/dsr 列出用户全部 DSR |
| B26-8 数据可携 | GET /pipl/me/data-export 返回完整包 |
| B26-9 跨境申请 | POST /pipl/cross-border 申请 |
| B26-10 跨境审批 | PATCH /cross-border/{id}/approve |
| B26-11 跨境列表 | GET /pipl/cross-border 含已审批项 |
| B26-12 匿名化 | POST /pipl/me/anonymize (admin 测试用) |

依赖: backend 启动在 8002, 已执行 alembic upgrade head.
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


def http_delete(url: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict | str]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body or {}).encode("utf-8") if body is not None else b""
    req = urllib.request.Request(url, data=data, headers=headers, method="DELETE")
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


def http_patch(url: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict | str]:
    headers = {"Content-Type": "application/json"}
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


def login(email: str, password: str, tenant_slug: str) -> tuple[str, dict]:
    """返回 (token, payload)."""
    s, d = http_post(
        f"{BASE_URL}/api/v1/auth/login",
        {"email": email, "password": password, "tenant_slug": tenant_slug},
    )
    if s != 200 or not isinstance(d, dict):
        raise RuntimeError(f"Login failed: {s} {d}")
    return d["tokens"]["access_token"], d


def main() -> int:
    print("=" * 60)
    print("🚀 Phase 5 B26 PIPL 数据保护 E2E 验收")
    print("=" * 60)

    results: dict[str, str] = {}

    try:
        token, _ = login("admin@demo.com", "DemoPass123!", "demo")
        log("demo 登录成功", "PASS")
    except Exception as e:
        log(f"登录失败: {e}", "FAIL")
        return 1

    # === 验收 1: 隐私政策 ===
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/pipl/privacy-policy", token)
        if s == 200 and isinstance(d, dict) and d.get("version") == "v1.0":
            content_len = len(d.get("content", ""))
            log(
                f"隐私政策: version={d['version']}, content_len={content_len}",
                "PASS" if content_len > 100 else "FAIL",
            )
            results["B26-Privacy Policy"] = "PASS" if content_len > 100 else "FAIL"
        else:
            log(f"隐私政策失败: {s} {d}", "FAIL")
            results["B26-Privacy Policy"] = "FAIL"
    except Exception as e:
        log(f"隐私政策异常: {e}", "FAIL")
        results["B26-Privacy Policy"] = "FAIL"

    # === 验收 2: 法律基础列表 ===
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/pipl/legal-basis", token)
        if s == 200 and isinstance(d, dict) and len(d.get("bases", [])) == 4:
            log(
                f"跨境法律基础: {d['bases']}",
                "PASS",
            )
            results["B26-Legal Basis"] = "PASS"
        else:
            log(f"法律基础失败: {s} {d}", "FAIL")
            results["B26-Legal Basis"] = "FAIL"
    except Exception as e:
        log(f"法律基础异常: {e}", "FAIL")
        results["B26-Legal Basis"] = "FAIL"

    # === 验收 3: 同意授予 ===
    consent_id = None
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/pipl/consent",
            body={"purpose": "marketing", "source": "e2e_test"},
            token=token,
        )
        if s == 200 and isinstance(d, dict) and "consent_id" in d:
            consent_id = d["consent_id"]
            log(f"同意授予: {consent_id[:8]}...", "PASS")
            results["B26-Consent Grant"] = "PASS"
        else:
            log(f"同意授予失败: {s} {d}", "FAIL")
            results["B26-Consent Grant"] = "FAIL"
    except Exception as e:
        log(f"同意授予异常: {e}", "FAIL")
        results["B26-Consent Grant"] = "FAIL"

    # === 验收 4: 同意检查 ===
    try:
        s, d = http_get(
            f"{BASE_URL}/api/v1/demo/pipl/consent/check?purpose=marketing", token
        )
        if s == 200 and isinstance(d, dict) and d.get("granted") is True:
            log(f"同意检查: marketing granted={d['granted']}", "PASS")
            results["B26-Consent Check"] = "PASS"
        else:
            log(f"同意检查失败: {s} {d}", "FAIL")
            results["B26-Consent Check"] = "FAIL"
    except Exception as e:
        log(f"同意检查异常: {e}", "FAIL")
        results["B26-Consent Check"] = "FAIL"

    # === 验收 5: 同意撤回 ===
    if consent_id:
        try:
            s, d = http_delete(
                f"{BASE_URL}/api/v1/demo/pipl/consent",
                body={"purpose": "marketing", "reason": "E2E 测试撤回"},
                token=token,
            )
            log(
                f"同意撤回: status={s}",
                "PASS" if s == 200 else "FAIL",
            )
            results["B26-Consent Revoke"] = "PASS" if s == 200 else "FAIL"
        except Exception as e:
            log(f"同意撤回异常: {e}", "FAIL")
            results["B26-Consent Revoke"] = "FAIL"

    # === 验收 6: 撤回后检查 (granted=false) ===
    try:
        s, d = http_get(
            f"{BASE_URL}/api/v1/demo/pipl/consent/check?purpose=marketing", token
        )
        if s == 200 and isinstance(d, dict) and d.get("granted") is False:
            log(f"撤回后检查: granted={d['granted']}", "PASS")
            results["B26-Consent Revoked Check"] = "PASS"
        else:
            log(f"撤回后检查失败: {s} {d}", "FAIL")
            results["B26-Consent Revoked Check"] = "FAIL"
    except Exception as e:
        log(f"撤回后检查异常: {e}", "FAIL")
        results["B26-Consent Revoked Check"] = "FAIL"

    # === 验收 7: DSR 提交 ===
    dsr_id = None
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/pipl/dsr",
            body={
                "request_type": "access",
                "reason": "E2E 测试查询请求",
            },
            token=token,
        )
        if s == 200 and isinstance(d, dict) and "request_id" in d:
            dsr_id = d["request_id"]
            log(
                f"DSR 提交: request_id={dsr_id[:8]}..., due_at={d.get('due_at', '')[:10]}",
                "PASS",
            )
            results["B26-DSR Submit"] = "PASS"
        else:
            log(f"DSR 提交失败: {s} {d}", "FAIL")
            results["B26-DSR Submit"] = "FAIL"
    except Exception as e:
        log(f"DSR 异常: {e}", "FAIL")
        results["B26-DSR Submit"] = "FAIL"

    # === 验收 8: DSR 列表 ===
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/pipl/dsr", token)
        if s == 200 and isinstance(d, list) and len(d) >= 1:
            log(f"DSR 列表: {len(d)} 条", "PASS")
            results["B26-DSR List"] = "PASS"
        else:
            log(f"DSR 列表失败: {s} {d}", "FAIL")
            results["B26-DSR List"] = "FAIL"
    except Exception as e:
        log(f"DSR 列表异常: {e}", "FAIL")
        results["B26-DSR List"] = "FAIL"

    # === 验收 9: DSR 处理流转 ===
    if dsr_id:
        try:
            s, d = http_patch(
                f"{BASE_URL}/api/v1/demo/pipl/dsr/{dsr_id}",
                body={"new_status": "completed", "response": {"note": "E2E 测试已完成"}},
                token=token,
            )
            log(
                f"DSR 处理: status={s}, new_status={d.get('status')}",
                "PASS" if s == 200 and d.get("status") == "completed" else "FAIL",
            )
            results["B26-DSR Process"] = (
                "PASS" if s == 200 and d.get("status") == "completed" else "FAIL"
            )
        except Exception as e:
            log(f"DSR 处理异常: {e}", "FAIL")
            results["B26-DSR Process"] = "FAIL"

    # === 验收 10: 数据可携 ===
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/pipl/me/data-export", token)
        if s == 200 and isinstance(d, dict) and "export_id" in d and "package_hash" in d:
            log(
                f"数据可携: export_id={d['export_id'][:8]}..., hash_len={len(d['package_hash'])}",
                "PASS",
            )
            results["B26-Data Export"] = "PASS"
        else:
            log(f"数据可携失败: {s} {d}", "FAIL")
            results["B26-Data Export"] = "FAIL"
    except Exception as e:
        log(f"数据可携异常: {e}", "FAIL")
        results["B26-Data Export"] = "FAIL"

    # === 验收 11: 跨境申请 ===
    transfer_id = None
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/pipl/cross-border",
            body={
                "destination_country": "US",
                "destination_entity": "AWS US-East (E2E)",
                "data_categories": ["internal.tenant_id"],
                "legal_basis": "cac_assessment",
                "legal_basis_ref": "CAC-E2E-001",
            },
            token=token,
        )
        if s == 200 and isinstance(d, dict) and "transfer_id" in d:
            transfer_id = d["transfer_id"]
            log(
                f"跨境申请: transfer_id={transfer_id[:8]}..., approved={d.get('approved')}",
                "PASS" if d.get("approved") is None else "FAIL",
            )
            results["B26-Cross-Border Request"] = (
                "PASS" if d.get("approved") is None else "FAIL"
            )
        else:
            log(f"跨境申请失败: {s} {d}", "FAIL")
            results["B26-Cross-Border Request"] = "FAIL"
    except Exception as e:
        log(f"跨境申请异常: {e}", "FAIL")
        results["B26-Cross-Border Request"] = "FAIL"

    # === 验收 12: 跨境审批 ===
    if transfer_id:
        try:
            s, d = http_patch(
                f"{BASE_URL}/api/v1/demo/pipl/cross-border/{transfer_id}/approve",
                body={"approved": True, "notes": "E2E 测试通过"},
                token=token,
            )
            log(
                f"跨境审批: status={s}, approved={d.get('approved')}",
                "PASS" if s == 200 and d.get("approved") is True else "FAIL",
            )
            results["B26-Cross-Border Approve"] = (
                "PASS" if s == 200 and d.get("approved") is True else "FAIL"
            )
        except Exception as e:
            log(f"跨境审批异常: {e}", "FAIL")
            results["B26-Cross-Border Approve"] = "FAIL"

    # === 验收 13: 跨境列表 ===
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/pipl/cross-border", token)
        if s == 200 and isinstance(d, list) and len(d) >= 1:
            log(f"跨境列表: {len(d)} 条", "PASS")
            results["B26-Cross-Border List"] = "PASS"
        else:
            log(f"跨境列表失败: {s} {d}", "FAIL")
            results["B26-Cross-Border List"] = "FAIL"
    except Exception as e:
        log(f"跨境列表异常: {e}", "FAIL")
        results["B26-Cross-Border List"] = "FAIL"

    # 汇总
    print("\n" + "=" * 60)
    print("📊 Phase 5 B26 PIPL 数据保护验收")
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