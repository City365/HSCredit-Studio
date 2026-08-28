"""Phase 6 B28 RBAC 细化 — 端到端验收.

依据 docs/ROADMAP.md Phase 6 B28 验收矩阵:

| 验收项 | 测试方法 |
|---|---|
| B28-1 权限矩阵 | GET /rbac/matrix 返回 5 角色 × 5 资源 |
| B28-2 viewer 菜单 | GET /rbac/menu viewer 仅基础项 |
| B28-3 analyst 菜单 | GET /rbac/menu analyst 含 billing |
| B28-4 权限校验 read | POST /rbac/check read workflow → allowed |
| B28-5 权限校验 write | POST /rbac/check write billing analyst → denied |
| B28-6 viewer 工作流创建 | POST /workflows viewer → 403 (核心验收) |
| B28-7 tenant_admin 工作流创建 | POST /workflows admin → 201 |
| B28-8 策略列表 | GET /rbac/policies |
| B28-9 角色审计 | GET /rbac/audit |

依赖: backend 启动在 8003 (避免占用 6002), 已执行 alembic upgrade head.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE_URL = "http://localhost:8003"


def log(msg: str, status: str = "INFO") -> None:
    symbol = "✓" if status == "PASS" else ("❌" if status == "FAIL" else "ℹ")
    print(f"[{symbol}] {msg}")


def http_post(url: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict | str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
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
    print("🚀 Phase 6 B28 RBAC 细化 E2E 验收")
    print("=" * 60)

    results: dict[str, str] = {}

    # === 登录 ===
    try:
        admin_token = login("admin@demo.com", "DemoPass123!", "demo")
        log("admin 登录成功", "PASS")
    except Exception as e:
        log(f"admin 登录失败: {e}", "FAIL")
        return 1

    try:
        viewer_token = login("viewer@demo.com", "DemoPass123!", "demo")
        log("viewer 登录成功", "PASS")
    except Exception as e:
        log(f"viewer 登录失败: {e}", "FAIL")
        return 1

    # === 验收 1: 权限矩阵 ===
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/rbac/matrix", admin_token)
        if s == 200 and isinstance(d, dict) and len(d.get("roles", [])) == 5:
            resources = d.get("resources", [])
            log(f"权限矩阵: roles={len(d['roles'])}, resources={resources}", "PASS")
            results["B28-Matrix"] = "PASS"
        else:
            log(f"权限矩阵失败: {s} {d}", "FAIL")
            results["B28-Matrix"] = "FAIL"
    except Exception as e:
        log(f"权限矩阵异常: {e}", "FAIL")
        results["B28-Matrix"] = "FAIL"

    # === 验收 2: viewer 菜单 ===
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/rbac/menu", viewer_token)
        if s == 200 and isinstance(d, dict):
            items = d.get("items", [])
            role = d.get("role", "")
            assert "admin_console" not in items
            assert "user_management" not in items
            assert "workflows" in items
            log(f"viewer 菜单: role={role}, items={items}", "PASS")
            results["B28-Viewer Menu"] = "PASS"
        else:
            log(f"viewer 菜单失败: {s} {d}", "FAIL")
            results["B28-Viewer Menu"] = "FAIL"
    except (AssertionError, Exception) as e:
        log(f"viewer 菜单异常: {e}", "FAIL")
        results["B28-Viewer Menu"] = "FAIL"

    # === 验收 3: admin 菜单 ===
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/rbac/menu", admin_token)
        if s == 200 and isinstance(d, dict):
            items = d.get("items", [])
            role = d.get("role", "")
            assert "user_management" in items
            assert "audit" in items
            assert "billing" in items
            log(f"admin 菜单: role={role}, items_count={len(items)}", "PASS")
            results["B28-Admin Menu"] = "PASS"
        else:
            log(f"admin 菜单失败: {s} {d}", "FAIL")
            results["B28-Admin Menu"] = "FAIL"
    except (AssertionError, Exception) as e:
        log(f"admin 菜单异常: {e}", "FAIL")
        results["B28-Admin Menu"] = "FAIL"

    # === 验收 4: 权限校验 read workflow ===
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/rbac/check",
            body={"resource": "workflow", "action": "read"},
            token=admin_token,
        )
        if s == 200 and isinstance(d, dict):
            allowed = d.get("allowed")
            log(f"admin read workflow: allowed={allowed}", "PASS" if allowed else "FAIL")
            results["B28-Check Read"] = "PASS" if allowed else "FAIL"
        else:
            log(f"read 校验失败: {s} {d}", "FAIL")
            results["B28-Check Read"] = "FAIL"
    except Exception as e:
        log(f"read 校验异常: {e}", "FAIL")
        results["B28-Check Read"] = "FAIL"

    # === 验收 5: viewer 写 workflow 校验 ===
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/rbac/check",
            body={"resource": "workflow", "action": "write"},
            token=viewer_token,
        )
        if s == 200 and isinstance(d, dict):
            allowed = d.get("allowed")
            log(
                f"viewer write workflow: allowed={allowed}, reason={d.get('reason', '')[:50]}",
                "PASS" if not allowed else "FAIL",
            )
            results["B28-Check Viewer Write"] = "PASS" if not allowed else "FAIL"
        else:
            log(f"viewer write 校验失败: {s} {d}", "FAIL")
            results["B28-Check Viewer Write"] = "FAIL"
    except Exception as e:
        log(f"viewer write 校验异常: {e}", "FAIL")
        results["B28-Check Viewer Write"] = "FAIL"

    # === 验收 6: viewer 调 POST /workflows 返回 403 (核心验收) ===
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/workflows",
            body={
                "name": "viewer-attempt",
                "description": "viewer 不应能创建",
                "definition": {"nodes": [], "edges": []},
            },
            token=viewer_token,
        )
        if s == 403:
            log(f"viewer POST /workflows → 403 ✓ (B28 核心验收)", "PASS")
            results["B28-Viewer Workflow 403"] = "PASS"
        else:
            log(f"viewer POST /workflows 期望 403, 实际 {s}: {d}", "FAIL")
            results["B28-Viewer Workflow 403"] = "FAIL"
    except urllib.error.HTTPError as e:
        if e.code == 403:
            log(f"viewer POST /workflows → 403 ✓ (B28 核心验收)", "PASS")
            results["B28-Viewer Workflow 403"] = "PASS"
        else:
            log(f"viewer POST /workflows 异常 {e.code}", "FAIL")
            results["B28-Viewer Workflow 403"] = "FAIL"
    except Exception as e:
        log(f"viewer POST /workflows 异常: {e}", "FAIL")
        results["B28-Viewer Workflow 403"] = "FAIL"

    # === 验收 7: admin 调 POST /workflows 返回 201 ===
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/workflows",
            body={
                "name": f"e2e-b28-{int(__import__('time').time())}",
                "description": "B28 E2E",
                "definition": {"nodes": [], "edges": []},
            },
            token=admin_token,
        )
        if s in (200, 201) and isinstance(d, dict) and ("workflow_id" in d or "id" in d):
            log(f"admin POST /workflows → {s} ✓", "PASS")
            results["B28-Admin Workflow 201"] = "PASS"
        else:
            log(f"admin POST /workflows 失败: {s} {d}", "FAIL")
            results["B28-Admin Workflow 201"] = "FAIL"
    except Exception as e:
        log(f"admin POST /workflows 异常: {e}", "FAIL")
        results["B28-Admin Workflow 201"] = "FAIL"

    # === 验收 8: 策略列表 ===
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/rbac/policies", admin_token)
        if s == 200 and isinstance(d, list):
            log(f"策略列表: {len(d)} 条", "PASS")
            results["B28-Policies"] = "PASS"
        else:
            log(f"策略列表失败: {s} {d}", "FAIL")
            results["B28-Policies"] = "FAIL"
    except Exception as e:
        log(f"策略列表异常: {e}", "FAIL")
        results["B28-Policies"] = "FAIL"

    # === 验收 9: 角色审计 ===
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/rbac/audit", admin_token)
        if s == 200 and isinstance(d, dict) and "items" in d:
            log(f"角色审计: items={len(d.get('items', []))}", "PASS")
            results["B28-Audit"] = "PASS"
        else:
            log(f"角色审计失败: {s} {d}", "FAIL")
            results["B28-Audit"] = "FAIL"
    except Exception as e:
        log(f"角色审计异常: {e}", "FAIL")
        results["B28-Audit"] = "FAIL"

    # 汇总
    print("\n" + "=" * 60)
    print("📊 Phase 6 B28 RBAC 细化验收")
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