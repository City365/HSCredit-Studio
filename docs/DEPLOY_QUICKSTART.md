# 部署快速上手 (Quickstart)

> 目标读者: **新加入的工程师 / 第一次接触本仓库的开发者**.
>
> 读完本文, 能在 **10 分钟内** 把整套系统 (PG + Redis + MinIO + Backend + Frontend) 跑起来, 并跑通 28 项 Phase 6 B36 节点可插拔 E2E 验收.

---

## 0. 系统要求

| 组件 | 最低 | 推荐 | 备注 |
|---|---|---|---|
| Python | 3.11 | 3.12 | 项目用 `pyproject.toml` requires-python>=3.11 |
| Node.js | 20 LTS | 22 LTS | Vite 5 要求 |
| PostgreSQL | 15 | 16 | 主库 + Alembic 迁移 |
| Redis | 7 | 7 | Celery broker + 多 worker pub/sub |
| MinIO | RELEASE.2024-01 | 同左 | S3 兼容 (artifact/report 存储) |
| Docker | 24+ | 26+ | 仅开发环境依赖服务用 |
| 内存 | 8 GB | 16 GB | 沙箱/模型训练吃内存 |
| OS | Win 11 / macOS 14 / Ubuntu 22 | 同左 | Windows 上 bash 用 Git Bash |

> 不需要 GPU. 模型训练阶段才需要, 默认 CPU 即可.

---

## 1. 第一次部署 (开发环境)

### 1.1 克隆 + 启动开发依赖

```bash
git clone https://github.com/City365/HSCredit-Studio.git
cd HSCredit-Studio

# 启动 PostgreSQL + Redis + MinIO (Docker Compose)
make dev-up
```

启动后:

| 服务 | 端口 | 默认凭证 |
|---|---|---|
| PostgreSQL | 5432 | hscredit / hscredit |
| Redis | 6379 | 无 |
| MinIO Console | 9001 | minio / minio123 |

### 1.2 后端: 安装 + 迁移 + 种子

```bash
# Python 虚拟环境 (推荐用 uv, 或 venv)
cd backend
python -m venv .venv
source .venv/bin/activate     # Git Bash: source .venv/Scripts/activate
pip install -e ".[dev,test]"

# 复制 .env 模板
cp ../.env.example .env       # 项目根 .env.example 是参考, 后端也读它

# 数据库迁移 (Alembic head)
alembic upgrade head

# 种子数据 (1 租户 + 2 用户 + 76 系统节点 + 3 模板)
python -m hscredit_studio.scripts.seed
```

种子完成后, 会有:
- 租户: `demo`
- 用户: `admin@demo.com` / `DemoPass123!` (super_admin), `viewer@demo.com` (viewer)
- 76 个系统节点 + 3 个系统模板

### 1.3 启动后端开发服务器

```bash
# 在 backend/ 目录下
uvicorn hscredit_studio.main:app --reload --host 0.0.0.0 --port 8003
```

健康检查:

```bash
curl http://localhost:8003/api/v1/healthz
# → {"status":"ok"}
```

### 1.4 前端: 安装 + 启动

新开一个终端:

```bash
cd frontend
npm install
npm run dev
```

访问: **http://localhost:5173**

登录: `admin@demo.com` / `DemoPass123!`, 租户选 `demo`.

### 1.5 跑 E2E 验收 (推荐)

```bash
cd scripts/e2e
python run_e2e_phase6_b36.py
```

期望输出: **28 通过 / 0 失败 / 28 项**.

如果用了非默认种子密码, 通过环境变量覆盖:

```bash
E2E_ADMIN_PASSWORD=admin123 python run_e2e_phase6_b36.py
```

---

## 2. 故障排查速查表

### 2.1 后端启动失败

| 症状 | 原因 | 解法 |
|---|---|---|
| `pydantic.ValidationError: secret_key` | `.env` 没 SECRET_KEY | 从 `.env.example` 复制完整 `.env` |
| `asyncpg.exceptions.InvalidPasswordError` | PG 密码错 | 改 `.env` 的 `DATABASE_URL`, 或重置 PG: `make dev-reset && make dev-up` |
| `Connection refused: 6379` | Redis 没起 | `docker compose -f deploy/docker-compose.dev.yml up -d redis` |
| `ImportError: hscredit` | 主库未 pip install | `pip install -e ../hscredit` (同级 sibling 包) |
| Windows 上 `DLL load failed` | Python 3.8 < 3.11 | 装 Python 3.11+ 64-bit |

### 2.2 数据库迁移失败

```bash
# 看当前 head 版本
alembic current

# 看所有版本
alembic history --verbose

# 强制重置 (开发环境, 会丢数据!)
alembic downgrade base
alembic upgrade head

# 看具体 migration 的 SQL (不执行)
alembic upgrade head --sql
```

如果多个 migration 冲突 (多个 head):

```bash
alembic heads                  # 看冲突的 head
alembic merge -m "merge heads" <rev1> <rev2>
alembic upgrade head
```

### 2.3 前端启动失败

| 症状 | 原因 | 解法 |
|---|---|---|
| `Cannot find module '@/...'` | tsconfig path 解析失败 | 检查 `frontend/tsconfig.json` 的 `compilerOptions.paths` |
| `Monaco loader timeout` | 网络拉不到 CDN | 改 `frontend/vite.config.ts` 的 monaco local 模式, 或配置代理 |
| `Port 5173 in use` | 端口冲突 | `npm run dev -- --port 3001` |
| `CORS error on login` | 后端 CORS 白名单不含前端端口 | 在 `.env` 加 `CORS_ALLOWED_ORIGINS=http://localhost:5173` |

### 2.4 节点可插拔专项

**症状: 自定义节点试运行报 `__import__ not found`**

原因: Phase 6 B36 阶段 0 的沙箱 worker 误把 `__import__` builtin 删除了. 已修复 (commit `08cbe10`).

**症状: 试运行报 `name 'NodeContract' is not defined`**

原因: RestrictedPython 编译后, `from x import Y` 用 `STORE_NAME` 写入 globals, 但如果 worker 用 `exec(code, globals, locals)` 三参数版, STORE_NAME 会写 locals — class body 的 LOAD_NAME 找不到. 已修复 (commit `08cbe10`, 不传 locals).

**症状: 系统节点 /sync 端点报 unique constraint 冲突**

原因: 之前 sync 失败留下的半成品行 + 第二次 sync 时 INSERT 冲突. 已修复 (commit `08cbe10`, 用 `INSERT ... ON CONFLICT DO UPDATE`).

**症状: 多 worker 节点定义不一致**

NodeRegistry 是 **进程内** 的, 多 Uvicorn worker 不会自动同步. 系统通过 Redis pub/sub `node:reload` channel 广播 reload. 检查:

```bash
# 1. Redis pub/sub 工作
redis-cli SUBSCRIBE node:reload
# 另开终端触发 sync
curl -X POST http://localhost:8003/api/v1/demo/node-definitions/sync -H "Authorization: Bearer $TOKEN"
# 应在 SUBSCRIBE 终端看到消息
```

---

## 3. 部署到生产 (Kubernetes)

### 3.1 镜像构建

```bash
# 后端
docker build -t ghcr.io/city365/hscredit-studio-backend:$SHA -f backend/Dockerfile .
docker push ghcr.io/city365/hscredit-studio-backend:$SHA

# Worker (独立镜像, 跑 Celery)
docker build -t ghcr.io/city365/hscredit-studio-worker:$SHA -f backend/Dockerfile.worker .
docker push ghcr.io/city365/hscredit-studio-worker:$SHA

# 前端
docker build -t ghcr.io/city365/hscredit-studio-frontend:$SHA -f frontend/Dockerfile .
docker push ghcr.io/city365/hscredit-studio-frontend:$SHA
```

### 3.2 Helm 安装

```bash
# 创建 namespace
kubectl create namespace hscredit-prod

# 准备 secrets (生产值, 不要提交)
kubectl create secret generic hscredit-prod-secrets \
  --from-literal=SECRET_KEY=$(openssl rand -hex 32) \
  --from-literal=JWT_SECRET_KEY=$(openssl rand -hex 32) \
  --from-literal=DATABASE_URL='postgresql+asyncpg://...' \
  --from-literal=REDIS_URL='redis://...' \
  --from-literal=S3_ACCESS_KEY='...' \
  --from-literal=S3_SECRET_KEY='...' \
  -n hscredit-prod

# 安装
helm upgrade --install hscredit-prod charts/hscredit-studio \
  -f charts/hscredit-studio/values-production.yaml \
  -n hscredit-prod --create-namespace \
  --wait --timeout 10m
```

### 3.3 部署后验证

```bash
# Pod 全 Ready?
kubectl get pods -n hscredit-prod

# 健康检查 (从集群内)
kubectl exec -n hscredit-prod deploy/hscredit-prod-api -- \
  curl -sf http://localhost:8000/api/v1/healthz

# 跑 E2E (端口通过 port-forward 暴露)
kubectl port-forward -n hscredit-prod svc/hscredit-prod-api 8003:8000 &
E2E_BASE_URL=http://localhost:8003 python scripts/e2e/run_e2e_phase6_b36.py
```

### 3.4 蓝绿部署

详见 `docs/DEPLOYMENT.md` 第 3 节.

### 3.5 回滚

```bash
# 看历史
helm history hscredit-prod -n hscredit-prod

# 回滚到上一个
helm rollback hscredit-prod -n hscredit-prod

# 数据库迁移回滚 (谨慎!)
# Alembic 不支持自动 downgrade — 手动:
cd backend && alembic downgrade -1
```

---

## 4. 监控接入

### 4.1 Prometheus 指标

后端在 `:8000/metrics` 暴露 Prometheus 指标. 关键指标见 `docs/node-plugin/05_OPERATIONS.md` 第 2 节.

### 4.2 健康检查端点

| 端点 | 用途 | 频率建议 |
|---|---|---|
| `/api/v1/healthz` | 进程存活 + DB ping | 10s |
| `/api/v1/readyz` | 完整依赖就绪 | 30s |
| `/metrics` | Prometheus scrape | 15s |

### 4.3 日志

后端用 `structlog` 输出 JSON. 通过 stdout/stderr → Loki / ELK / Datadog 采集.

关键日志字段: `tenant_id`, `user_id`, `run_id`, `node_type`, `duration_ms`. 详见 `docs/node-plugin/05_OPERATIONS.md` 第 3 节.

---

## 5. 备份与恢复

### 5.1 自动备份

`scripts/backup.sh` 每日凌晨 2 点跑 (cron: `0 2 * * * /opt/hscredit/scripts/backup.sh`).

输出到 `/tmp/backups/hscredit_YYYYMMDD_HHMMSS.dump`, 同步到 S3.

### 5.2 手动备份

```bash
./scripts/backup.sh
# 输出: /tmp/backups/hscredit_20260914_020000.dump
```

### 5.3 恢复演练 (季度)

详见 `docs/DEPLOYMENT.md` 第 6 节.

---

## 6. 环境变量完整列表

后端从 `.env` 或环境变量读, 优先级: 进程 env > `.env`.

### 6.1 必填 (生产)

| 变量 | 说明 | 示例 |
|---|---|---|
| `SECRET_KEY` | 后端签名密钥 (≥32 字符) | `openssl rand -hex 32` |
| `JWT_SECRET_KEY` | JWT 签名密钥 (≥32 字符) | `openssl rand -hex 32` |
| `DATABASE_URL` | PG 异步 URL | `postgresql+asyncpg://user:pass@host:5432/db` |
| `REDIS_URL` | Redis broker | `redis://host:6379/0` |
| `REDIS_CELERY_URL` | Celery 专用 (可同 REDIS_URL 不同 db) | `redis://host:6379/1` |
| `S3_ENDPOINT` | S3 endpoint | `https://s3.amazonaws.com` |
| `S3_ACCESS_KEY` | S3 access key | |
| `S3_SECRET_KEY` | S3 secret key | |
| `S3_BUCKET_PREFIX` | Bucket 名前缀 | `hscredit-prod` |

### 6.2 推荐设置

| 变量 | 默认 | 说明 |
|---|---|---|
| `ENVIRONMENT` | `development` | 改 `production` 后启用严格检查 |
| `DEBUG` | `false` | 生产必须 false |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | 逗号分隔 |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | |

### 6.3 沙箱配置 (节点可插拔 Phase 3)

| 变量 | 默认 | 说明 |
|---|---|---|
| `USER_SANDBOX_TIMEOUT_SEC` | `60` | 单次试运行 wall-clock 超时 |
| `USER_SANDBOX_MEMORY_MB` | `2048` | 子进程 AS (address space) 限制 |
| `USER_SANDBOX_CPU_SEC` | `60` | CPU 时间限制 |
| `USER_SANDBOX_CPU_COUNT` | `1` | 限制可用核数 |
| `USER_SANDBOX_OPEN_FILE_LIMIT` | `64` | 同时打开文件数 |
| `USER_SANDBOX_MAX_PID` | `32` | 最大子进程数 |
| `USER_SANDBOX_DIR_TEMP` | `/tmp/hscredit-sandbox` | 临时文件目录 |
| `USER_SANDBOX_KEEP_TEMP` | `false` | 调试时设 `true` 保留现场 |

### 6.4 可观测性 (可选)

| 变量 | 说明 |
|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OpenTelemetry Collector 地址 |
| `OTEL_SERVICE_NAME` | 服务名 (默认 `hscredit-studio`) |

### 6.5 前端 (Vite)

前端变量以 `VITE_` 开头, 构建时注入:

| 变量 | 说明 |
|---|---|
| `VITE_API_BASE_URL` | 后端 API 完整 URL, 含 `/api/v1` |
| `VITE_WS_BASE_URL` | WebSocket URL |
| `VITE_DEFAULT_LOCALE` | `zh-CN` / `en-US` |

---

## 7. 完整文档索引

| 场景 | 文档 |
|---|---|
| 本文档 (快速上手) | `docs/DEPLOY_QUICKSTART.md` ← 你在这 |
| 生产部署 / 灾备 / 监控 | `docs/DEPLOYMENT.md` |
| 节点可插拔运维 | `docs/node-plugin/05_OPERATIONS.md` |
| 节点可插拔设计 | `docs/node-plugin/01_DESIGN.md` |
| 节点可插拔实施 | `docs/node-plugin/02_IMPLEMENTATION.md` |
| 节点可插拔测试 | `docs/node-plugin/03_TESTING.md` |
| 节点可插拔验收 | `docs/node-plugin/04_VERIFICATION.md` |
| 系统架构 | `docs/ARCHITECTURE.md` |
| 开发规范 | `docs/DEVELOPMENT.md` |
| 前端规划 | `docs/FRONTEND_PLAN.md` |
| 路线图 | `docs/ROADMAP.md` |

---

## 8. 紧急联系人

| 角色 | 联系方式 | 处理范围 |
|---|---|---|
| 后端 oncall | (Slack #oncall-backend) | API 500 / 性能 / DB |
| 前端 oncall | (Slack #oncall-frontend) | UI 报错 / 性能 |
| DBA | (PagerDuty) | DB 故障 / 数据恢复 |
| 安全 | (Slack #security) | 漏洞 / 入侵 / 审计 |
