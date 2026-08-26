-- PostgreSQL 初始化脚本 — Docker 容器首次启动时自动执行
-- @see docs/design/09-database-design.md 第 9.5 节
--
-- 注意：本脚本在 postgres 容器首次启动时执行（挂载到 /docker-entrypoint-initdb.d/）
-- 如果数据卷已存在则不会重新执行，请用 `alembic upgrade head` 替代。

-- 启用扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";      -- UUID 生成
CREATE EXTENSION IF NOT EXISTS "pgcrypto";        -- 加密
CREATE EXTENSION IF NOT EXISTS "pg_trgm";         -- trigram 模糊搜索

-- 设置默认权限（dev/staging 用；prod 由 K8s Secret 管理）
-- ALTER USER hscredit WITH PASSWORD 'hscredit';