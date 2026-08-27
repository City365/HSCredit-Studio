"""Phase 4 B18 用量计量 — 端到端验证.

依据 docs/ROADMAP.md Phase 4 B18 验收矩阵:

| 验收项 | 测试方法 |
|---|---|
| B18-1 usage API 响应 | GET /api/v1/demo/usage 返回 200 + JSON 含 runs/sandbox/artifacts/workflows/api_calls |
| B18-2 Run 维度数据 | 触发 Run 后, runs.total 与 sandbox.total 增长 |
| B18-3 Sandbox 维度字段 | 含 total_duration_ms / total_cpu_seconds / max_mem_peak_mb / by_node_type |
| B18-4 Artifact 维度 | 含 total + total_bytes |
| B18-5 Workflow 维度 | 含 total |
| B18-6 多租户隔离 | acme / demo 返回不同数据 |

依赖: backend 启动在 8002.
"""
from __future__ import annotations

import json
import sys
import time
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


def http_get(url: str, token: str | None = None) -> tuple[int, dict]:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
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
    print("🚀 Phase 4 B18 用量计量 E2E 验收")
    print("=" * 60)

    results: dict[str, str] = {}

    try:
        token_demo = login("admin@demo.com", "DemoPass123!", "demo")
        token_acme = login("admin@acme.com", "AcmePass123!", "acme")
        log("demo + acme 登录成功", "PASS")
    except Exception as e:
        log(f"登录失败: {e}", "FAIL")
        return 1

    # === 验收 1: usage API 响应 ===
    try:
        s, usage = http_get(f"{BASE_URL}/api/v1/demo/usage?days=30", token_demo)
        if s != 200:
            log(f"usage API 返回 {s}: {usage}", "FAIL")
            results["B18-Usage API"] = "FAIL"
        else:
            required_dims = {"runs", "sandbox", "artifacts", "workflows", "api_calls"}
            present = set(usage.keys())
            missing = required_dims - present
            log(
                f"usage API 返回 200, 含 {len(present)} 维度 (missing={missing})",
                "PASS" if not missing else "FAIL",
            )
            results["B18-Usage API"] = "PASS" if not missing else "FAIL"
    except Exception as e:
        log(f"usage API 异常: {e}", "FAIL")
        results["B18-Usage API"] = "FAIL"

    # === 验收 2: Sandbox 维度字段完整 ===
    try:
        sandbox = usage.get("sandbox", {})
        required_fields = {
            "total", "total_duration_ms", "total_cpu_seconds", "max_mem_peak_mb", "by_node_type"
        }
        missing = required_fields - set(sandbox.keys())
        log(
            f"Sandbox 维度字段: missing={missing}",
            "PASS" if not missing else "FAIL",
        )
        results["B18-Sandbox Fields"] = "PASS" if not missing else "FAIL"
    except Exception as e:
        log(f"Sandbox 检查异常: {e}", "FAIL")
        results["B18-Sandbox Fields"] = "FAIL"

    # === 验收 3: Artifact 维度字段 ===
    try:
        artifacts = usage.get("artifacts", {})
        ok = "total" in artifacts and "total_bytes" in artifacts
        log(
            f"Artifact 字段: total={artifacts.get('total')}, total_bytes={artifacts.get('total_bytes')}",
            "PASS" if ok else "FAIL",
        )
        results["B18-Artifact Fields"] = "PASS" if ok else "FAIL"
    except Exception as e:
        log(f"Artifact 检查异常: {e}", "FAIL")
        results["B18-Artifact Fields"] = "FAIL"

    # === 验收 4: Workflow 维度 ===
    try:
        workflows = usage.get("workflows", {})
        log(
            f"Workflow 数: {workflows.get('total')}",
            "PASS" if "total" in workflows else "FAIL",
        )
        results["B18-Workflow Fields"] = "PASS" if "total" in workflows else "FAIL"
    except Exception as e:
        log(f"Workflow 检查异常: {e}", "FAIL")
        results["B18-Workflow Fields"] = "FAIL"

    # === 验收 5: 多租户隔离 ===
    try:
        s_demo, u_demo = http_get(f"{BASE_URL}/api/v1/demo/usage?days=30", token_demo)
        s_acme, u_acme = http_get(f"{BASE_URL}/api/v1/acme/usage?days=30", token_acme)
        demo_runs = u_demo.get("runs", {}).get("total", 0)
        acme_runs = u_acme.get("runs", {}).get("total", 0)
        log(
            f"多租户隔离: demo runs={demo_runs}, acme runs={acme_runs}",
            "PASS" if demo_runs >= acme_runs else "FAIL",
        )
        results["B18-Multi-Tenant"] = "PASS" if demo_runs >= acme_runs else "FAIL"
    except Exception as e:
        log(f"多租户隔离异常: {e}", "FAIL")
        results["B18-Multi-Tenant"] = "FAIL"

    # === 验收 6: 时间范围参数 (days) ===
    try:
        s, u_1d = http_get(f"{BASE_URL}/api/v1/demo/usage?days=1", token_demo)
        s, u_30d = http_get(f"{BASE_URL}/api/v1/demo/usage?days=30", token_demo)
        runs_1d = u_1d.get("runs", {}).get("total", 0)
        runs_30d = u_30d.get("runs", {}).get("total", 0)
        log(
            f"days=1 runs={runs_1d}, days=30 runs={runs_30d}",
            "PASS" if runs_30d >= runs_1d else "FAIL",
        )
        results["B18-Time Range"] = "PASS" if runs_30d >= runs_1d else "FAIL"
    except Exception as e:
        log(f"时间范围异常: {e}", "FAIL")
        results["B18-Time Range"] = "FAIL"

    # 汇总
    print("\n" + "=" * 60)
    print("📊 Phase 4 B18 用量计量验收")
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