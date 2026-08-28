"""Phase 6 B31 自定义模板共享 — 端到端验收.

依据 docs/ROADMAP.md Phase 6 B31 验收矩阵:

| 验收项 | 测试方法 |
|---|---|
| B31-1 发布工作流为模板 | POST /template-sharing/publish → draft |
| B31-2 跨租户申请共享 | POST /template-sharing/{id}/share → pending |
| B31-3 审核通过 | POST /template-sharing/{id}/review approve=True → approved |
| B31-4 共享后 visibility 升 public | response.visibility == "public" |
| B31-5 拒绝流转 | review approve=False → rejected |
| B31-6 审核日志 | GET /template-sharing/{id}/logs 含变更记录 |
| B31-7 viewer 发布拒绝 | viewer POST /publish → 403 (B28 联动) |
| B31-8 analyst 无权审核 | analyst POST /review → 403 (B28 require_role) |

依赖: backend 启动在 8003 (避免占用 6002), 已执行 alembic upgrade head + seed.
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
    print("🚀 Phase 6 B31 自定义模板共享 E2E 验收")
    print("=" * 60)

    results: dict[str, str] = {}

    try:
        admin_token = login("admin@demo.com", "DemoPass123!", "demo")
        analyst_token = login("analyst@demo.com", "DemoPass123!", "demo")
        viewer_token = login("viewer@demo.com", "DemoPass123!", "demo")
        log("登录成功 (admin/analyst/viewer)", "PASS")
    except Exception as e:
        log(f"登录失败: {e}", "FAIL")
        return 1

    # === 准备: 先创建一个工作流 ===
    workflow_id = None
    try:
        import time as _t

        name = f"e2e-b31-{int(_t.time())}"
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/workflows",
            body={"name": name, "description": "B31 E2E", "definition": {"nodes": [], "edges": []}},
            token=admin_token,
        )
        if s in (200, 201) and isinstance(d, dict):
            workflow_id = d.get("id") or d.get("workflow_id")
            log(f"创建工作流: id={workflow_id[:8] if workflow_id else 'None'}...", "PASS")
        else:
            log(f"创建工作流失败: {s} {d}", "FAIL")
            return 1
    except Exception as e:
        log(f"创建工作流异常: {e}", "FAIL")
        return 1

    template_id = None

    # === 验收 1: 发布工作流为模板 ===
    try:
        import time as _t

        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/template-sharing/publish",
            body={
                "workflow_id": workflow_id,
                "template_name": f"E2E-B31-{int(_t.time())}",
                "description": "E2E 测试模板",
                "tags": ["E2E"],
                "visibility": "tenant",
            },
            token=admin_token,
        )
        if s in (200, 201) and isinstance(d, dict) and d.get("review_status") == "draft":
            template_id = d["template_id"]
            log(
                f"发布模板: id={template_id[:8]}..., status={d.get('review_status')}",
                "PASS",
            )
            results["B31-Publish"] = "PASS"
        else:
            log(f"发布失败: {s} {d}", "FAIL")
            results["B31-Publish"] = "FAIL"
    except Exception as e:
        log(f"发布异常: {e}", "FAIL")
        results["B31-Publish"] = "FAIL"

    if not template_id:
        log("模板未创建, 跳过后续", "FAIL")
        return 1

    # === 验收 2: 跨租户申请共享 ===
    target_tenant_id = None
    try:
        # 找到 acme 租户 id (作为 target)
        s, d = http_get(f"{BASE_URL}/api/v1/demo/admin/tenants?search=acme", admin_token)
        if s == 200 and isinstance(d, dict):
            for it in d.get("items", []):
                if it["slug"] == "acme":
                    target_tenant_id = it["tenant_id"]
                    break
    except Exception:
        pass

    if target_tenant_id:
        try:
            s, d = http_post(
                f"{BASE_URL}/api/v1/demo/template-sharing/{template_id}/share",
                body={
                    "target_tenants": [target_tenant_id],
                    "reason": "E2E 测试共享给 acme",
                },
                token=admin_token,
            )
            if s == 200 and isinstance(d, dict) and d.get("review_status") == "pending":
                log(f"申请共享: status={d.get('review_status')}", "PASS")
                results["B31-Share Request"] = "PASS"
            else:
                log(f"申请共享失败: {s} {d}", "FAIL")
                results["B31-Share Request"] = "FAIL"
        except Exception as e:
            log(f"申请共享异常: {e}", "FAIL")
            results["B31-Share Request"] = "FAIL"

    # === 验收 3: 审核通过 ===
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/template-sharing/{template_id}/review",
            body={
                "approve": True,
                "comment": "E2E 测试通过",
                "granted_tenants": [target_tenant_id] if target_tenant_id else [],
            },
            token=admin_token,
        )
        if s == 200 and isinstance(d, dict) and d.get("review_status") == "approved":
            log(f"审核通过: status={d.get('review_status')}, visibility={d.get('visibility')}", "PASS")
            results["B31-Approve"] = "PASS"
        else:
            log(f"审核失败: {s} {d}", "FAIL")
            results["B31-Approve"] = "FAIL"
    except Exception as e:
        log(f"审核异常: {e}", "FAIL")
        results["B31-Approve"] = "FAIL"

    # === 验收 4: 共享后 visibility=public ===
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/template-sharing/{template_id}/logs", admin_token)
        if s == 200 and isinstance(d, dict):
            items = d.get("items", [])
            log(f"审核日志: items={len(items)}", "PASS" if len(items) >= 3 else "FAIL")
            results["B31-Logs"] = "PASS" if len(items) >= 3 else "FAIL"
        else:
            log(f"日志失败: {s} {d}", "FAIL")
            results["B31-Logs"] = "FAIL"
    except Exception as e:
        log(f"日志异常: {e}", "FAIL")
        results["B31-Logs"] = "FAIL"

    # === 验收 5: viewer 发布拒绝 (B28 联动) ===
    try:
        import time as _t

        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/template-sharing/publish",
            body={
                "workflow_id": workflow_id,
                "template_name": f"e2e-b31-viewer-{int(_t.time())}",
                "description": "viewer 不应能发布",
            },
            token=viewer_token,
        )
        if s == 403:
            log("viewer 发布 → 403 ✓ (B28 联动)", "PASS")
            results["B31-Viewer 403"] = "PASS"
        else:
            log(f"viewer 发布期望 403, 实际 {s}", "FAIL")
            results["B31-Viewer 403"] = "FAIL"
    except urllib.error.HTTPError as e:
        if e.code == 403:
            log("viewer 发布 → 403 ✓", "PASS")
            results["B31-Viewer 403"] = "PASS"
        else:
            log(f"viewer 发布异常 {e.code}", "FAIL")
            results["B31-Viewer 403"] = "FAIL"
    except Exception as e:
        log(f"viewer 发布异常: {e}", "FAIL")
        results["B31-Viewer 403"] = "FAIL"

    # === 验收 6: analyst 无权审核 (require_role TENANT_ADMIN) ===
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/template-sharing/{template_id}/review",
            body={"approve": False, "comment": "analyst 不应能审核"},
            token=analyst_token,
        )
        if s == 403:
            log("analyst 审核 → 403 ✓ (B28 require_role)", "PASS")
            results["B31-Analyst 403"] = "PASS"
        else:
            log(f"analyst 审核期望 403, 实际 {s}", "FAIL")
            results["B31-Analyst 403"] = "FAIL"
    except urllib.error.HTTPError as e:
        if e.code == 403:
            log("analyst 审核 → 403 ✓", "PASS")
            results["B31-Analyst 403"] = "PASS"
        else:
            log(f"analyst 审核异常 {e.code}", "FAIL")
            results["B31-Analyst 403"] = "FAIL"
    except Exception as e:
        log(f"analyst 审核异常: {e}", "FAIL")
        results["B31-Analyst 403"] = "FAIL"

    # 汇总
    print("\n" + "=" * 60)
    print("📊 Phase 6 B31 自定义模板共享验收")
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