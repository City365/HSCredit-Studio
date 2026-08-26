#!/usr/bin/env bash
# 数据库备份脚本 — 每日凌晨 2 点由 crontab 调用
# 用法: ./scripts/backup.sh

set -euo pipefail

BACKUP_DIR=${BACKUP_DIR:-/tmp/backups}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DB_HOST=${DB_HOST:-localhost}
DB_PORT=${DB_PORT:-5432}
DB_NAME=${DB_NAME:-hscredit}
DB_USER=${DB_USER:-hscredit}
PGPASSWORD=${DB_PASSWORD:-hscredit}

BACKUP_FILE="${BACKUP_DIR}/hscredit_${TIMESTAMP}.sql.gz"
mkdir -p "${BACKUP_DIR}"

echo "📦 备份数据库 ${DB_NAME} -> ${BACKUP_FILE}"
PGPASSWORD="${PGPASSWORD}" pg_dump \
    -h "${DB_HOST}" \
    -p "${DB_PORT}" \
    -U "${DB_USER}" \
    -d "${DB_NAME}" \
    --format=custom \
    --no-owner \
    --no-acl \
    | gzip > "${BACKUP_FILE}"

echo "✅ 备份完成: ${BACKUP_FILE}"
ls -lh "${BACKUP_FILE}"

# 保留最近 30 天备份
echo "🧹 清理 30 天前的旧备份..."
find "${BACKUP_DIR}" -name "hscredit_*.sql.gz" -mtime +30 -delete

echo "🎉 完成"