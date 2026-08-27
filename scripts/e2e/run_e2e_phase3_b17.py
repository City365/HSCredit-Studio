"""Phase 3 B17 沙箱资源用量埋点 — 端到端验证.

依据 docs/ROADMAP.md Phase 3 B17 验收矩阵:

| 验收项 | 测试方法 |
|---|---|
| B17-1 表存在 | 直接 SQL 查 node_resource_usage 表 |
| B17-2 落库成功 | 触发真实 Run 后, 表里有新记录 |
| B17-3 字段完整 | 记录含 node_type/duration_ms/status/sandbox_backend |
| B17-4 duration_ms > 0 | 实际节点执行, 时长非零 |
| B17-5 celery 日志 | 包含 resource_usage_recorded 事件 |
| B17-6 status=success | 正常路径 status 不为 failed/timeout |

依赖: backend + celery 启动在 8002.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "http://localhost:8002"
REPO_POSIX = "/d/notebook/AIGC/hscredit-platform"
BASH_EXE = "D:/notebook/software/git/Git/usr/bin/bash.exe"
REPO_WIN = "D:\\notebook\\AIGC\\hscredit-platform"


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
        with urllib.request.urlopen(req, timeout=60) as resp:
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


def poll_run(tenant_slug: str, run_id: str, token: str, timeout_sec: int = 180) -> dict:
    start = time.time()
    while time.time() - start < timeout_sec:
        s, run = http_get(f"{BASE_URL}/api/v1/{tenant_slug}/runs/{run_id}", token)
        if s != 200:
            time.sleep(1.5)
            continue
        status = run.get("status")
        if status in ("success", "failed", "cancelled", "cached", "cached_hit"):
            return run
        time.sleep(2)
    raise TimeoutError(f"Run {run_id} timed out")


def query_db(sql: str) -> list[dict]:
    """通过 asyncpg 直接查 DB."""
    import asyncpg

    async def _run():
        conn = await asyncpg.connect("postgresql://postgres:root@localhost:5432/postgres")
        rows = await conn.fetch(sql)
        await conn.close()
        return [dict(r) for r in rows]

    return asyncio.run(_run())


def main() -> int:
    print("=" * 60)
    print("🚀 Phase 3 B17 资源用量埋点 E2E 验收")
    print("=" * 60)

    results: dict[str, str] = {}

    # === 验收 1: 表存在 ===
    try:
        rows = query_db(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'node_resource_usage') AS exists"
        )
        exists = rows[0]["exists"] if rows else False
        log(f"node_resource_usage 表存在: {exists}", "PASS" if exists else "FAIL")
        results["B17-Table Exists"] = "PASS" if exists else "FAIL"
    except Exception as e:
        log(f"表存在性检查异常: {e}", "FAIL")
        results["B17-Table Exists"] = "FAIL"

    # 登录
    try:
        token = login("admin@demo.com", "DemoPass123!", "demo")
        log("demo 登录成功", "PASS")
    except Exception as e:
        log(f"登录失败: {e}", "FAIL")
        return 1

    # 取记录数 (基线)
    try:
        before = query_db("SELECT COUNT(*) AS cnt FROM node_resource_usage")
        baseline_count = int(before[0]["cnt"])
        log(f"基线记录数: {baseline_count}", "INFO")
    except Exception as e:
        log(f"基线查询失败: {e}", "FAIL")
        baseline_count = 0

    # 清 Redis 缓存, 强制真实沙箱执行 (不走 cached_hit 路径)
    import subprocess

    subprocess.run(
        [BASH_EXE, "-c", "redis-cli FLUSHALL 2>&1 || echo 'redis flush done'"],
        capture_output=True,
        timeout=10,
        check=False,
    )

    # 触发一个真实 Run
    csv_path = "D:/notebook/AIGC/hscredit-platform/scripts/e2e_data/bank_fraud_1k.csv"
    target = "target"
    overrides = {
        "csv_ingest": {"path": csv_path, "target": target},
        "field_type_infer": {"target": target},
        "bin_age": {"feature": "customer_age", "target": target},
        "bin_income": {"feature": "income", "target": target},
        "bin_history": {"feature": "bank_months_count", "target": target},
        "iv_analysis": {"target": target, "max_n_bins": 5},
        "iv_selector": {"target": target, "threshold": 0.02},
        "vif_selector": {"target": target},
        "optimal_binning_chi": {"feature": "customer_age", "target": target, "max_n_bins": 5},
        "woe_encoder": {"target": target, "features": ["customer_age_bin", "income_bin", "bank_months_count_bin"]},
        "logistic_regression": {"target": target, "features": [], "eval_metric": ["auc", "ks", "gini"]},
        "score_card": {"target": target, "features": [], "pdo": 60, "rate": 2, "base_score": 750},
        "model_report": {"target": target, "features": [], "output_path": "./_b17_report.xlsx"},
    }

    # === 验收 2: 落库成功 ===
    try:
        s, tpls = http_get(f"{BASE_URL}/api/v1/demo/templates", token)
        tpl_id = next((t["id"] for t in tpls["items"] if "评分卡" in t["name"]), None)
        s, wf = http_post(
            f"{BASE_URL}/api/v1/demo/templates/{tpl_id}/instantiate",
            {"workflow_name": "B17 Resource Test", "params_overrides": overrides},
            token,
        )
        wf_id = wf["id"]
        s, versions = http_get(f"{BASE_URL}/api/v1/demo/workflows/{wf_id}/versions", token)
        ver_id = versions[0]["id"]
        s, run = http_post(
            f"{BASE_URL}/api/v1/demo/workflows/{wf_id}/runs",
            {"workflow_version_id": ver_id},
            token,
        )
        run_id = run["id"]
        log(f"Run 提交成功 (id={run_id[:8]}...)", "INFO")

        final = poll_run("demo", run_id, token, timeout_sec=180)
        log(f"Run 完成: status={final['status']}", "INFO")

        # 等异步落库 2s
        time.sleep(2)

        after = query_db("SELECT COUNT(*) AS cnt FROM node_resource_usage")
        new_count = int(after[0]["cnt"])
        delta = new_count - baseline_count
        log(f"新增记录数: {delta} (baseline={baseline_count}, now={new_count})", "PASS" if delta > 0 else "FAIL")
        results["B17-Records Inserted"] = "PASS" if delta > 0 else "FAIL"
    except Exception as e:
        log(f"落库验证异常: {e}", "FAIL")
        results["B17-Records Inserted"] = "FAIL"
        return 1

    # === 验收 3: 字段完整 ===
    try:
        rows = query_db(
            """SELECT node_type, duration_ms, status, sandbox_backend, captured_at
               FROM node_resource_usage
               ORDER BY captured_at DESC LIMIT 5"""
        )
        if rows:
            sample = rows[0]
            required = {"node_type", "duration_ms", "status", "sandbox_backend", "captured_at"}
            missing = required - set(sample.keys())
            log(f"字段完整 (sample): missing={missing}", "PASS" if not missing else "FAIL")
            results["B17-Field Schema"] = "PASS" if not missing else "FAIL"
        else:
            log("无样本记录", "FAIL")
            results["B17-Field Schema"] = "FAIL"
    except Exception as e:
        log(f"字段检查异常: {e}", "FAIL")
        results["B17-Field Schema"] = "FAIL"

    # === 验收 4: duration_ms > 0 ===
    try:
        rows = query_db(
            "SELECT duration_ms FROM node_resource_usage WHERE duration_ms > 0 LIMIT 1"
        )
        ok = rows and int(rows[0]["duration_ms"]) > 0
        log(f"duration_ms > 0: {ok}", "PASS" if ok else "FAIL")
        results["B17-Duration Positive"] = "PASS" if ok else "FAIL"
    except Exception as e:
        log(f"duration_ms 检查异常: {e}", "FAIL")
        results["B17-Duration Positive"] = "FAIL"

    # === 验收 5: status=success + sandbox_backend=subprocess ===
    try:
        rows = query_db(
            """SELECT status, sandbox_backend, COUNT(*) AS cnt
               FROM node_resource_usage
               GROUP BY status, sandbox_backend"""
        )
        ok_rows = [r for r in rows if r["status"] == "success" and r["sandbox_backend"] == "subprocess"]
        log(f"成功记录分布: {rows}", "PASS" if ok_rows else "FAIL")
        results["B17-Success Records"] = "PASS" if ok_rows else "FAIL"
    except Exception as e:
        log(f"status 检查异常: {e}", "FAIL")
        results["B17-Success Records"] = "FAIL"

    # === 汇总 ===
    print("\n" + "=" * 60)
    print("📊 Phase 3 B17 资源用量埋点验收")
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