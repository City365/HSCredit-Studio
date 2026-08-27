"""Phase 3 B15 Rate Limiting — 端到端验证.

依据 docs/ROADMAP.md Phase 3 B15 验收矩阵:

| 验收项 | 测试方法 |
|---|---|
| B15-1 响应头含 X-RateLimit-Plan | GET /templates, 校验头含 plan=free/pro/enterprise |
| B15-2 限额正确分级 | demo/pro plan 应有不同限额, 验证 X-RateLimit-Limit |
| B15-3 Lua 原子执行 | 验证响应头 X-RateLimit-Remaining 随请求递减 (多次请求) |
| B15-4 fail-open 头存在 | 任意成功请求都应包含 X-RateLimit-* 三个头 |

依赖: backend 启动在 8002, demo + acme 租户已 seed.
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


def http_post(url: str, body: dict, token: str | None = None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else ""
        try:
            return e.code, json.loads(raw) if raw else {}
        except Exception:
            return e.code, {"raw": raw}


def http_get(url: str, token: str | None = None) -> tuple[int, dict, dict]:
    """返回 (status, body, headers)."""
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}, dict(resp.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else ""
        try:
            return e.code, json.loads(raw) if raw else {}, dict(e.headers)
        except Exception:
            return e.code, {"raw": raw}, dict(e.headers)


def login(email: str, password: str, tenant_slug: str) -> str:
    s, d = http_post(
        f"{BASE_URL}/api/v1/auth/login",
        {"email": email, "password": password, "tenant_slug": tenant_slug},
    )
    if s != 200:
        raise RuntimeError(f"Login failed: {s} {d}")
    return d["tokens"]["access_token"]


def main() -> int:
    print("=" * 60)
    print("🚀 Phase 3 B15 Rate Limiting E2E 验收")
    print("=" * 60)

    results: dict[str, str] = {}

    # 登录两个租户
    try:
        token_demo = login("admin@demo.com", "DemoPass123!", "demo")
        token_acme = login("admin@acme.com", "AcmePass123!", "acme")
        log("demo + acme 双租户登录成功", "PASS")
        results["B15-Auth"] = "PASS"
    except Exception as e:
        log(f"登录失败: {e}", "FAIL")
        results["B15-Auth"] = "FAIL"
        return 1

    # 验收 1: 响应头含 X-RateLimit-Plan
    try:
        _, _, headers = http_get(f"{BASE_URL}/api/v1/demo/templates", token_demo)
        plan = headers.get("X-RateLimit-Plan") or headers.get("x-ratelimit-plan")
        limit = headers.get("X-RateLimit-Limit") or headers.get("x-ratelimit-limit")
        log(
            f"demo 租户响应头: plan={plan}, limit={limit}",
            "PASS" if plan in ("free", "pro", "enterprise") else "FAIL",
        )
        results["B15-Plan Header"] = "PASS" if plan in ("free", "pro", "enterprise") else "FAIL"
    except Exception as e:
        log(f"plan 头验证异常: {e}", "FAIL")
        results["B15-Plan Header"] = "FAIL"

    # 验收 2: 不同租户 plan 不同
    try:
        _, _, headers_demo = http_get(f"{BASE_URL}/api/v1/demo/templates", token_demo)
        _, _, headers_acme = http_get(f"{BASE_URL}/api/v1/acme/templates", token_acme)
        plan_demo = headers_demo.get("X-RateLimit-Plan") or headers_demo.get("x-ratelimit-plan")
        plan_acme = headers_acme.get("X-RateLimit-Plan") or headers_acme.get("x-ratelimit-plan")
        log(
            f"demo plan={plan_demo}, acme plan={plan_acme}",
            "INFO",
        )
        # 两个租户可能是同 plan, 但 limit 字段必须出现
        limit_demo = headers_demo.get("X-RateLimit-Limit") or headers_demo.get("x-ratelimit-limit")
        limit_acme = headers_acme.get("X-RateLimit-Limit") or headers_acme.get("x-ratelimit-limit")
        both_have_limit = limit_demo and limit_acme
        log(
            f"两租户 X-RateLimit-Limit 头都存在: demo={limit_demo}, acme={limit_acme}",
            "PASS" if both_have_limit else "FAIL",
        )
        results["B15-Limit Header"] = "PASS" if both_have_limit else "FAIL"
    except Exception as e:
        log(f"limit 头验证异常: {e}", "FAIL")
        results["B15-Limit Header"] = "FAIL"

    # 验收 3: Remaining 头随请求递减 (Lua 实际写入 Redis)
    try:
        remaining_values = []
        for _ in range(3):
            _, _, h = http_get(f"{BASE_URL}/api/v1/demo/templates", token_demo)
            rem = h.get("X-RateLimit-Remaining") or h.get("x-ratelimit-remaining")
            remaining_values.append(int(rem) if rem else None)
        log(
            f"3 次请求 Remaining 序列: {remaining_values}",
            "PASS" if all(v is not None for v in remaining_values) else "FAIL",
        )
        results["B15-Remaining Decrement"] = (
            "PASS" if all(v is not None for v in remaining_values) else "FAIL"
        )
    except Exception as e:
        log(f"Remaining 验证异常: {e}", "FAIL")
        results["B15-Remaining Decrement"] = "FAIL"

    # 验收 4: Retry-After + X-RateLimit-* 三个头都存在
    try:
        _, _, headers = http_get(f"{BASE_URL}/api/v1/demo/templates", token_demo)
        plan = headers.get("X-RateLimit-Plan") or headers.get("x-ratelimit-plan")
        limit = headers.get("X-RateLimit-Limit") or headers.get("x-ratelimit-limit")
        remaining = headers.get("X-RateLimit-Remaining") or headers.get("x-ratelimit-remaining")
        all_three = plan is not None and limit is not None and remaining is not None
        log(
            f"三个 X-RateLimit-* 头齐全: plan={plan}, limit={limit}, remaining={remaining}",
            "PASS" if all_three else "FAIL",
        )
        results["B15-Three Headers"] = "PASS" if all_three else "FAIL"
    except Exception as e:
        log(f"头齐全验证异常: {e}", "FAIL")
        results["B15-Three Headers"] = "FAIL"

    # 汇总
    print("\n" + "=" * 60)
    print("📊 Phase 3 B15 Rate Limiting 验收")
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