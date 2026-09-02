#!/usr/bin/env bash
# kill-by-port.sh — 按端口关闭监听进程, 跨平台 (Windows Git Bash / Linux / macOS).
#
# 用法: kill-by-port.sh <port> "<label>"
# 例:   kill-by-port.sh 8003 "backend-dev"
#
# 退出码:
#   0 - 成功 (找到并停止, 或端口空闲)
#   1 - 用法错误

set -u

PORT="${1:-}"
LABEL="${2:-target process}"

if [[ -z "$PORT" ]]; then
  echo "Usage: $0 <port> <label>" >&2
  exit 1
fi

kill_on_windows() {
  # Git Bash on Windows: 用 PowerShell 查找 LISTEN 状态的 owning process.
  local pids
  pids=$(powershell -NoProfile -Command \
    "Get-NetTCPConnection -LocalPort $PORT -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess" \
    2>/dev/null | tr -d '[:space:]')
  if [[ -z "$pids" ]]; then
    echo "[$LABEL] 端口 $PORT 未在监听, 无需关闭"
    return 0
  fi
  for pid in $pids; do
    if powershell -NoProfile -Command "Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue" >/dev/null 2>&1; then
      echo "[$LABEL] 已关闭 PID $pid (端口 $PORT)"
    else
      echo "[$LABEL] 无法关闭 PID $pid (可能已退出)" >&2
    fi
  done
}

kill_on_unix() {
  local pids
  # 优先 lsof, 回退到 fuser
  if command -v lsof >/dev/null 2>&1; then
    pids=$(lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null)
  elif command -v fuser >/dev/null 2>&1; then
    pids=$(fuser "$PORT/tcp" 2>/dev/null | tr -d '[:space:]')
  else
    echo "Error: 需要 lsof 或 fuser 才能在 Unix 上按端口杀进程" >&2
    exit 1
  fi
  if [[ -z "$pids" ]]; then
    echo "[$LABEL] 端口 $PORT 未在监听, 无需关闭"
    return 0
  fi
  for pid in $pids; do
    if kill -9 "$pid" 2>/dev/null; then
      echo "[$LABEL] 已关闭 PID $pid (端口 $PORT)"
    else
      echo "[$LABEL] 无法关闭 PID $pid (可能已退出)" >&2
    fi
  done
}

# 平台判断: $OSTYPE 在 Git Bash (mingw) 下为 msys, PowerShell 可用 → Windows
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || -n "${WINDIR:-}" ]]; then
  kill_on_windows
else
  kill_on_unix
fi