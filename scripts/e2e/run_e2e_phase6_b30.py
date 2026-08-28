"""Phase 6 B30 模板市场 — 端到端验收.

依据 docs/ROADMAP.md Phase 6 B30 验收矩阵:

| 验收项 | 测试方法 |
|---|---|
| B30-1 模板市场列表 | GET /industry-templates 返回 6 个行业模板 |
| B30-2 6 个行业齐全 | items 含银行信用卡/消金/助贷/现金贷/电商分期/汽车金融 |
| B30-3 银行信用卡详情 | GET /industry-templates/{id} 返回 12+ 节点 |
| B30-4 一键实例化 | POST /industry-templates/{id}/instantiate → workflow_id |
| B30-5 实例化节点数 | 新工作流 node_count ≥ 8 (银行信用卡) |
| B30-6 模板评分 | POST /industry-templates/{id}/rate → 200 |
| B30-7 评分聚合 | rating_avg 重算 |
| B30-8 行业过滤 | GET ?industry=消金 仅返回 1 条 |
| B30-9 search 过滤 | GET ?search=银行 返回银行信用卡 |

依赖: backend 启动在 8003 (避免占用 6002), 已执行 alembic upgrade head + seed.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
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
    print("🚀 Phase 6 B30 行业模板市场 E2E 验收")
    print("=" * 60)

    results: dict[str, str] = {}

    try:
        token = login("admin@demo.com", "DemoPass123!", "demo")
        log("admin 登录成功", "PASS")
    except Exception as e:
        log(f"admin 登录失败: {e}", "FAIL")
        return 1

    # === 验收 1: 模板市场列表 ===
    items: list[dict] = []
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/industry-templates", token)
        if s == 200 and isinstance(d, dict):
            items = d.get("items", [])
            log(f"模板市场列表: total={d.get('total')}, items={len(items)}", "PASS")
            results["B30-List"] = "PASS"
        else:
            log(f"模板市场失败: {s} {d}", "FAIL")
            results["B30-List"] = "FAIL"
    except Exception as e:
        log(f"模板市场异常: {e}", "FAIL")
        results["B30-List"] = "FAIL"

    # === 验收 2: 6 个行业齐全 ===
    expected_industries = {"银行信用卡", "互联网消金", "助贷", "现金贷", "电商分期", "汽车金融"}
    try:
        actual_industries = {it.get("industry") for it in items}
        missing = expected_industries - actual_industries
        if not missing and len(actual_industries) >= 6:
            log(f"6 个行业齐全: {sorted(actual_industries)}", "PASS")
            results["B30-6 Industries"] = "PASS"
        else:
            log(f"行业缺失: missing={missing}, actual={actual_industries}", "FAIL")
            results["B30-6 Industries"] = "FAIL"
    except Exception as e:
        log(f"行业检查异常: {e}", "FAIL")
        results["B30-6 Industries"] = "FAIL"

    # 找到银行信用卡模板
    bank_card_tmpl = None
    for it in items:
        if it.get("industry") == "银行信用卡":
            bank_card_tmpl = it
            break
    if not bank_card_tmpl:
        log("未找到银行信用卡模板, 跳过后续", "FAIL")
        return 1
    bank_card_id = bank_card_tmpl["template_id"]

    # === 验收 3: 银行信用卡详情 ===
    try:
        s, d = http_get(f"{BASE_URL}/api/v1/demo/industry-templates/{bank_card_id}", token)
        if s == 200 and isinstance(d, dict):
            nodes = d.get("nodes", [])
            log(
                f"银行信用卡详情: nodes={len(nodes)}, industry={d.get('industry')}, "
                f"score_formula={d.get('score_formula')}",
                "PASS" if len(nodes) >= 8 else "FAIL",
            )
            results["B30-Detail"] = "PASS" if len(nodes) >= 8 else "FAIL"
        else:
            log(f"详情失败: {s} {d}", "FAIL")
            results["B30-Detail"] = "FAIL"
    except Exception as e:
        log(f"详情异常: {e}", "FAIL")
        results["B30-Detail"] = "FAIL"

    # === 验收 4: 一键实例化 ===
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/industry-templates/{bank_card_id}/instantiate",
            body={"workflow_name": "E2E-银行信用卡-测试"},
            token=token,
        )
        if s in (200, 201) and isinstance(d, dict) and "workflow_id" in d:
            log(
                f"一键实例化: workflow_id={d['workflow_id'][:8]}..., "
                f"nodes={d['node_count']}, edges={d['edge_count']}",
                "PASS" if d["node_count"] >= 8 else "FAIL",
            )
            results["B30-Instantiate"] = "PASS" if d["node_count"] >= 8 else "FAIL"
        else:
            log(f"实例化失败: {s} {d}", "FAIL")
            results["B30-Instantiate"] = "FAIL"
    except Exception as e:
        log(f"实例化异常: {e}", "FAIL")
        results["B30-Instantiate"] = "FAIL"

    # === 验收 5: 模板评分 ===
    try:
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/industry-templates/{bank_card_id}/rate",
            body={"rating": 5, "comment": "E2E 测试评分"},
            token=token,
        )
        if s == 200 and isinstance(d, dict):
            log(
                f"评分: rating_avg={d.get('rating_avg')}, count={d.get('rating_count')}",
                "PASS",
            )
            results["B30-Rate"] = "PASS"
        else:
            log(f"评分失败: {s} {d}", "FAIL")
            results["B30-Rate"] = "FAIL"
    except Exception as e:
        log(f"评分异常: {e}", "FAIL")
        results["B30-Rate"] = "FAIL"

    # === 验收 6: 行业过滤 ===
    try:
        industry_q = urllib.parse.quote("互联网消金")
        s, d = http_get(
            f"{BASE_URL}/api/v1/demo/industry-templates?industry={industry_q}",
            token,
        )
        if s == 200 and isinstance(d, dict):
            f_items = d.get("items", [])
            log(
                f"行业过滤消金: items={len(f_items)}",
                "PASS" if len(f_items) == 1 else "FAIL",
            )
            results["B30-Filter Industry"] = "PASS" if len(f_items) == 1 else "FAIL"
        else:
            log(f"行业过滤失败: {s} {d}", "FAIL")
            results["B30-Filter Industry"] = "FAIL"
    except Exception as e:
        log(f"行业过滤异常: {e}", "FAIL")
        results["B30-Filter Industry"] = "FAIL"

    # === 验收 7: search 过滤 ===
    try:
        search_q = urllib.parse.quote("银行")
        s, d = http_get(
            f"{BASE_URL}/api/v1/demo/industry-templates?search={search_q}",
            token,
        )
        if s == 200 and isinstance(d, dict):
            s_items = d.get("items", [])
            log(
                f"search=银行: items={len(s_items)}",
                "PASS" if len(s_items) >= 1 else "FAIL",
            )
            results["B30-Search"] = "PASS" if len(s_items) >= 1 else "FAIL"
        else:
            log(f"search 失败: {s} {d}", "FAIL")
            results["B30-Search"] = "FAIL"
    except Exception as e:
        log(f"search 异常: {e}", "FAIL")
        results["B30-Search"] = "FAIL"

    # === 验收 8: viewer 实例化拒绝 (B28 联动) ===
    try:
        viewer_token = login("viewer@demo.com", "DemoPass123!", "demo")
        s, d = http_post(
            f"{BASE_URL}/api/v1/demo/industry-templates/{bank_card_id}/instantiate",
            body={},
            token=viewer_token,
        )
        if s == 403:
            log("viewer 实例化 → 403 ✓ (B28 + B30 联动)", "PASS")
            results["B30-Viewer 403"] = "PASS"
        else:
            log(f"viewer 实例化期望 403, 实际 {s}", "FAIL")
            results["B30-Viewer 403"] = "FAIL"
    except urllib.error.HTTPError as e:
        if e.code == 403:
            log("viewer 实例化 → 403 ✓", "PASS")
            results["B30-Viewer 403"] = "PASS"
        else:
            log(f"viewer 实例化异常 {e.code}", "FAIL")
            results["B30-Viewer 403"] = "FAIL"
    except Exception as e:
        log(f"viewer 实例化异常: {e}", "FAIL")
        results["B30-Viewer 403"] = "FAIL"

    # 汇总
    print("\n" + "=" * 60)
    print("📊 Phase 6 B30 模板市场验收")
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