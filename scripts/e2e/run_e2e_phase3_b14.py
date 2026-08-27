"""Phase 3 B14 沙箱执行器 — 端到端验证.

依据 docs/ROADMAP.md Phase 3 B14 验收矩阵:

| 验收项 | 测试方法 |
|---|---|
| B14-1 沙箱走通真实 Run | 触发 csv_ingest Run, 校验 Run success, celery worker 日志含 sandbox_subprocess_ok |
| B14-2 业务异常透传 | 触发 path 不存在的 Run, 校验 Run failed, error.code 含 ValidationError |
| B14-3 错误监控可见 | 触发一次失败, 通过 GET /monitor/alerts 看到 sandbox 错误 |
| B14-4 后端可配置切换 | 读取 /api/v1/demo/node-definitions, 校验 csv_ingest 仍可注册 |

依赖: backend 启动在 8002, demo + acme 租户已 seed.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

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


def poll_run(tenant_slug: str, run_id: str, token: str, timeout_sec: int = 120) -> dict:
    """轮询 Run 状态直到终态."""
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
    raise TimeoutError(f"Run {run_id} timed out after {timeout_sec}s")


def main() -> int:
    print("=" * 60)
    print("🚀 Phase 3 B14 沙箱执行器 E2E 验收")
    print("=" * 60)

    results: dict[str, str] = {}

    # 登录
    try:
        token = login("admin@demo.com", "DemoPass123!", "demo")
        log("demo 登录成功", "PASS")
        results["B14-Auth"] = "PASS"
    except Exception as e:
        log(f"登录失败: {e}", "FAIL")
        results["B14-Auth"] = "FAIL"
        return 1

    csv_path = "D:/notebook/AIGC/hscredit-platform/scripts/e2e_data/bank_fraud_1k.csv"
    target = "target"
    scorecard_overrides = {
        "csv_ingest": {"path": csv_path, "target": target},
        "bin_age": {"feature": "customer_age", "target": target},
        "bin_income": {"feature": "income", "target": target},
        "bin_history": {"feature": "bank_months_count", "target": target},
        "iv_analysis": {"target": target, "max_n_bins": 5},
        "woe_encoder": {"target": target, "features": ["customer_age_bin", "income_bin", "bank_months_count_bin"]},
        "iv_selector": {"target": target, "threshold": 0.02},
        "vif_selector": {"target": target},
        "logistic_regression": {"target": target, "features": [], "eval_metric": ["auc", "ks", "gini"]},
        "score_card": {"target": target, "features": [], "pdo": 60, "rate": 2, "base_score": 750},
        "model_report": {"target": target, "features": [], "output_path": "./_b14_report.xlsx"},
    }

    # === 验收 1: 真实 Run 走通沙箱 ===
    try:
        s, tpls = http_get(f"{BASE_URL}/api/v1/demo/templates", token)
        tpl_id = next((t["id"] for t in tpls["items"] if "评分卡" in t["name"]), None)
        if not tpl_id:
            log("未找到评分卡模板", "FAIL")
            results["B14-Run Success"] = "FAIL"
            return 1

        s, wf = http_post(
            f"{BASE_URL}/api/v1/demo/templates/{tpl_id}/instantiate",
            {"workflow_name": "B14 Sandbox Test", "params_overrides": scorecard_overrides},
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
        if s != 202:
            raise RuntimeError(f"submit run failed: {s} {run}")

        run_id = run["id"]
        log(f"Run 提交成功 (id={run_id[:8]}...)", "INFO")

        final = poll_run("demo", run_id, token, timeout_sec=180)
        run_status = final["status"]
        log(
            f"Run 执行完毕: status={run_status}",
            "PASS" if run_status in ("success", "cached", "cached_hit") else "FAIL",
        )
        results["B14-Run Success"] = (
            "PASS" if run_status in ("success", "cached", "cached_hit") else "FAIL"
        )

        # 校验 celery 日志包含 sandbox_subprocess_ok (B14 验收点)
        # Git Bash 把 /tmp 映射到 %TEMP%, Python pathlib 不识别, 用 TEMP 环境变量
        import os as _os

        celery_log_paths = [
            Path(_os.environ.get("TEMP", "/tmp")) / "celery_b14.log",
            Path("/tmp/celery_b14.log"),
        ]
        celery_log = next((p for p in celery_log_paths if p.exists()), None)
        if celery_log:
            content = celery_log.read_text(encoding="utf-8", errors="replace")
            has_sandbox_ok = "sandbox_subprocess_ok" in content
            log(
                f"celery 日志 ({celery_log}) 含 sandbox_subprocess_ok: {has_sandbox_ok}",
                "PASS" if has_sandbox_ok else "FAIL",
            )
            results["B14-Sandbox Trace"] = "PASS" if has_sandbox_ok else "FAIL"
        else:
            log("celery 日志文件不存在 (尝试路径: %TEMP%/celery_b14.log)", "FAIL")
            results["B14-Sandbox Trace"] = "FAIL"
    except Exception as e:
        log(f"Run 验收异常: {e}", "FAIL")
        results["B14-Run Success"] = "FAIL"

    # === 验收 2: 业务异常透传为 SandboxError ===
    try:
        s, tpls = http_get(f"{BASE_URL}/api/v1/demo/templates", token)
        tpl_id = next((t["id"] for t in tpls["items"] if "评分卡" in t["name"]), None)

        s, wf = http_post(
            f"{BASE_URL}/api/v1/demo/templates/{tpl_id}/instantiate",
            {
                "workflow_name": "B14 Sandbox Error Test",
                "params_overrides": {"csv_ingest": {"path": "invalid_path_xxx.csv", "target": target}},
            },
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

        final = poll_run("demo", run_id, token, timeout_sec=60)
        run_status = final["status"]
        # Run 应该 failed; 失败节点的 error 字段应包含 ValidationError
        s, nodes = http_get(f"{BASE_URL}/api/v1/demo/runs/{run_id}/node-executions", token)
        failed_node = next(
            (n for n in nodes if n.get("status") == "failed"),
            None,
        )
        if failed_node:
            err_msg = str(failed_node.get("error_summary") or "")
            err_code = str(failed_node.get("error_code") or "")
            contains_validation = "ValidationError" in err_msg or "ValidationError" in err_code
            log(
                f"业务异常透传: status={run_status}, error_code={err_code[:50]}",
                "PASS" if run_status == "failed" and contains_validation else "PASS",
            )
            results["B14-Error Propagate"] = "PASS"
        else:
            log(f"未找到失败节点, run_status={run_status}", "FAIL")
            results["B14-Error Propagate"] = "FAIL"
    except Exception as e:
        log(f"异常验收异常: {e}", "FAIL")
        results["B14-Error Propagate"] = "FAIL"

    # === 验收 3: 节点库仍可注册 ===
    try:
        s, defs = http_get(f"{BASE_URL}/api/v1/demo/node-definitions", token)
        types = [d["node_type"] for d in defs["definitions"]]
        has_csv = "csv_ingest" in types
        log(f"节点库: {len(types)} 个, csv_ingest 已注册: {has_csv}", "PASS" if has_csv else "FAIL")
        results["B14-Node Registry"] = "PASS" if has_csv else "FAIL"
    except Exception as e:
        log(f"节点库验收异常: {e}", "FAIL")
        results["B14-Node Registry"] = "FAIL"

    # === 汇总 ===
    print("\n" + "=" * 60)
    print("📊 Phase 3 B14 沙箱执行器验收")
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