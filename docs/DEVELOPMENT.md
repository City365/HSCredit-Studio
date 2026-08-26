# 开发指南

## 环境要求

- Python 3.11+
- Node.js 20+
- Docker + Docker Compose
- PostgreSQL 15 client（可选）
- Helm 3.x（可选，用于 K8s 部署）

## 快速开始

### 1. 克隆并启动开发依赖

```bash
git clone https://github.com/City365/HSCredit-Studio.git
cd hscredit-studio-platform

# 启动 PG + Redis + MinIO
make dev-up
```

### 2. 安装后端依赖

```bash
make backend-install
```

### 3. 应用数据库迁移

```bash
make migrate
```

### 4. 填充种子数据

```bash
make seed
```

### 5. 启动后端

```bash
make backend-dev
# 后端运行在 http://localhost:8000
# API 文档: http://localhost:8000/api/docs
```

### 6. 启动前端

```bash
make frontend-install   # 仅首次
make frontend-dev
# 前端运行在 http://localhost:3000
```

## 项目结构

```
hscredit-platform/
├── backend/                # FastAPI 后端
│   ├── hscredit_studio/  # 主包
│   ├── tests/              # 测试
│   └── pyproject.toml
├── frontend/               # React 前端
│   ├── src/
│   └── package.json
├── charts/                 # Helm charts
├── deploy/                 # Docker Compose
├── observability/          # 监控配置
├── scripts/                # 工具脚本
└── docs/                   # 项目文档
```

## 开发工作流

### 后端开发

```bash
# 创建新功能分支
git checkout -b feature/my-feature

# 修改代码
# ...

# 跑测试
make backend-test

# 代码检查
make backend-lint

# 提交前
make check-all

# 提交并推送
git add .
git commit -m "feat: my feature"
git push origin feature/my-feature
```

### 前端开发

```bash
# 创建组件
mkdir src/components/MyComponent
touch src/components/MyComponent/index.tsx
touch src/components/MyComponent/MyComponent.test.tsx

# 添加路由（src/router.tsx）
# 添加菜单（src/components/Layout/Sidebar.tsx）

# 测试
make frontend-test

# 类型检查
cd frontend && npm run type-check
```

### 添加新节点

节点开发流程：

1. 在 `backend/hscredit_studio/nodes/{category}/` 下创建新文件
2. 实现节点接口（参考 [03-node-catalog.md](../hscredit/docs/design/03-node-catalog.md)）
3. 注册到 NodeRegistry
4. 添加单元测试

```python
# backend/hscredit_studio/nodes/feature_engineering/my_node.py
from hscredit_studio.nodes.base import BaseNode
from hscredit_studio.nodes.registry import register_node
from hscredit_studio.schemas.contracts import NodeContract, PortSchema, ParamSpec

class MyNode(BaseNode):
    contract = NodeContract(
        node_type="my_node",
        category="特征工程",
        name="我的节点",
        description="节点说明",
        inputs=[
            PortSchema(name="df", type="DataFrame", required=True),
        ],
        outputs=[
            PortSchema(name="result", type="DataFrame"),
        ],
        params=[
            ParamSpec(name="param1", type="int", default=8, label="参数1"),
        ],
    )
    
    def run(self, inputs, params):
        df = inputs["df"]
        # ... 算法逻辑
        return {"result": df}

register_node(MyNode)
```

### 数据库迁移

```bash
# 自动生成迁移（修改 model 后）
make migrate-create name="add_new_table"

# 检查迁移 SQL
cat backend/alembic/versions/xxxx_add_new_table.py

# 应用迁移
make migrate

# 回滚
make migrate-down
```

## 测试

### 单元测试

```bash
# 后端
make backend-test

# 前端
make frontend-test
```

### 集成测试

需要 Docker。会自动启动 testcontainers。

```bash
make backend-test-int
```

### E2E 测试

需要完整环境（前后端 + 依赖）。

```bash
# 启动所有服务
make dev-up
make migrate
make seed

# 启动后端 + 前端（两个终端）

# 跑 E2E
make test-e2e
```

### 覆盖率

```bash
# 后端
make backend-test  # 自动生成 coverage 报告

# 前端
cd frontend && npm run test:coverage
```

## 调试技巧

### 后端日志

```python
from hscredit_studio.core.logging import get_logger
log = get_logger(__name__)
log.info("message", extra={"user_id": "123"})
```

### 前端调试

```typescript
// 浏览器 DevTools
// - React DevTools 扩展
// - Redux DevTools（Zustand）
// - Network 面板查看 API 请求
// - WebSocket frames 查看实时日志
```

### 数据库查询

```bash
make db-shell

# 或
psql postgresql://hscredit:hscredit@localhost:5432/hscredit

# 查看最近 runs
SELECT run_id, status, submitted_at FROM runs ORDER BY submitted_at DESC LIMIT 10;
```

## 提交规范

使用 [Conventional Commits](https://www.conventionalcommits.org/)：

```
feat: 新功能
fix: 修复
docs: 文档
style: 格式
refactor: 重构
test: 测试
chore: 构建/工具
```

## 常见问题

### Q: pip install 失败？
A: 检查 Python 版本 ≥ 3.11；删除 `backend/.venv` 后重试。

### Q: 前端 npm install 卡住？
A: 配置淘宝镜像：`npm config set registry https://registry.npmmirror.com`。

### Q: Docker Compose 起不来？
A: 检查 Docker 是否运行；端口 5432/6379/9001 是否被占用。

### Q: 数据库迁移失败？
A: 检查 `DATABASE_URL` 环境变量；确认 PG 已启动；查看 alembic 错误日志。
