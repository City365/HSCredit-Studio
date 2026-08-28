"""Phase 6 B29 租户超管后台 — 端到端验收.

依据 docs/ROADMAP.md Phase 6 B29 验收矩阵:

| 验收项 | 测试方法 |
|---|---|
| B29-1 super_admin 仪表板 | GET /admin/overview 返回全局聚合 |
| B29-2 租户列表 | GET /admin/tenants 含 demo + acme |
| B29-3 租户详情 | GET /admin/tenants/{id} 含 members/usage |
| B29-4 租户停用 | POST /admin/tenants/{id}/status → suspended |
| B29-5 租户启用 | POST /admin/tenants/{id}/status → active |
| B29-6 租户迁移 | POST /admin/tenants/{id}/migrate → cluster=cn-east-1 |
| B29-7 角色变更 | POST /admin/tenants/{id}/users/{uid}/role → analyst |
| B29-8 viewer 拒绝 | GET /admin/overview viewer → 403 |
| B29-9 审计写入 | GET /rbac/audit 验证变更留痕 |

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


def login(email: str, password: str, tenant_slug: str) -> tuple[str, dict]:
    s, d = http_post(
        f"{BASE_URL}/api/v1/auth/login",
        {"email": email, "password": password, "tenant_slug": tenant_slug},
    )
    if s != 200 or not isinstance(d, dict):
        raise RuntimeError(f"Login failed: {s} {d}")
    return d["tokens"]["access_token"], d.get("user", {})


def main() -> int:
    print("=" * 60)
    print("🚀 Phase 6 B29 租户超管后台 E2E 验收")
    print("=" * 60)

    results: dict[str, str] = {}

    try:
        admin_token, admin_user = login("admin@demo.com", "DemoPass123!", "demo")
        log(f"admin (super_admin) 登录成功: role={admin_user.get('role')}", "PASS")
        if admin_user.get("role") != "super_admin":
            log(f"警告: admin role 应为 super_admin, 实际 {admin_user.get('role')}", "FAIL")
    except Exception as e:
        log(f"admin 登录失败: {e}", "FAIL")
        return 1

    try:
        viewer_token, _ = login("viewer@demo.com", "DemoPass123!", "demo")
        log("viewer 登录成功", "PASS")
    except Exception as e:
        log(f"viewer 登录失败: {e}", "FAIL")
        return 1

    # === 验收 1: super_admin 仪表板 ===
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/admin/overview", admin_token)
        if s == 200 and isinstance(d, dict) and "total_tenants" in d:
            log(
                f"仪表板: total={d['total_tenants']}, active={d['active_tenants']}, "
                f"runs={d['total_runs_30d']}",
                "PASS",
            )
            results["B29-Overview"] = "PASS"
        else:
            log(f"仪表板失败: {s} {d}", "FAIL")
            results["B29-Overview"] = "FAIL"
    except Exception as e:
        log(f"仪表板异常: {e}", "FAIL")
        results["B29-Overview"] = "FAIL"

    # === 验收 2: 租户列表 ===
    demo_tenant_id = None
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/admin/tenants?page=1&page_size=10", admin_token)
        if s == 200 and isinstance(d, dict):
            items = d.get("items", [])
            for it in items:
                if it["slug"] == "demo":
                    demo_tenant_id = it["tenant_id"]
            log(f"租户列表: {len(items)} 条, demo_id={demo_tenant_id[:8]}...", "PASS")
            results["B29-List"] = "PASS"
        else:
            log(f"租户列表失败: {s} {d}", "FAIL")
            results["B29-List"] = "FAIL"
    except Exception as e:
        log(f"租户列表异常: {e}", "FAIL")
        results["B29-List"] = "FAIL"

    if not demo_tenant_id:
        log("无法获取 demo tenant_id, 跳过后续验收", "FAIL")
        return 1

    # === 验收 3: 租户详情 ===
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/admin/tenants/{demo_tenant_id}", admin_token)
        if s == 200 and isinstance(d, dict):
            members = d.get("members", [])
            usage_30d = d.get("usage_30d", {})
            log(
                f"租户详情: members={len(members)}, runs_30d={usage_30d.get('total_runs')}",
                "PASS",
            )
            results["B29-Detail"] = "PASS"
        else:
            log(f"租户详情失败: {s} {d}", "FAIL")
            results["B29-Detail"] = "FAIL"
    except Exception as e:
        log(f"租户详情异常: {e}", "FAIL")
        results["B29-Detail"] = "FAIL"

    # === 验收 4: 租户停用 ===
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/admin/tenants/{demo_tenant_id}/status",
            body={"status": "suspended"},
            token=admin_token,
        )
        if s == 200 and isinstance(d, dict) and d.get("status") == "suspended":
            log(f"租户停用: status={d.get('status')}", "PASS")
            results["B29-Suspend"] = "PASS"
        else:
            log(f"租户停用失败: {s} {d}", "FAIL")
            results["B29-Suspend"] = "FAIL"
    except Exception as e:
        log(f"租户停用异常: {e}", "FAIL")
        results["B29-Suspend"] = "FAIL"

    # === 验收 5: 租户启用 ===
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/admin/tenants/{demo_tenant_id}/status",
            body={"status": "active"},
            token=admin_token,
        )
        if s == 200 and isinstance(d, dict) and d.get("status") == "active":
            log(f"租户启用: status={d.get('status')}", "PASS")
            results["B29-Reactivate"] = "PASS"
        else:
            log(f"租户启用失败: {s} {d}", "FAIL")
            results["B29-Reactivate"] = "FAIL"
    except Exception as e:
        log(f"租户启用异常: {e}", "FAIL")
        results["B29-Reactivate"] = "FAIL"

    # === 验收 6: 租户迁移 ===
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/admin/tenants/{demo_tenant_id}/migrate",
            body={"target_cluster": "cn-east-1"},
            token=admin_token,
        )
        if s == 200 and isinstance(d, dict) and d.get("target_cluster") == "cn-east-1":
            log(f"租户迁移: cluster={d.get('target_cluster')}", "PASS")
            results["B29-Migrate"] = "PASS"
        else:
            log(f"租户迁移失败: {s} {d}", "FAIL")
            results["B29-Migrate"] = "FAIL"
    except Exception as e:
        log(f"租户迁移异常: {e}", "FAIL")
        results["B29-Migrate"] = "FAIL"

    # === 验收 7: viewer 拒绝 (核心验收) ===
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/admin/overview", viewer_token)
        if s == 403:
            log(f"viewer GET /admin/overview → 403 ✓ (B29 核心验收)", "PASS")
            results["B29-Viewer 403"] = "PASS"
        else:
            log(f"viewer 期望 403, 实际 {s}: {d}", "FAIL")
            results["B29-Viewer 403"] = "FAIL"
    except urllib.error.HTTPError as e:
        if e.code == 403:
            log(f"viewer GET /admin/overview → 403 ✓", "PASS")
            results["B29-Viewer 403"] = "PASS"
        else:
            log(f"viewer 异常 {e.code}", "FAIL")
            results["B29-Viewer 403"] = "FAIL"
    except Exception as e:
        log(f"viewer 异常: {e}", "FAIL")
        results["B29-Viewer 403"] = "FAIL"

    # === 验收 8: 角色变更 (把 viewer 改成 analyst) ===
    user_id_to_change = None
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/admin/tenants/{demo_tenant_id}", admin_token)
        if s == 200:
            for m in d.get("members", []):
                if m["email"] == "viewer@demo.com":
                    user_id_to_change = m["user_id"]
                    break
    except Exception:
        pass

    if user_id_to_change:
        try:
            s, d = http_post(
                f"{BASE_URL}/api/v1/demo/admin/tenants/{demo_tenant_id}/users/{user_id_to_change}/role",
                body={"new_role": "analyst", "reason": "B29 E2E 测试升级"},
                token=admin_token,
            )
            if s == 200 and isinstance(d, dict) and d.get("new_role") == "analyst":
                log(f"角色变更: viewer→analyst ✓", "PASS")
                results["B29-Role Change"] = "PASS"
            else:
                log(f"角色变更失败: {s} {d}", "FAIL")
                results["B29-Role Change"] = "FAIL"
        except Exception as e:
            log(f"角色变更异常: {e}", "FAIL")
            results["B29-Role Change"] = "FAIL"

        # === 验收 9: 审计验证 ===
        try:
            s, d = http_get(
                f"{BASE_URL}/api/v1/demo/rbac/audit?user_id={user_id_to_change}",
                admin_token,
            )
            if s == 200 and isinstance(d, dict):
                    audit_items = d.get("items", [])
                    has_change = any(
                        it.get("new_role") == "analyst" for it in audit_items
                    )
                    log(
                        f"审计: items={len(audit_items)}, 含变更={has_change}",
                        "PASS" if has_change else "FAIL",
                    )
                    results["B29-Audit"] = "PASS" if has_change else "FAIL"
            else:
                log(f"审计失败: {s} {d}", "FAIL")
                results["B29-Audit"] = "FAIL"
        except Exception as e:
            log(f"审计异常: {e}", "FAIL")
            results["B29-Audit"] = "FAIL"

        # 恢复: 把 analyst 改回 viewer (避免污染环境)
        try:
            http_post(
                f"{BASE_URL}/api/v1/demo/admin/tenants/{demo_tenant_id}/users/{user_id_to_change}/role",
                body={"new_role": "viewer", "reason": "B29 E2E 恢复"},
                token=admin_token,
            )
            log("角色已恢复为 viewer", "INFO")
        except Exception:
            pass

    # 汇总
    print("\n" + "=" * 60)
    print("📊 Phase 6 B29 租户超管后台验收")
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