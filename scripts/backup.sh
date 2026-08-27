#!/usr/bin/env bash
# HSCredit Studio 备份脚本 (Phase 2 批次 13)
#
# 备份目标:
#   1. PostgreSQL 数据库 (pg_dump, 压缩)
#   2. 本地文件存储 (_storage/) - 节点产物
#   3. Redis db 1 (cache) + db 2 (Celery 结果) - 可选
#
# 用法:
#   ./backup.sh                     # 全量备份
#   ./backup.sh --db-only           # 仅数据库
#   ./backup.sh --files-only        # 仅文件
#   ./backup.sh --restore <dir>     # 从指定目录恢复
#
# 环境变量:
#   POSTGRES_HOST   (默认 localhost)
#   POSTGRES_PORT   (默认 5432)
#   POSTGRES_DB     (默认 hscredit)
#   POSTGRES_USER   (默认 postgres)
#   PGPASSWORD       (从 .env 读取)
#   STORAGE_DIR    (默认 ./backend/_storage)
#   BACKUP_DIR     (默认 ./backups)
#   RETENTION_DAYS (默认 7)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-postgres}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
STORAGE_DIR="${STORAGE_DIR:-$ROOT_DIR/backend/_storage}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

# 从 .env 读取 DB URL
if [ -f "$ROOT_DIR/backend/.env" ]; then
  DB_URL=$(grep -E '^DATABASE_URL=' "$ROOT_DIR/backend/.env" | cut -d= -f2- | tr -d '"' || true)
  if [ -n "$DB_URL" ]; then
    POSTGRES_USER=$(echo "$DB_URL" | sed -n 's|.*postgresql.*://\([^:]*\):.*|\1|p' | head -1)
    PGPASSWORD=$(echo "$DB_URL" | sed -n 's|.*postgresql.*://[^:]*:\([^@]*\)@.*|\1|p' | head -1)
    POSTGRES_DB=$(echo "$DB_URL" | sed -n 's|.*postgresql.*://[^@]*@\([^:/]*\).*|\1|p' | head -1)
    POSTGRES_PORT=$(echo "$DB_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p' | head -1)
    POSTGRES_HOST=$(echo "$DB_URL" | sed -n 's|.*@\([^:/]*\).*|\1|p' | head -1)
  fi
fi

mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="$BACKUP_DIR/$TIMESTAMP"
mkdir -p "$BACKUP_PATH"

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }

# ===== 数据库备份 =====
backup_db() {
  log "备份 PostgreSQL 数据库 $POSTGRES_DB ..."
  PGPASSWORD="$PGPASSWORD" pg_dump \
    -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
    -Fc -n "$POSTGRES_DB" \
    -f "$BACKUP_PATH/db_${POSTGRES_DB}.dump" 2>/dev/null \
  || {
    # 失败时尝试 plain text 格式
    warn "pg_dump 二进制格式失败,改用 plain 格式"
    PGPASSWORD="$PGPASSWORD" pg_dump \
      -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
      -Fp -n "$POSTGRES_DB" \
      -f "$BACKUP_PATH/db_${POSTGRES_DB}.sql" 2>/dev/null
  }
  ls -lh "$BACKUP_PATH/" | tail -1
  log "✓ 数据库备份完成: $BACKUP_PATH/db_${POSTGRES_DB}.dump"
}

# ===== 文件备份 =====
backup_files() {
  if [ -d "$STORAGE_DIR" ]; then
    log "备份节点产物目录 $STORAGE_DIR ..."
    tar -czf "$BACKUP_PATH/storage.tar.gz" -C "$(dirname "$STORAGE_DIR")" "$(basename "$STORAGE_DIR")"
    ls -lh "$BACKUP_PATH/storage.tar.gz"
    log "✓ 文件存储备份完成"
  else
    warn "$STORAGE_DIR 不存在, 跳过文件备份"
  fi
}

# ===== Redis 备份 =====
backup_redis() {
  log "备份 Redis db 1 + db 2 ..."
  for db in 1 2; do
    redis-cli -n $db --rdb "$BACKUP_PATH/redis_db${db}.rdb" 2>/dev/null || warn "Redis db $db 备份失败"
  done
  ls -lh "$BACKUP_PATH/redis_"*.rdb 2>/dev/null || warn "无 Redis 备份文件"
}

# ===== 恢复 =====
restore() {
  local src="$1"
  if [ ! -d "$src" ]; then
    warn "备份目录不存在: $src"
    exit 1
  fi

  log "恢复数据库 ..."
  PGPASSWORD="$PGPASSWORD" pg_restore \
    -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" -c \
    "$src/db_${POSTGRES_DB}.dump" 2>/dev/null \
  || warn "数据库恢复失败"

  if [ -f "$src/storage.tar.gz" ]; then
    log "恢复文件存储 ..."
    tar -xzf "$src/storage.tar.gz" -C "$(dirname "$STORAGE_DIR")"
  fi

  log "✓ 恢复完成"
}

# ===== 清理旧备份 =====
cleanup_old() {
  log "清理 $RETENTION_DAYS 天前的旧备份 ..."
  find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +"$RETENTION_DAYS" -exec rm -rf {} + || true
  log "✓ 当前备份数: $(find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l)"
}

# ===== Main =====
MODE_ARG="${1:-all}"

case "$MODE_ARG" in
  --db-only)
    backup_db
    cleanup_old
    ;;
  --files-only)
    backup_files
    cleanup_old
    ;;
  --redis-only)
    backup_redis
    cleanup_old
    ;;
  --restore)
    if [ -z "${2:-}" ]; then
      echo "用法: $0 --restore <备份目录>"
      exit 1
    fi
    restore "$2"
    ;;
  all|"")
    backup_db
    backup_files
    backup_redis
    cleanup_old
    ;;
  *)
    echo "用法: $0 [all|--db-only|--files-only|--redis-only|--restore <dir>]"
    exit 1
    ;;
esac

log "✓ 备份完成: $BACKUP_PATH"