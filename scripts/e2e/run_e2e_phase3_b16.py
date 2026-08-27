"""Phase 3 B16 备份升级 — 端到端验证.

依据 docs/ROADMAP.md Phase 3 B16 验收矩阵:

| 验收项 | 测试方法 |
|---|---|
| B16-1 WAL hint 文件 | 跑 backup.sh --db-only, 校验 backup_metadata.json 含 pg_lsn_at_backup |
| B16-2 SHA-256 校验 | 跑 backup.sh --verify <dir>, 校验返回码 0 |
| B16-3 健康检查 JSON | 跑 backup.sh --status, 校验返回合法 JSON + healthy 字段 |
| B16-4 元数据 schema | 校验 backup_metadata.json 含 backup_type / pg_dump_format 字段 |
| B16-5 help 含新参数 | 校验 usage 输出含 --status / --verify |

注: 本地 dev 无 pg_dump, 测试用 mock + 真实目录结构验证脚本逻辑。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

REPO_POSIX = "/d/notebook/AIGC/hscredit-platform"
REPO_WIN = "D:\\notebook\\AIGC\\hscredit-platform"
# Windows 系统 bash 默认为 bash.exe (WSL), Python subprocess 找不到 Git Bash
# 显式指定 Git Bash 路径, 确保执行环境一致
BASH_EXE = "D:/notebook/software/git/Git/usr/bin/bash.exe"
POSIX_TEST_BACKUP_DIR = "/tmp/backup_b16_test"


def log(msg: str, status: str = "INFO") -> None:
    symbol = "✓" if status == "PASS" else ("❌" if status == "FAIL" else "ℹ")
    print(f"[{symbol}] {msg}")


def _run_bash(cmd: str, check: bool = False) -> tuple[int, str]:
    """运行 bash -c 命令, 返回 (rc, stdout)."""
    proc = subprocess.run(
        [BASH_EXE, "-c", cmd],
        capture_output=True,
        cwd=REPO_WIN,
        env=os.environ.copy(),
        timeout=60,
    )
    out = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
    err = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
    import re as _re

    out = _re.sub(r"\033\[[0-9;]*m", "", out)
    err = _re.sub(r"\033\[[0-9;]*m", "", err)
    return proc.returncode, out + err


def run_backup(args: list[str], env_extra: dict[str, str] | None = None) -> tuple[int, str]:
    """运行 backup.sh, 返回 (returncode, stdout+stderr)."""
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [BASH_EXE, "scripts/backup.sh"] + args,
        capture_output=True,
        cwd=REPO_WIN,
        env=env,
        timeout=60,
    )
    out = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
    err = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
    import re as _re

    out = _re.sub(r"\033\[[0-9;]*m", "", out)
    err = _re.sub(r"\033\[[0-9;]*m", "", err)
    if proc.returncode != 0:
        print(f"  [DEBUG backup.sh exit={proc.returncode}] stdout: {out[:300]}")
        print(f"  [DEBUG backup.sh exit={proc.returncode}] stderr: {err[:300]}")
    return proc.returncode, out + err


def main() -> int:
    print("=" * 60)
    print("🚀 Phase 3 B16 备份升级 E2E 验收")
    print("=" * 60)

    results: dict[str, str] = {}

    test_env = {
        "BACKUP_DIR": POSIX_TEST_BACKUP_DIR,
        "REMOTE_BACKUP": "false",
    }

    # 准备测试目录
    _run_bash(f'rm -rf "{POSIX_TEST_BACKUP_DIR}"')
    _run_bash(f'mkdir -p "{POSIX_TEST_BACKUP_DIR}"')

    # === 验收 1: --db-only 含 WAL hint ===
    try:
        rc, _ = run_backup(["--db-only"], env_extra=test_env)
        rc, ls_out = _run_bash(f'ls -1 "{POSIX_TEST_BACKUP_DIR}"')
        sub_dirs = [x.strip() for x in ls_out.splitlines() if x.strip()]
        if not sub_dirs:
            log("未生成备份目录", "FAIL")
            results["B16-WAL Hint"] = "FAIL"
        else:
            latest_name = sorted(sub_dirs)[-1]
            latest_posix = f"{POSIX_TEST_BACKUP_DIR}/{latest_name}"
            _, meta_text = _run_bash(f'cat "{latest_posix}/backup_metadata.json"')
            meta = json.loads(meta_text) if meta_text.strip() else {}
            has_lsn = "pg_lsn_at_backup" in meta
            log(
                f"WAL hint: pg_lsn_at_backup={meta.get('pg_lsn_at_backup')}, "
                f"backup_type={meta.get('backup_type')}",
                "PASS" if has_lsn else "FAIL",
            )
            results["B16-WAL Hint"] = "PASS" if has_lsn else "FAIL"
    except Exception as e:
        log(f"WAL hint 验证异常: {e}", "FAIL")
        results["B16-WAL Hint"] = "FAIL"

    # === 验收 2: SHA-256 校验 ===
    try:
        _, ls_out = _run_bash(f'ls -1 "{POSIX_TEST_BACKUP_DIR}"')
        sub_dirs = [x.strip() for x in ls_out.splitlines() if x.strip()]
        if not sub_dirs:
            log("无备份可校验", "FAIL")
            results["B16-SHA256"] = "FAIL"
        else:
            latest_name = sorted(sub_dirs)[-1]
            latest_posix = f"{POSIX_TEST_BACKUP_DIR}/{latest_name}"
            # 注入 test_data.bin + checksums.sha256
            test_file_posix = f"{latest_posix}/test_data.bin"
            _run_bash(f'printf "hello world" > "{test_file_posix}"', check=True)
            import hashlib

            sha = hashlib.sha256(b"hello world").hexdigest()
            sha_posix = f"{latest_posix}/checksums.sha256"
            _run_bash(f'echo "{sha}  test_data.bin" > "{sha_posix}"', check=True)
            # 跑 --verify
            rc, _ = run_backup(["--verify", latest_posix], env_extra=test_env)
            log(f"--verify 返回码: {rc}", "PASS" if rc == 0 else "FAIL")
            results["B16-SHA256"] = "PASS" if rc == 0 else "FAIL"
    except Exception as e:
        log(f"SHA-256 校验异常: {e}", "FAIL")
        results["B16-SHA256"] = "FAIL"

    # === 验收 3: --status 输出合法 JSON ===
    try:
        rc, out = run_backup(["--status"], env_extra=test_env)
        json_lines = []
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("{") or line.startswith("}") or (":" in line and not line.startswith("[")):
                json_lines.append(line)
        json_text = "\n".join(json_lines)
        try:
            status = json.loads(json_text)
            healthy = status.get("healthy")
            total = status.get("total_backups")
            log(
                f"--status: healthy={healthy}, total_backups={total}",
                "PASS" if "healthy" in status else "FAIL",
            )
            results["B16-Status JSON"] = "PASS" if "healthy" in status else "FAIL"
        except json.JSONDecodeError as e:
            log(f"--status 输出非合法 JSON: {e}\n原文: {json_text[:200]}", "FAIL")
            results["B16-Status JSON"] = "FAIL"
    except Exception as e:
        log(f"--status 异常: {e}", "FAIL")
        results["B16-Status JSON"] = "FAIL"

    # === 验收 4: 元数据 schema 完整 ===
    try:
        _, ls_out = _run_bash(f'ls -1 "{POSIX_TEST_BACKUP_DIR}"')
        sub_dirs = [x.strip() for x in ls_out.splitlines() if x.strip()]
        if not sub_dirs:
            results["B16-Metadata Schema"] = "FAIL"
        else:
            latest_name = sorted(sub_dirs)[-1]
            latest_posix = f"{POSIX_TEST_BACKUP_DIR}/{latest_name}"
            _, meta_text = _run_bash(f'cat "{latest_posix}/backup_metadata.json"')
            meta = json.loads(meta_text) if meta_text.strip() else {}
            required = {
                "timestamp", "tenant_db", "pg_lsn_at_backup",
                "backup_type", "pg_dump_format", "db_backup_succeeded",
            }
            missing = required - set(meta.keys())
            log(f"元数据 schema: missing={missing}", "PASS" if not missing else "FAIL")
            results["B16-Metadata Schema"] = "PASS" if not missing else "FAIL"
    except Exception as e:
        log(f"元数据 schema 验证异常: {e}", "FAIL")
        results["B16-Metadata Schema"] = "FAIL"

    # === 验收 5: --help 用法展示新参数 ===
    try:
        rc, out = run_backup(["--help"], env_extra=test_env)
        has_status = "--status" in out
        has_verify = "--verify" in out
        log(
            f"help 输出含 --status: {has_status}, --verify: {has_verify}",
            "PASS" if has_status and has_verify else "FAIL",
        )
        results["B16-Help"] = "PASS" if has_status and has_verify else "FAIL"
    except Exception as e:
        log(f"help 验证异常: {e}", "FAIL")
        results["B16-Help"] = "FAIL"

    # 清理
    _run_bash(f'rm -rf "{POSIX_TEST_BACKUP_DIR}"')

    # 汇总
    print("\n" + "=" * 60)
    print("📊 Phase 3 B16 备份升级验收")
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