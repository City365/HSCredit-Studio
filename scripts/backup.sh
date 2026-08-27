#!/usr/bin/env bash
# HSCredit Studio 备份脚本 (Phase 3 批次 16 升级版)
#
# 升级点 (相对 Phase 2 批次 13):
#   - WAL hint 文件: 记录 dump 时刻的 PG LSN, 配合归档 WAL 可做 PITR
#   - 跨区 S3 复制: 本地备份后异步上传到 S3 (含端点/bucket/region 配置)
#   - 完整性校验: SHA-256 checksum 写入 .sha256 文件
#   - 保留策略: 日/周/月三级保留 (默认 7/30/365 天)
#   - 健康检查: --status 输出 JSON 摘要 (供监控接入)
#
# 用法:
#   ./backup.sh                       # 全量备份 (db + files + 远端复制)
#   ./backup.sh --db-only             # 仅数据库
#   ./backup.sh --files-only          # 仅文件
#   ./backup.sh --no-remote           # 本地备份但跳过 S3 上传
#   ./backup.sh --status              # 输出备份健康状态 (JSON)
#   ./backup.sh --restore <dir>       # 从指定目录恢复
#   ./backup.sh --verify <dir>        # 校验指定备份目录完整性 (SHA-256)
#
# 环境变量 (新增 B16):
#   S3_BUCKET          跨区备份桶名 (例: hscredit-backups-east-1)
#   S3_ENDPOINT        S3 端点 (例: http://rustfs:9000)
#   S3_ACCESS_KEY      S3 凭证
#   S3_SECRET_KEY      S3 密钥
#   S3_REGION          S3 区域 (默认 us-east-1)
#   REMOTE_BACKUP      true/false (默认 false)
#   RETENTION_DAYS     日备份保留天数 (默认 7)
#   RETENTION_WEEKS    周备份保留周数 (默认 4)
#   RETENTION_MONTHS   月备份保留月数 (默认 12)

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
RETENTION_WEEKS="${RETENTION_WEEKS:-4}"
RETENTION_MONTHS="${RETENTION_MONTHS:-12}"

# B16 新增
REMOTE_BACKUP="${REMOTE_BACKUP:-false}"
S3_BUCKET="${S3_BUCKET:-hscredit-backups}"
S3_ENDPOINT="${S3_ENDPOINT:-}"
S3_ACCESS_KEY="${S3_ACCESS_KEY:-}"
S3_SECRET_KEY="${S3_SECRET_KEY:-}"
S3_REGION="${S3_REGION:-us-east-1}"

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

# 兜底 (set -u 兼容)
PGPASSWORD="${PGPASSWORD:-}"

mkdir -p "$BACKUP_DIR"

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# 当前是否为本月/本周/本日 (用于分级保留)
NOW_TS=$(date +%s)
IS_MONTHLY=$(date +%d | grep -E '^(01)$' >/dev/null && echo true || echo false)
IS_WEEKLY=$(date +%u | grep -E '^7$' >/dev/null && echo true || echo false)

# ===== 数据库备份 (含 WAL hint) =====
backup_db() {
  local ts="$1"
  local backup_path="$BACKUP_DIR/$ts"
  mkdir -p "$backup_path"

  local db_backup_ok=false
  log "备份 PostgreSQL 数据库 $POSTGRES_DB ..."

  # 1. 逻辑备份 (pg_dump 自定义格式, 压缩比高)
  # 用 if/else 而非 || chain, 让 pg_dump 缺失时不触发 set -e
  if command -v pg_dump >/dev/null 2>&1; then
    if PGPASSWORD="$PGPASSWORD" pg_dump \
        -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
        -Fc -n "$POSTGRES_DB" \
        -f "$backup_path/db_${POSTGRES_DB}.dump" 2>/dev/null; then
      log "✓ pg_dump 完成 (自定义格式)"
      db_backup_ok=true
    else
      # fallback to plain text
      if PGPASSWORD="$PGPASSWORD" pg_dump \
          -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
          -Fp -n "$POSTGRES_DB" \
          -f "$backup_path/db_${POSTGRES_DB}.sql" 2>/dev/null; then
        log "✓ pg_dump 完成 (plain 格式)"
        db_backup_ok=true
      else
        warn "pg_dump 两种格式均失败"
      fi
    fi
  else
    warn "pg_dump 不在 PATH (生产环境请安装 postgresql-client); 跳过实际数据库备份, 仅写元数据"
  fi

  # 2. WAL hint 文件 (B16 新增) — 记录当前 PG LSN, 配合归档 WAL 可做 PITR
  local current_lsn="unknown"
  if command -v psql >/dev/null 2>&1; then
    current_lsn=$(PGPASSWORD="$PGPASSWORD" psql \
      -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
      -d "$POSTGRES_DB" -tAc "SELECT pg_current_wal_lsn();" 2>/dev/null || echo "unknown")
  fi

  # 3. 备份元数据 (PITR 恢复时的关键信息)
  local backup_type="daily"
  if [ "$IS_MONTHLY" = "true" ]; then backup_type="monthly"
  elif [ "$IS_WEEKLY" = "true" ]; then backup_type="weekly"
  fi
  local dump_format="none"
  if [ -f "$backup_path/db_${POSTGRES_DB}.dump" ]; then dump_format="custom"
  elif [ -f "$backup_path/db_${POSTGRES_DB}.sql" ]; then dump_format="plain"
  fi

  cat > "$backup_path/backup_metadata.json" <<EOF
{
  "timestamp": "$ts",
  "tenant_db": "$POSTGRES_DB",
  "pg_host": "$POSTGRES_HOST",
  "pg_lsn_at_backup": "$current_lsn",
  "backup_type": "$backup_type",
  "pg_dump_format": "$dump_format",
  "db_backup_succeeded": $db_backup_ok
}
EOF

  # 4. SHA-256 校验和 (B16 新增)
  if [ -n "$(ls -A "$backup_path" 2>/dev/null | grep -v checksums.sha256)" ]; then
    (cd "$backup_path" && sha256sum *.dump *.sql backup_metadata.json 2>/dev/null > "checksums.sha256" || true)
  fi

  log "✓ 数据库备份元数据完成 (LSN=$current_lsn, dump_ok=$db_backup_ok)"
}

# ===== 文件备份 =====
backup_files() {
  local ts="$1"
  local backup_path="$BACKUP_DIR/$ts"

  if [ -d "$STORAGE_DIR" ]; then
    log "备份节点产物目录 $STORAGE_DIR ..."
    tar -czf "$backup_path/storage.tar.gz" -C "$(dirname "$STORAGE_DIR")" "$(basename "$STORAGE_DIR")"
    log "✓ 文件存储备份完成"
  else
    warn "$STORAGE_DIR 不存在, 跳过文件备份"
  fi
}

# ===== 跨区 S3 复制 (B16 新增) =====
upload_to_s3() {
  local ts="$1"
  local backup_path="$BACKUP_DIR/$ts"

  if [ "$REMOTE_BACKUP" != "true" ]; then
    log "[本地模式] 跳过 S3 上传 (REMOTE_BACKUP=$REMOTE_BACKUP)"
    return 0
  fi

  if [ -z "$S3_ENDPOINT" ] || [ -z "$S3_BUCKET" ]; then
    err "S3 配置缺失: S3_ENDPOINT=$S3_ENDPOINT, S3_BUCKET=$S3_BUCKET"
    return 1
  fi

  log "上传备份到 S3: s3://$S3_BUCKET/$ts/ ..."
  export AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY"
  export AWS_SECRET_ACCESS_KEY="$S3_SECRET_KEY"
  export AWS_DEFAULT_REGION="$S3_REGION"

  if command -v aws >/dev/null 2>&1; then
    aws s3 cp "$backup_path/" "s3://$S3_BUCKET/$ts/" --recursive --endpoint-url "$S3_ENDPOINT" 2>/dev/null
    log "✓ S3 复制完成"
  elif command -v mc >/dev/null 2>&1; then
    # MinIO 客户端兼容
    mc cp --recursive "$backup_path/" "$S3_BUCKET/$ts/" 2>/dev/null
    log "✓ MinIO 复制完成"
  else
    warn "未找到 aws/mc CLI, 跳过 S3 上传 (本地保留)"
    return 1
  fi
}

# ===== 完整性校验 (B16 新增) =====
verify_backup() {
  local src="$1"
  if [ ! -d "$src" ]; then
    err "备份目录不存在: $src"
    return 1
  fi
  if [ ! -f "$src/checksums.sha256" ]; then
    err "缺少 checksums.sha256, 无法校验"
    return 1
  fi
  log "校验 $src 完整性 ..."
  (cd "$src" && sha256sum -c checksums.sha256)
}

# ===== 健康检查 (B16 新增) =====
status_check() {
  local latest=$(find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | awk '{print $2}')
  local total=$(find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)
  local total_size=$(du -sh "$BACKUP_DIR" 2>/dev/null | awk '{print $1}')
  local latest_age_hours="null"
  if [ -n "$latest" ] && [ -d "$latest" ]; then
    local latest_mtime=$(stat -c %Y "$latest" 2>/dev/null || echo 0)
    local now=$(date +%s)
    latest_age_hours=$(( (now - latest_mtime) / 3600 ))
  fi
  cat <<EOF
{
  "backup_dir": "$BACKUP_DIR",
  "total_backups": $total,
  "total_size": "$total_size",
  "latest_backup": "${latest:-null}",
  "latest_age_hours": $latest_age_hours,
  "retention_days": $RETENTION_DAYS,
  "retention_weeks": $RETENTION_WEEKS,
  "retention_months": $RETENTION_MONTHS,
  "remote_backup_enabled": $REMOTE_BACKUP,
  "healthy": $(if [ "$latest_age_hours" != "null" ] && [ "$latest_age_hours" -lt 48 ]; then echo "true"; else echo "false"; fi)
}
EOF
}

# ===== 清理旧备份 (B16 升级: 三级保留策略) =====
cleanup_old() {
  log "清理过期备份 ..."

  # 1. 日级保留: 删除超过 RETENTION_DAYS 天的非日级备份 (weekly/monthly 不删)
  find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +"$RETENTION_DAYS" \
    -exec sh -c '
      meta="$1/backup_metadata.json"
      if [ -f "$meta" ]; then
        bt=$(grep -oE "\"backup_type\": *\"[a-z]+\"" "$meta" | grep -oE "[a-z]+\"$" | tr -d "\"")
        if [ "$bt" = "daily" ]; then
          rm -rf "$1"
          echo "  删除日级备份: $1"
        fi
      fi
    ' _ {} \; || true

  # 2. 周级保留: 超过 RETENTION_WEEKS*7 天的 weekly 备份删除
  local weekly_days=$((RETENTION_WEEKS * 7))
  find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +"$weekly_days" \
    -exec sh -c '
      meta="$1/backup_metadata.json"
      if [ -f "$meta" ] && grep -q "\"backup_type\": \"weekly\"" "$meta"; then
        rm -rf "$1"
        echo "  删除周级备份: $1"
      fi
    ' _ {} \; || true

  # 3. 月级保留: 超过 RETENTION_MONTHS*30 天的 monthly 备份删除
  local monthly_days=$((RETENTION_MONTHS * 30))
  find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +"$monthly_days" \
    -exec sh -c '
      meta="$1/backup_metadata.json"
      if [ -f "$meta" ] && grep -q "\"backup_type\": \"monthly\"" "$meta"; then
        rm -rf "$1"
        echo "  删除月级备份: $1"
      fi
    ' _ {} \; || true

  log "✓ 当前备份数: $(find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l)"
}

# ===== 恢复 =====
restore() {
  local src="$1"
  if [ ! -d "$src" ]; then
    err "备份目录不存在: $src"
    exit 1
  fi

  # 先校验完整性 (B16 新增)
  if [ -f "$src/checksums.sha256" ]; then
    log "校验备份完整性 ..."
    (cd "$src" && sha256sum -c checksums.sha256) || {
      err "完整性校验失败, 中止恢复"
      exit 1
    }
  fi

  log "恢复数据库 ..."
  if [ -f "$src/db_${POSTGRES_DB}.dump" ]; then
    PGPASSWORD="$PGPASSWORD" pg_restore \
      -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
      -d "$POSTGRES_DB" -c \
      "$src/db_${POSTGRES_DB}.dump" 2>/dev/null \
    || warn "数据库恢复失败"
  fi

  if [ -f "$src/storage.tar.gz" ]; then
    log "恢复文件存储 ..."
    tar -xzf "$src/storage.tar.gz" -C "$(dirname "$STORAGE_DIR")"
  fi

  # 显示 WAL hint (B16 新增)
  if [ -f "$src/backup_metadata.json" ]; then
    log "备份 LSN: $(grep -oE 'pg_lsn_at_backup.*' "$src/backup_metadata.json")"
    log "如需 PITR, 请配合归档 WAL 从 LSN 处 replay"
  fi

  log "✓ 恢复完成"
}

# ===== Main =====
MODE_ARG="${1:-all}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

case "$MODE_ARG" in
  --db-only)
    backup_db "$TIMESTAMP"
    cleanup_old
    ;;
  --files-only)
    backup_files "$TIMESTAMP"
    cleanup_old
    ;;
  --no-remote)
    backup_db "$TIMESTAMP"
    backup_files "$TIMESTAMP"
    cleanup_old
    ;;
  --status)
    status_check
    ;;
  --verify)
    if [ -z "${2:-}" ]; then
      err "用法: $0 --verify <备份目录>"
      exit 1
    fi
    verify_backup "$2"
    ;;
  --restore)
    if [ -z "${2:-}" ]; then
      echo "用法: $0 --restore <备份目录>"
      exit 1
    fi
    restore "$2"
    ;;
  all|"")
    backup_db "$TIMESTAMP"
    backup_files "$TIMESTAMP"
    upload_to_s3 "$TIMESTAMP"
    cleanup_old
    ;;
  *)
    echo "用法: $0 [all|--db-only|--files-only|--no-remote|--status|--verify <dir>|--restore <dir>]"
    exit 1
    ;;
esac

log "✓ 备份流程完成"