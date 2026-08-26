# HSCredit Workflow Platform Makefile
# 常用命令统一入口

.PHONY: help dev-up dev-down backend-dev frontend-dev test lint format migrate seed logs clean

help: ## 显示所有可用命令
	@awk 'BEGIN {FS = ":.*##"; printf "Usage: make \033[36m<target>\033[0m\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# ==================== 开发环境 ====================

dev-up: ## 启动开发依赖（PG / Redis / MinIO）
	docker compose -f deploy/docker-compose.dev.yml up -d
	@echo "✅ 开发依赖已启动"
	@echo "  PostgreSQL: localhost:5432 (user/pass: hscredit/hscredit)"
	@echo "  Redis: localhost:6379"
	@echo "  MinIO: localhost:9001 (minio/minio123)"

dev-down: ## 停止开发依赖
	docker compose -f deploy/docker-compose.dev.yml down

dev-logs: ## 查看开发依赖日志
	docker compose -f deploy/docker-compose.dev.yml logs -f

dev-reset: ## 重置开发数据（删除所有数据）
	docker compose -f deploy/docker-compose.dev.yml down -v
	@echo "✅ 开发数据已重置"

# ==================== 后端 ====================

backend-install: ## 安装后端依赖
	cd backend && pip install -e ".[dev,test]"

backend-dev: ## 启动后端开发服务器
	cd backend && uvicorn hscredit_studio.main:app --reload --host 0.0.0.0 --port 8000

backend-shell: ## 进入后端 Python 交互
	cd backend && python

backend-format: ## 格式化后端代码
	cd backend && black hscredit_studio/ tests/ --line-length 120
	cd backend && ruff check hscredit_studio/ tests/ --fix

backend-lint: ## 后端代码检查
	cd backend && ruff check hscredit_studio/ tests/
	cd backend && mypy hscredit_studio/ --ignore-missing-imports

backend-test: ## 后端单元测试
	cd backend && pytest tests/unit/ -m unit --cov=hscredit_studio --cov-report=term

backend-test-int: ## 后端集成测试
	cd backend && pytest tests/integration/ -m integration -v

backend-test-all: ## 后端全部测试
	cd backend && pytest tests/ -m "not slow and not integration" --cov=hscredit_studio

# ==================== 前端 ====================

frontend-install: ## 安装前端依赖
	cd frontend && npm install

frontend-dev: ## 启动前端开发服务器
	cd frontend && npm run dev

frontend-build: ## 构建前端生产包
	cd frontend && npm run build

frontend-lint: ## 前端代码检查
	cd frontend && npm run lint

frontend-test: ## 前端单元测试
	cd frontend && npm run test

frontend-format: ## 格式化前端代码
	cd frontend && npm run format

# ==================== 数据库 ====================

migrate: ## 应用数据库迁移
	cd backend && alembic upgrade head

migrate-create: ## 创建新迁移
	cd backend && alembic revision --autogenerate -m "$(name)"

migrate-down: ## 回滚最后一次迁移
	cd backend && alembic downgrade -1

seed: ## 填充种子数据
	cd backend && python -m hscredit_studio.scripts.seed

db-shell: ## 进入 PostgreSQL 交互
	psql postgresql://hscredit:hscredit@localhost:5432/hscredit

db-backup: ## 数据库备份
	./scripts/backup.sh

# ==================== Docker ====================

docker-build: ## 构建所有镜像
	docker build -t hscredit-studio-backend:latest -f backend/Dockerfile backend/
	docker build -t hscredit-studio-worker:latest -f backend/Dockerfile.worker backend/
	docker build -t hscredit-studio-frontend:latest -f frontend/Dockerfile frontend/

docker-up: ## Docker Compose 启动全栈
	docker compose up -d

docker-down: ## Docker Compose 停止
	docker compose down

docker-logs: ## 查看全栈日志
	docker compose logs -f

# ==================== Kubernetes / Helm ====================

helm-deps: ## 更新 Helm 依赖
	helm dependency update charts/hscredit-studio

helm-lint: ## Helm Chart 检查
	helm lint charts/hscredit-studio

helm-template: ## 渲染 K8s 模板
	helm template hscredit charts/hscredit-studio -f charts/hscredit-studio/values.yaml > /tmp/rendered.yaml

helm-install-staging: ## 安装到 staging
	helm upgrade --install hscredit-staging charts/hscredit-studio \
		-f charts/hscredit-studio/values-staging.yaml \
		--namespace hscredit-staging --create-namespace

helm-install-prod: ## 安装到 production（需确认）
	helm upgrade --install hscredit-prod charts/hscredit-studio \
		-f charts/hscredit-studio/values-production.yaml \
		--namespace hscredit-prod --create-namespace

# ==================== 质量检查 ====================

test: backend-test frontend-test ## 跑全部测试
lint: backend-lint frontend-lint ## 代码检查
format: backend-format frontend-format ## 代码格式化

check-all: format lint test ## 完整检查（format + lint + test）

# ==================== 工具 ====================

logs: ## 查看应用日志
	docker compose -f deploy/docker-compose.dev.yml logs -f backend celery redis postgres minio

clean: ## 清理临时文件
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "node_modules" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "dist" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "build" -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ 清理完成"
