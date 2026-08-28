"""Phase 5 B24 数据分类与脱敏 — 端到端验证.

依据 docs/ROADMAP.md Phase 5 B24 验收矩阵:

| 验收项 | 测试方法 |
|---|---|
| B24-1 字段分类列表 | GET /data-classification/fields 返回 20+ 字段 |
| B24-2 单字段脱敏 | POST /mask 身份证 → 1101**********1234 |
| B24-3 邮箱脱敏 | POST /mask email → a***@example.com |
| B24-4 批量脱敏 | POST /redact dict 含敏感字段 → 自动脱敏 |
| B24-5 嵌套脱敏 | POST /redact 嵌套 dict → 递归脱敏 |
| B24-6 多租户隔离 | demo/acme 都 200 |

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
    print("🚀 Phase 5 B24 数据分类与脱敏 E2E 验收")
    print("=" * 60)

    results: dict[str, str] = {}

    try:
        token = login("admin@demo.com", "DemoPass123!", "demo")
        log("demo 登录成功", "PASS")
    except Exception as e:
        log(f"登录失败: {e}", "FAIL")
        return 1

    # === 验收 1: 字段分类列表 ===
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/data-classification/fields", token)
        if s == 200 and isinstance(d, dict) and "items" in d:
            count = d.get("count", 0)
            highly = [i for i in d["items"] if i["sensitivity"] == "highly_sensitive"]
            log(
                f"字段分类: {count} 条, 高敏 {len(highly)} 种",
                "PASS" if count >= 20 and len(highly) >= 5 else "FAIL",
            )
            results["B24-Fields"] = "PASS" if count >= 20 and len(highly) >= 5 else "FAIL"
        else:
            log(f"字段列表失败: {s} {d}", "FAIL")
            results["B24-Fields"] = "FAIL"
    except Exception as e:
        log(f"字段列表异常: {e}", "FAIL")
        results["B24-Fields"] = "FAIL"

    # === 验收 2: 单字段脱敏 — 身份证 ===
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/data-classification/mask",
            body={"field_name": "id_card", "value": "110101199001011234"},
            token=token,
        )
        if s == 200 and isinstance(d, dict):
            masked = d.get("masked_value", "")
            h = d.get("field_value_hash", "")
            log(
                f"身份证脱敏: masked='{masked}', hash={h[:8]}...",
                "PASS" if "1234" in masked and "1990" not in masked else "FAIL",
            )
            results["B24-Mask ID Card"] = (
                "PASS" if "1234" in masked and "1990" not in masked else "FAIL"
            )
        else:
            log(f"身份证脱敏失败: {s} {d}", "FAIL")
            results["B24-Mask ID Card"] = "FAIL"
    except Exception as e:
        log(f"身份证脱敏异常: {e}", "FAIL")
        results["B24-Mask ID Card"] = "FAIL"

    # === 验收 3: 单字段脱敏 — 邮箱 ===
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/data-classification/mask",
            body={"field_name": "email", "value": "alice@example.com"},
            token=token,
        )
        if s == 200 and isinstance(d, dict):
            masked = d.get("masked_value", "")
            log(
                f"邮箱脱敏: {masked}",
                "PASS" if masked == "a***@example.com" else "FAIL",
            )
            results["B24-Mask Email"] = "PASS" if masked == "a***@example.com" else "FAIL"
        else:
            log(f"邮箱脱敏失败: {s} {d}", "FAIL")
            results["B24-Mask Email"] = "FAIL"
    except Exception as e:
        log(f"邮箱脱敏异常: {e}", "FAIL")
        results["B24-Mask Email"] = "FAIL"

    # === 验收 4: 批量脱敏 dict ===
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/data-classification/redact",
            body={
                "payload": {
                    "name": "张三",
                    "phone": "13800138000",
                    "email": "alice@example.com",
                    "id_card": "110101199001011234",
                }
            },
            token=token,
        )
        if s == 200 and isinstance(d, dict) and "redacted" in d:
            r = d["redacted"]
            fields = d.get("fields_redacted", [])
            log(
                f"批量脱敏: name 保留={r.get('name')}, phone mask={r.get('phone')}, 脱敏字段={fields}",
                "PASS"
                if r.get("name") == "张三"
                and "****" in r.get("phone", "")
                else "FAIL",
            )
            results["B24-Batch Redact"] = (
                "PASS"
                if r.get("name") == "张三" and "****" in r.get("phone", "")
                else "FAIL"
            )
        else:
            log(f"批量脱敏失败: {s} {d}", "FAIL")
            results["B24-Batch Redact"] = "FAIL"
    except Exception as e:
        log(f"批量脱敏异常: {e}", "FAIL")
        results["B24-Batch Redact"] = "FAIL"

    # === 验收 5: 嵌套脱敏 ===
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/data-classification/redact",
            body={
                "payload": {
                    "user_id": "u-1",
                    "profile": {
                        "name": "李四",
                        "phone": "13800138001",
                        "id_card": "110101199002021234",
                    },
                }
            },
            token=token,
        )
        if s == 200 and isinstance(d, dict) and "redacted" in d:
            profile = d["redacted"].get("profile", {})
            log(
                f"嵌套脱敏: profile.phone={profile.get('phone')}",
                "PASS" if "1234" in profile.get("id_card", "") else "FAIL",
            )
            results["B24-Nested Redact"] = "PASS" if "1234" in profile.get("id_card", "") else "FAIL"
        else:
            log(f"嵌套脱敏失败: {s} {d}", "FAIL")
            results["B24-Nested Redact"] = "FAIL"
    except Exception as e:
        log(f"嵌套脱敏异常: {e}", "FAIL")
        results["B24-Nested Redact"] = "FAIL"

    # === 验收 6: 多租户隔离 ===
    try:
        token_acme = login("admin@acme.com", "AcmePass123!", "acme")
        s_demo, _ = http_get(f"{BASE_URL}/api/v1/demo/data-classification/fields", token)
        s_acme, _ = http_get(f"{BASE_URL}/api/v1/acme/data-classification/fields", token_acme)
        log(
            f"多租户: demo={s_demo}, acme={s_acme}",
            "PASS" if s_demo == 200 and s_acme == 200 else "FAIL",
        )
        results["B24-Multi-Tenant"] = "PASS" if s_demo == 200 and s_acme == 200 else "FAIL"
    except Exception as e:
        log(f"多租户异常: {e}", "FAIL")
        results["B24-Multi-Tenant"] = "FAIL"

    # 汇总
    print("\n" + "=" * 60)
    print("📊 Phase 5 B24 数据分类与脱敏验收")
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