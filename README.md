# HSCredit Studio

> 基于 hscredit 的多租户 SaaS 评分卡建模云 — 让信贷风控业务策略师也能自助完成评分卡建模。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![React 18](https://img.shields.io/badge/React-18-61DAFB.svg)](https://react.dev/)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-ready-326CE5.svg)](https://kubernetes.io/)

## ✨ 核心能力

- 🎯 **拖拽式建模**：业务策略师无需 Python 也能跑评分卡
- 🔌 **88 节点库**：分箱/编码/筛选/模型/评分卡/规则全覆盖
- 🏢 **多租户 SaaS**：数据严格隔离 + RBAC + 审计
- ⚡ **全异步执行**：Celery + Redis + WebSocket 实时推送
- 🔒 **金融合规**：等保三级、PIPL、完整审计追溯
- 🌐 **中英文双语**：内置 i18n 与时区/货币本地化

## 📐 架构

```
┌─────────────────────────────────────────────┐
│ Frontend (React + react-flow)               │
└──────────────────┬──────────────────────────┘
                   │ HTTPS / WSS
┌──────────────────▼──────────────────────────┐
│ FastAPI Gateway + JWT + Multi-tenant        │
├─────────────────────────────────────────────┤
│ DAG Executor + Node Registry + Templates    │
├─────────────────────────────────────────────┤
│ Celery Workers (88 nodes via hscredit)      │
├─────────────────────────────────────────────┤
│ PostgreSQL + Redis + MinIO                  │
└─────────────────────────────────────────────┘
```

完整设计文档：[`docs/design/`](../hscredit/docs/design/)

## 🚀 快速开始

### 本地开发（Docker Compose）

```bash
# 1. 克隆仓库
git clone https://github.com/City365/HSCredit-Studio.git
cd hscredit-studio-platform

# 2. 启动依赖（PG + Redis + MinIO）
make dev-up

# 3. 跑数据库迁移
make migrate

# 4. 启动后端
make backend-dev

# 5. 另开终端启动前端
make frontend-dev

# 访问 http://localhost:3000
# 默认账号: admin@demo.com / password
```

### 生产部署（Kubernetes）

```bash
# 安装依赖
helm dependency update charts/hscredit-studio

# 部署到 staging
helm install hscredit-staging charts/hscredit-studio \
  -f charts/hscredit-studio/values-staging.yaml \
  --namespace hscredit-staging \
  --create-namespace

# 部署到 production
helm install hscredit-prod charts/hscredit-studio \
  -f charts/hscredit-studio/values-production.yaml \
  --namespace hscredit-prod \
  --create-namespace
```

## 📁 项目结构

```
hscredit-platform/
├── backend/                       # FastAPI 后端
│   ├── hscredit_studio/        # 主包
│   │   ├── main.py               # FastAPI 入口
│   │   ├── core/                 # 配置/日志/安全/DB
│   │   ├── api/v1/               # REST API
│   │   ├── models/               # SQLAlchemy ORM
│   │   ├── schemas/              # Pydantic
│   │   ├── services/             # 业务逻辑
│   │   ├── nodes/                # 节点实现（88）
│   │   ├── executor/             # DAG 执行引擎
│   │   ├── adapters/             # hscredit 适配层
│   │   └── alembic/              # 数据库迁移
│   ├── tests/                    # 测试
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/                      # React 前端
│   ├── src/
│   │   ├── pages/                # 页面
│   │   ├── components/           # 通用组件
│   │   ├── hooks/                # 自定义 hooks
│   │   ├── stores/               # Zustand
│   │   ├── api/                  # API 客户端
│   │   ├── i18n/                 # 多语言
│   │   └── ...
│   ├── package.json
│   └── Dockerfile
├── charts/                        # Helm charts
│   └── hscredit-studio/
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/            # K8s 资源模板
├── deploy/                        # 部署配置
├── observability/                 # 监控告警
│   ├── prometheus/
│   ├── grafana/
│   └── loki/
├── .github/                       # GitHub Actions
└── docs/                          # 项目文档
```

## 🧪 测试

```bash
# 后端单元测试
make test-unit

# 后端集成测试（需要 Docker）
make test-integration

# 前端测试
make test-frontend

# E2E 测试（需要完整环境）
make test-e2e

# 全部
make test-all
```

## 🔧 常用命令

```bash
make help          # 查看所有可用命令
make dev-up        # 启动开发环境
make dev-down      # 停止开发环境
make backend-dev   # 启动后端开发服务器
make frontend-dev  # 启动前端开发服务器
make lint          # 代码检查
make format        # 代码格式化
make migrate       # 数据库迁移
make seed          # 种子数据
make logs          # 查看日志
make clean         # 清理
```

## 📚 文档

- [开发指南](docs/DEVELOPMENT.md)
- [部署指南](docs/DEPLOYMENT.md)
- [架构设计](../hscredit/docs/design/)（在 hscredit 仓库）
- [API 文档](https://developer.hscredit.com)（部署后可用）

## 🤝 贡献

参见 [CONTRIBUTING.md](CONTRIBUTING.md)

## 📄 许可证

[MIT License](LICENSE)

## 📞 联系方式

- 项目主页：https://github.com/City365/HSCredit-Studio
- 问题反馈：https://github.com/City365/HSCredit-Studio/issues
- 邮件：dev@hscredit.example.com
