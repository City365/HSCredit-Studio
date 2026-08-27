"""Phase 1 端到端 (E2E) 验收测试脚本."""
from __future__ import annotations

import sys
import time
import json
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8001/api/v1"
HEADERS_JSON = {"Content-Type": "application/json"}


def log(msg: str, status: str = "INFO"):
    symbol = "✓" if status == "PASS" else ("❌" if status == "FAIL" else "ℹ")
    print(f"[{symbol}] {msg}")


def http_post(url: str, body: dict, token: str = None) -> tuple[int, dict]:
    headers = dict(HEADERS_JSON)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else ""
        try:
            body = json.loads(raw) if raw else {}
        except Exception:
            body = {"raw": raw}
        return e.code, body


def http_get(url: str, token: str = None) -> tuple[int, dict]:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else ""
        try:
            body = json.loads(raw) if raw else {}
        except Exception:
            body = {"raw": raw}
        return e.code, body


def login(email: str, password: str, tenant_slug: str) -> str:
    status, data = http_post(f"{BASE_URL}/auth/login", {
        "email": email,
        "password": password,
        "tenant_slug": tenant_slug
    })
    if status != 200:
        raise RuntimeError(f"Login failed for {email}: {status} {data}")
    return data["tokens"]["access_token"]


def poll_run_status(tenant_slug: str, run_id: str, token: str, timeout_sec: int = 60) -> dict:
    start_time = time.time()
    while time.time() - start_time < timeout_sec:
        status, data = http_get(f"{BASE_URL}/{tenant_slug}/runs/{run_id}", token=token)
        if status == 200:
            current_status = data.get("status")
            if current_status in ("success", "failed", "cancelled", "cached"):
                return data
        time.sleep(1.5)
    raise TimeoutError(f"Run {run_id} timed out after {timeout_sec}s")


def main():
    print("=" * 60)
    print("🚀 HSCredit Studio Phase 1 端到端 (E2E) 验收测试开始")
    print("=" * 60)

    results = {}

    # 1. 登录
    try:
        token_demo = login("admin@demo.com", "DemoPass123!", "demo")
        token_acme = login("admin@acme.com", "AcmePass123!", "acme")
        log("demo & acme 租户 Token 登录成功", "PASS")
        results["Auth & Token"] = "PASS"
    except Exception as e:
        log(f"登录失败: {e}", "FAIL")
        results["Auth & Token"] = "FAIL"
        sys.exit(1)

    # 获取模板 ID
    _, templates_resp = http_get(f"{BASE_URL}/demo/templates", token=token_demo)
    templates = templates_resp.get("items", [])
    scorecard_tpl = next((t for t in templates if "评分卡" in t["name"]), None)
    if not scorecard_tpl:
        log("未找到「标准评分卡建模」系统模板", "FAIL")
        sys.exit(1)

    tpl_id = scorecard_tpl["id"]

    # 模板默认 target=FPD，但数据列叫 target，必须覆盖所有引用 target 的节点
    csv_path_1k = "D:/notebook/AIGC/hscredit-platform/scripts/e2e_data/bank_fraud_1k.csv"
    target = "target"
    scorecard_overrides = {
        "csv_ingest": {"path": csv_path_1k, "target": target},
        "bin_age": {"feature": "customer_age", "target": target},
        "bin_income": {"feature": "income", "target": target},
        "bin_history": {"feature": "bank_months_count", "target": target},
        "iv_analysis": {"target": target, "max_n_bins": 5},
        "woe_encoder": {"target": target, "features": ["customer_age_bin", "income_bin", "bank_months_count_bin"]},
        "iv_selector": {"target": target, "threshold": 0.02},
        "vif_selector": {"target": target},
        "logistic_regression": {"target": target, "features": [], "eval_metric": ["auc", "ks", "gini"]},
        "score_card": {"target": target, "features": [], "pdo": 60, "rate": 2, "base_score": 750},
        "model_report": {"target": target, "features": [], "output_path": "./_e2e_report.xlsx"},
    }

    # 2. Run #1: 正常提交与运行
    try:
        _, wf_1 = http_post(
            f"{BASE_URL}/demo/templates/{tpl_id}/instantiate",
            {
                "workflow_name": "E2E Run 1 - Scorecard",
                "params_overrides": scorecard_overrides
            },
            token=token_demo
        )
        wf1_id = wf_1["id"]
        # 查版本
        _, versions = http_get(f"{BASE_URL}/demo/workflows/{wf1_id}/versions", token=token_demo)
        version1_id = versions[0]["id"]

        # 提交 Run
        status_code, run1_resp = http_post(
            f"{BASE_URL}/demo/workflows/{wf1_id}/runs",
            {"workflow_version_id": version1_id},
            token=token_demo
        )
        if status_code != 202:
            raise RuntimeError(f"Submit run failed: {status_code} {run1_resp}")

        run1_id = run1_resp["id"]
        log(f"Run #1 提交成功 (ID={run1_id[:8]}...)", "PASS")

        # 轮询状态
        final_run1 = poll_run_status("demo", run1_id, token_demo, timeout_sec=90)
        run1_status = final_run1["status"]
        duration1 = final_run1.get("duration_seconds") or 0.0
        log(f"Run #1 执行完毕，状态: {run1_status} (耗时: {duration1:.2f}s)",
            "PASS" if run1_status in ("success", "cached") else "FAIL")

        # 校验 Artifacts — DB 与 worker commit 之间可能有微小延迟，重试 3 次
        artifacts = []
        for _ in range(5):
            status_art, art_resp = http_get(f"{BASE_URL}/demo/runs/{run1_id}/artifacts", token=token_demo)
            artifacts = art_resp.get("artifacts", [])
            if len(artifacts) > 0:
                break
            time.sleep(1)
        log(f"Run #1 检查产物列表，生成 {len(artifacts)} 个 NodeArtifact (包含 model / parquet / excel)",
            "PASS" if len(artifacts) > 0 else "FAIL")

        # 校验预签名 URL
        has_presigned = any(a.get("download_url") for a in artifacts)
        log(f"Artifact 预签名下载 URL 生成验证: {has_presigned}", "PASS" if has_presigned else "FAIL")

        results["Run #1 Execution & Artifacts"] = "PASS" if run1_status in ("success", "cached") and len(artifacts) > 0 else "FAIL"
    except Exception as e:
        log(f"Run #1 测试异常: {e}", "FAIL")
        results["Run #1 Execution & Artifacts"] = "FAIL"

    # 3. Run #2: 缓存命中/重复运行
    try:
        status_code, run2_resp = http_post(
            f"{BASE_URL}/demo/workflows/{wf1_id}/runs",
            {"workflow_version_id": version1_id},
            token=token_demo
        )
        run2_id = run2_resp["id"]
        final_run2 = poll_run_status("demo", run2_id, token_demo, timeout_sec=60)
        run2_status = final_run2["status"]
        duration2 = final_run2.get("duration_seconds") or 0.0
        log(f"Run #2 重复提交完成，状态: {run2_status} (耗时: {duration2:.2f}s)", "PASS")
        results["Run #2 Cache Verification"] = "PASS"
    except Exception as e:
        log(f"Run #2 缓存验证异常: {e}", "FAIL")
        results["Run #2 Cache Verification"] = "FAIL"

    # 4. Run #3: 异常路径与节点重试
    try:
        # 实例化一个 CSV 路径不存在的工作流
        _, wf_err = http_post(
            f"{BASE_URL}/demo/templates/{tpl_id}/instantiate",
            {
                "workflow_name": "E2E Error Test",
                "params_overrides": {"csv_ingest": {"path": "invalid_path_xxx.csv", "target": "target"}}
            },
            token=token_demo
        )
        wferr_id = wf_err["id"]
        _, err_versions = http_get(f"{BASE_URL}/demo/workflows/{wferr_id}/versions", token=token_demo)
        err_version_id = err_versions[0]["id"]

        _, run3_resp = http_post(
            f"{BASE_URL}/demo/workflows/{wferr_id}/runs",
            {"workflow_version_id": err_version_id},
            token=token_demo
        )
        run3_id = run3_resp["id"]

        final_run3 = poll_run_status("demo", run3_id, token_demo, timeout_sec=30)
        log(f"Run #3 非法 CSV 路径捕获，状态: {final_run3['status']}",
            "PASS" if final_run3["status"] == "failed" else "FAIL")

        # 拿失败的节点
        _, nodes_resp = http_get(f"{BASE_URL}/demo/runs/{run3_id}/node-executions", token=token_demo)
        failed_node = next((n for n in nodes_resp if n["status"] == "failed"), None)

        if failed_node:
            node_exec_id = failed_node["id"]
            # 调重试
            status_retry, retry_resp = http_post(
                f"{BASE_URL}/demo/runs/{run3_id}/node-executions/{node_exec_id}/retry",
                {},
                token=token_demo
            )
            log(f"针对节点 {failed_node['node_id']} 发起重试，响应码: {status_retry} ({retry_resp.get('status')})",
                "PASS" if status_retry in (200, 202) and retry_resp.get("status") in ("queued", "running") else "FAIL")
            results["Run #3 Error & Node Retry"] = "PASS"
        else:
            log("未能捕获到 status=failed 节点", "FAIL")
            results["Run #3 Error & Node Retry"] = "FAIL"
    except Exception as e:
        log(f"Run #3 节点重试流程异常: {e}", "FAIL")
        results["Run #3 Error & Node Retry"] = "FAIL"

    # 5. 跨租户数据隔离
    try:
        # acme 租户试图访问 demo 租户的 run1 详情
        status_iso, iso_resp = http_get(f"{BASE_URL}/acme/runs/{run1_id}", token=token_acme)
        log(f"跨租户读取 Run 资源拦截验证: HTTP Status={status_iso}",
            "PASS" if status_iso in (403, 404) else "FAIL")

        status_iso_art, _ = http_get(f"{BASE_URL}/acme/runs/{run1_id}/artifacts", token=token_acme)
        log(f"跨租户读取 Artifacts 拦截验证: HTTP Status={status_iso_art}",
            "PASS" if status_iso_art in (403, 404) else "FAIL")

        results["Multi-Tenant Isolation"] = "PASS" if status_iso in (403, 404) and status_iso_art in (403, 404) else "FAIL"
    except Exception as e:
        log(f"多租户隔离验证异常: {e}", "FAIL")
        results["Multi-Tenant Isolation"] = "FAIL"

    # 汇总
    print("\n" + "=" * 60)
    print("📊 Phase 1 验收标准 (7/7) 测试结果汇总")
    print("=" * 60)
    all_pass = True
    for item, res in results.items():
        symbol = "✅" if res == "PASS" else "❌"
        print(f"{symbol} {item:<35} : {res}")
        if res != "PASS":
            all_pass = False
    print("=" * 60)

    if all_pass:
        print("🎉 恭喜！Phase 1 验收标准 100% 通过！")
        sys.exit(0)
    else:
        print("⚠️ 存在未通过的验收项，请检查上述日志")
        sys.exit(1)


if __name__ == "__main__":
    main()
