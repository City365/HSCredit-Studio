# 节点可插拔改造 — 设计文档

> 本文档是节点管理 + 自定义节点可插拔特性的完整设计依据, 含 4 大章节:
> 1. 存储设计 (DB 表 + 文件存储)
> 2. 前端页面设计 (页面布局 + 交互)
> 3. 后端 API 设计 (RESTful)
> 4. 前后端联合调度 (时序图 + 数据流)

---

## 1. 存储设计

### 1.1 决策: 不引入 SQLite, 沿用 PostgreSQL

**原方案候选**:
- A. 引入 SQLite + 单独存储
- B. 沿用 PostgreSQL (本项目主库)
- C. 混合: 元数据 PostgreSQL + 代码对象存储 (MinIO)

**最终选择**: **B. 沿用 PostgreSQL**

**理由**:
1. **已有 CustomNode / CustomNodeVersion / CustomNodeTestRun 表** 完全够用, 字段覆盖完整 (code/contract/visibility/versions/test_runs)
2. **SQLite 引入会增加运维负担** — 需要 schema 迁移, 多库一致性, 备份策略
3. **代码通常 < 50 KB/节点**, 存 PG TEXT 字段足够, 性能影响可忽略
4. **统一 RLS / 审计 / 备份**: PostgreSQL 已经做完了
5. **多租户隔离**: 已用 RLS + tenant_id 字段
6. **如未来代码膨胀** (单节点 > 1 MB) → 走方案 C 切到 MinIO, 不影响 schema (只需把 `code` 改成 `code_storage_key` String)

### 1.2 数据库表设计 (现有 + 扩展)

#### 1.2.1 `node_definitions` 表 (扩展)

**现状**: 系统节点缓存表, 全局共享.

**新增字段** (alembic migration 0015):

```sql
ALTER TABLE node_definitions
  -- 区分系统/自定义节点
  ADD COLUMN is_custom BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN source VARCHAR(16) NOT NULL DEFAULT 'system',  -- 'system' / 'custom'
  -- 自定义节点所属租户 (NULL = 系统节点)
  ADD COLUMN owner_tenant_id UUID NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  -- 元数据可编辑 (name/description/icon)
  ADD COLUMN meta_editable BOOLEAN NOT NULL DEFAULT FALSE,
  -- 时间戳 (TimestampMixin 已有, 但需补 updated_at)
  ADD CONSTRAINT fk_node_definitions_tenant FOREIGN KEY (owner_tenant_id)
    REFERENCES tenants(tenant_id) ON DELETE CASCADE;

-- 索引
CREATE INDEX ix_node_definitions_tenant ON node_definitions (owner_tenant_id);
CREATE INDEX ix_node_definitions_custom_enabled ON node_definitions (is_custom, enabled);
CREATE INDEX ix_node_definitions_source ON node_definitions (source);
```

#### 1.2.2 `custom_nodes` 表 (扩展)

**现状**: 已存在, 字段: `custom_node_id / node_type / name / visibility / code / requirements / contract / approved_at / approved_by / created_by / versions relationship`.

**新增字段**:

```sql
ALTER TABLE custom_nodes
  -- 启停控制 (供管理页面开关)
  ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT TRUE,
  -- 元数据可编辑字段
  ADD COLUMN icon VARCHAR(128) NULL,
  ADD COLUMN description TEXT NULL,
  -- 节点分类 (前端按 category 分组显示)
  ADD COLUMN category VARCHAR(64) NOT NULL DEFAULT '特征工程',
  -- 当前激活版本号 (冗余, 便于直接定位)
  ADD COLUMN current_version_number INTEGER NULL,
  -- 试运行次数 / 最后试运行时间
  ADD COLUMN last_test_run_at TIMESTAMPTZ NULL,
  ADD COLUMN test_run_count INTEGER NOT NULL DEFAULT 0,
  -- 锁定标志 (编辑时锁定, 防止并发覆盖)
  ADD COLUMN locked_by UUID NULL REFERENCES users(user_id) ON DELETE SET NULL,
  ADD COLUMN locked_at TIMESTAMPTZ NULL;

-- 索引
CREATE INDEX ix_custom_nodes_enabled ON custom_nodes (enabled);
CREATE INDEX ix_custom_nodes_tenant_enabled ON custom_nodes (tenant_id, enabled);
CREATE INDEX ix_custom_nodes_category ON custom_nodes (tenant_id, category);
```

#### 1.2.3 `custom_node_versions` 表 (无需扩展, 已有)

**现状字段**: `version_id / custom_node_id / version_number / code / contract / requirements / change_summary / created_by`.

**已满足需求**: 完整版本管理 + 回滚支持.

#### 1.2.4 `custom_node_test_runs` 表 (无需扩展, 已有)

**现状字段**: `test_run_id / version_id / status / log / started_at / finished_at / triggered_by`.

**已满足需求**: 试运行记录追踪.

#### 1.2.5 新增表 `node_definition_drafts` (草稿)

**用途**: 用户在 UI 上编辑节点时, 不直接覆盖正式表, 先存草稿, 试运行通过后才提交正式版本.

```sql
CREATE TABLE node_definition_drafts (
    draft_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    custom_node_id UUID NOT NULL REFERENCES custom_nodes(custom_node_id) ON DELETE CASCADE,
    draft_code TEXT NOT NULL,
    draft_contract JSONB NOT NULL DEFAULT '{}'::jsonb,
    contract_preview JSONB NULL,  -- AST 反推的 contract 预览
    validation_status VARCHAR(16) NOT NULL DEFAULT 'draft',  -- 'draft' / 'validating' / 'valid' / 'invalid'
    validation_issues JSONB NULL,
    last_validation_at TIMESTAMPTZ NULL,
    locked_by UUID REFERENCES users(user_id),
    locked_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE(custom_node_id)  -- 每个 custom_node 只有一个活跃草稿
);

CREATE INDEX ix_drafts_validation_status ON node_definition_drafts (validation_status);
```

**为什么需要草稿表**:
- 用户编辑时频繁保存, 不应触发版本历史膨胀
- 草稿可以"丢弃", 不污染版本
- 草稿的 contract_preview 缓存, 减少后端 AST 重复计算

#### 1.2.6 新增表 `node_definition_locks` (编辑锁)

**用途**: 防止多人同时编辑同一节点导致覆盖.

```sql
CREATE TABLE node_definition_locks (
    lock_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_type VARCHAR(128) NOT NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    locked_by UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    locked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    UNIQUE(node_type, tenant_id)
);

CREATE INDEX ix_node_locks_expires ON node_definition_locks (expires_at);
```

**锁策略**:
- 进入编辑页时, 后端申请锁 (TTL 5 分钟, 可续期)
- 心跳每 2 分钟续期一次
- 关闭页面或切换租户时释放锁
- 锁过期后自动释放 (数据库触发器 / Celery beat 定时清理)

### 1.3 文件存储设计

**决策**: **代码不存文件, 全部在 PostgreSQL TEXT 字段.**

**理由**:
- 避免文件路径管理 (跨平台 Windows / Linux 兼容性)
- 避免文件权限 / git 同步问题
- DB 事务一致性
- 已有 `requirements` 字段支持依赖白名单

**唯一文件存储场景**: 试运行沙箱的 payload 文件 (`/tmp/payload.pkl`), 这是临时的, 不算长期存储.

### 1.4 数据生命周期

| 数据 | 保留期 | 清理策略 |
|------|--------|----------|
| `node_definitions` | 永久 | 软删除, 系统节点 `enabled=false` 等同删除 |
| `custom_nodes` | 永久 (SoftDeleteMixin) | 软删除, 30 天后由 Celery beat 清理 |
| `custom_node_versions` | 永久 | 跟随 custom_node, 删除时级联 |
| `custom_node_test_runs` | 90 天 | TTL 清理 |
| `node_definition_drafts` | 30 天无更新 | 自动清理 |
| `node_definition_locks` | 锁过期自动释放 | Celery beat 清理 |

---

## 2. 前端页面设计

### 2.1 路由结构

```
/nodes                          # 节点管理主页 (列表)
  /nodes/new                    # 新增节点向导 (5 步)
  /nodes/:id                    # 节点详情 (只读, 含版本历史)
  /nodes/:id/edit               # 节点编辑 (代码编辑器)
  /nodes/:id/test               # 试运行面板 (弹窗或独立页)
```

### 2.2 节点管理主页 `/nodes`

#### 2.2.1 布局 (截图草图)

```
┌─────────────────────────────────────────────────────────────────────┐
│ ◄ 返回  节点管理                              [同步系统节点] [+新增]   │
├─────────────────────────────────────────────────────────────────────┤
│ 搜索框: [____________________]                                     │
│ 过滤:   分类 ▼  来源 ▼  状态 ▼  可见性 ▼                          │
├─────────────────────────────────────────────────────────────────────┤
│ 表格:                                                              │
│ ┌─────────┬──────────┬────────┬──────────┬──────┬─────────────┐    │
│ │ 节点类型│ 名称     │ 分类   │ 来源     │ 状态 │ 操作        │    │
│ ├─────────┼──────────┼────────┼──────────┼──────┼─────────────┤    │
│ │xgboost  │XGBoost   │模型训练│ 🛠️ 系统  │ ●启用│ ⋯          │    │
│ │my_node  │我的节点  │特征工程│ 👤 自定义│ ●启用│ ⋯          │    │
│ │broken   │坏掉的    │EDA    │ 👤 自定义│ ○停用│ ⋯          │    │
│ └─────────┴──────────┴────────┴──────────┴──────┴─────────────┘    │
│                                                                     │
│ 分页: < 1 2 3 >  共 N 条                                          │
└─────────────────────────────────────────────────────────────────────┘
```

#### 2.2.2 列定义

| 列 | 字段 | 宽度 | 排序 | 说明 |
|---|---|---|---|---|
| 节点类型 | `node_type` | 200px | ✅ | 等宽字体 |
| 名称 | `name` | 200px | ✅ | 中文显示名 |
| 分类 | `category` | 120px | ✅ | Tag 颜色分类 |
| 来源 | `is_custom` → `system`/`custom` | 100px | ✅ | icon 区分 |
| 状态 | `enabled` | 100px | ✅ | Switch 开关 |
| 操作 | (按钮组) | 200px | - | 详情/编辑/测试/删除 |

#### 2.2.3 操作菜单 (行内 "..." 按钮)

| 操作 | 系统节点 | 自定义节点 | 权限 |
|---|---|---|---|
| 查看详情 | ✅ | ✅ | 登录 |
| 编辑元数据 (name/desc/icon/enabled) | ✅ | ✅ | tenant_admin / super_admin |
| 编辑代码 | ❌ | ✅ | owner |
| 试运行 | ❌ | ✅ | owner |
| 版本历史 | ❌ | ✅ | owner |
| 删除 | ❌ | ✅ | owner |

#### 2.2.4 顶部按钮

- **同步系统节点**: 重新从 NodeRegistry 同步到 DB. **仅 super_admin**.
- **+新增**: 跳转 `/nodes/new` 向导. **tenant_admin+**.

### 2.3 节点编辑页 `/nodes/:id/edit`

#### 2.3.1 布局 (左右分栏)

```
┌─────────────────────────────────────────────────────────────────────┐
│ ◄ 返回  节点: my_filter_v1  v2 / v3 ▼  [启停: ●]  [保存版本] [试运行] │
├────────────────────────────────────┬────────────────────────────────┤
│ 代码编辑器 (Monaco)                  │ 实时 contract 预览            │
│ ┌────────────────────────────────┐ │ ┌──────────────────────────┐ │
│ │1  from hscredit_studio....      │ │ │ 分类: [特征工程 ▼]        │ │
│ │2  class MyFilterNode(BaseNode):│ │ │ 名称: [我的过滤器     ]   │ │
│ │3    contract = NodeContract(   │ │ │ 图标: [🛠️]              │ │
│ │4      node_type="my_filter_v1",│ │ │                          │ │
│ │5      category="特征工程",     │ │ │ 输入端口:                │ │
│ │6      inputs=[PortSchema(...)], │ │ │  • df (DataFrame) ✓     │ │
│ │7      ...                       │ │ │                          │ │
│ │8    )                           │ │ │ 输出端口:                │ │
│ │9    def run(self, inputs, ...):│ │ │  • filtered_df (DataFrame)│ │
│ │10     ...                       │ │ │                          │ │
│ └────────────────────────────────┘ │ │ 参数:                     │ │
│ 状态栏: ✓ 校验通过 | 3 行错误 | 编译中│ │  • threshold (float) 0.5│ │
│                                     │ │                          │ │
│                                     │ │ [▶ 试运行] [📋 复制]    │ │
│                                     │ └──────────────────────────┘ │
├────────────────────────────────────┴────────────────────────────────┤
│ 底部状态条:                                                          │
│ 📊 试运行 5 次通过 | 📝 最近保存 v3 (3 天前) | ⏱ 编辑时长 12 分钟   │
└─────────────────────────────────────────────────────────────────────┘
```

#### 2.3.2 关键交互

| 交互 | 行为 |
|---|---|
| 编辑代码 | 防抖 500ms 后调用 AST 静态校验 |
| 修改 contract | 防抖 800ms 后调用反推 API 更新预览 |
| 版本下拉切换 | 加载该版本代码到编辑器 (只读, 不保存到当前草稿) |
| 点击"保存版本" | 弹出版本提交对话框, 输入 change_summary, 创建新 version |
| 点击"试运行" | 打开试运行面板, 弹出 sample data 输入框 |
| 点击"启停" Switch | 调用 PUT 切换 enabled |
| 自动保存草稿 | 每 30 秒或修改后 5 秒静默保存到 `node_definition_drafts` |
| 心跳续锁 | 每 2 分钟续期编辑锁 |
| 关闭页面 | 释放编辑锁 (navigator.sendBeacon) |

#### 2.3.3 试运行面板 (Modal)

```
┌─────────────────────────────────────────────────┐
│ 试运行: my_filter_v1                              │
├─────────────────────────────────────────────────┤
│ 输入样本:                                         │
│   ○ 上传 CSV                                      │
│   ○ 粘贴 JSON                                     │
│   [___________________________] [选择文件]       │
│                                                  │
│ 参数:                                             │
│   threshold: [0.7]                                │
│                                                  │
│ [▶ 运行]                                          │
├─────────────────────────────────────────────────┤
│ 状态: ✓ 成功 (耗时 234ms)                        │
│                                                  │
│ 输出:                                             │
│   filtered_df: DataFrame (1000 rows × 5 cols)    │
│                                                  │
│ 日志:                                             │
│   [12:34:56] 开始执行                             │
│   [12:34:56] filtered 1000 → 723 rows            │
│   [12:34:56] 完成                                  │
│                                                  │
│ [复制为版本] [下载日志]                          │
└─────────────────────────────────────────────────┘
```

### 2.4 新增节点向导 `/nodes/new`

**5 步流程** (Stepper):

```
Step 1: 起点选择
  ┌────────────────────────────────────────┐
  │  ○ 从空白创建                          │
  │  ○ 从系统节点复制                       │
  │  ○ 从自定义节点复制 (我的或其他租户)    │
  └────────────────────────────────────────┘
  [取消] [下一步 →]

Step 2: 基础信息
  ┌────────────────────────────────────────┐
  │ 节点类型 (node_type): [my_filter_v1]   │
  │ 分类: [特征工程 ▼]                     │
  │ 名称 (中文): [我的过滤器       ]        │
  │ 图标 (emoji): [🛠️]                    │
  │ 可见性: [private / tenant / public ▼] │
  └────────────────────────────────────────┘
  [← 上一步] [下一步 →]

Step 3: 代码编辑 (Monaco)
  ┌────────────────────────────────────────┐
  │ 代码编辑器 (带模板)                     │
  │ [实时校验状态: ✓ 通过 / 3 行错误]      │
  └────────────────────────────────────────┘
  [← 上一步] [下一步 →]

Step 4: 测试样本 + 试运行
  ┌────────────────────────────────────────┐
  │ 输入样本 (CSV/JSON)                     │
  │ 参数填值                                  │
  │ [▶ 试运行] → 显示 outputs               │
  └────────────────────────────────────────┘
  [← 上一步] [下一步 →]

Step 5: 确认 + 保存
  ┌────────────────────────────────────────┐
  │ 节点摘要:                                │
  │   类型: my_filter_v1                    │
  │   分类: 特征工程                         │
  │   名称: 我的过滤器                       │
  │   来源: 自定义 (private)                │
  │   试运行: ✓ 通过 (1 次)                 │
  │                                          │
  │ [✓] 确认并保存为 v1                      │
  └────────────────────────────────────────┘
  [← 上一步] [保存] → 跳转 /nodes/:id/edit
```

### 2.5 RBAC 在前端的表现

| 角色 | /nodes 可见 | 新增按钮 | 启停开关 | 编辑代码 | 删除 |
|---|---|---|---|---|---|
| super_admin | ✅ | ✅ | ✅ | ✅ (全租户) | ✅ |
| tenant_admin | ✅ | ✅ | ✅ (本租户) | ✅ (本租户) | ✅ (本租户) |
| analyst | ✅ | ❌ | ❌ | ❌ | ❌ |
| viewer | ✅ | ❌ | ❌ | ❌ | ❌ |

前端通过 `useAuthStore` 读 `role`, 组件级隐藏按钮; 后端二次校验.

---

## 3. 后端 API 设计

### 3.1 API 总览

| 路径 | 方法 | 功能 | 权限 |
|---|---|---|---|
| **系统节点** | | | |
| `/api/v1/{tenant}/node-definitions` | GET | 列出节点 | 登录 |
| `/api/v1/{tenant}/node-definitions/{node_type}/enable` | PUT | 启用 | super_admin |
| `/api/v1/{tenant}/node-definitions/{node_type}/disable` | PUT | 停用 | super_admin |
| `/api/v1/{tenant}/node-definitions/{node_type}/meta` | PUT | 改 name/desc/icon | super_admin |
| `/api/v1/{tenant}/node-definitions/sync` | POST | 同步系统节点 | super_admin |
| `/api/v1/{tenant}/node-definitions/{node_type}` | GET | 单节点详情 | 登录 |
| **自定义节点** | | | |
| `/api/v1/{tenant}/custom-nodes` | GET | 列出 (可见范围内) | 登录 |
| `/api/v1/{tenant}/custom-nodes` | POST | 创建 | tenant_admin+ |
| `/api/v1/{tenant}/custom-nodes/{id}` | GET | 详情 | 登录 (限可见) |
| `/api/v1/{tenant}/custom-nodes/{id}` | PUT | 更新元数据 | owner |
| `/api/v1/{tenant}/custom-nodes/{id}` | DELETE | 软删除 | owner |
| `/api/v1/{tenant}/custom-nodes/{id}/code` | PUT | 提交新版本 | owner |
| `/api/v1/{tenant}/custom-nodes/{id}/versions` | GET | 版本列表 | 登录 |
| `/api/v1/{tenant}/custom-nodes/{id}/versions/{vid}` | GET | 版本详情 | 登录 |
| `/api/v1/{tenant}/custom-nodes/{id}/versions/{vid}/rollback` | POST | 回滚 | owner |
| **草稿** | | | |
| `/api/v1/{tenant}/custom-nodes/{id}/draft` | GET | 取草稿 | owner |
| `/api/v1/{tenant}/custom-nodes/{id}/draft` | PUT | 保存草稿 (静默) | owner |
| `/api/v1/{tenant}/custom-nodes/{id}/draft` | DELETE | 丢弃草稿 | owner |
| **编辑锁** | | | |
| `/api/v1/{tenant}/custom-nodes/{id}/lock` | POST | 申请锁 | owner |
| `/api/v1/{tenant}/custom-nodes/{id}/lock` | DELETE | 释放锁 | owner |
| `/api/v1/{tenant}/custom-nodes/{id}/lock/heartbeat` | POST | 心跳续期 | owner |
| **校验 / 试运行** | | | |
| `/api/v1/{tenant}/custom-nodes/{id}/validate` | POST | AST 静态校验 | owner |
| `/api/v1/{tenant}/custom-nodes/{id}/detect-contract` | POST | 反推 contract | owner |
| `/api/v1/{tenant}/custom-nodes/{id}/test` | POST | 沙箱试运行 | owner |
| `/api/v1/{tenant}/custom-nodes/{id}/test-runs` | GET | 试运行历史 | owner |

### 3.2 请求/响应 Schema (核心)

#### 3.2.1 POST /custom-nodes 创建请求

```json
{
  "node_type": "my_filter_v1",
  "name": "我的过滤器",
  "category": "特征工程",
  "description": "按分数阈值过滤样本",
  "icon": "🛠️",
  "code": "from hscredit_studio.nodes.base import BaseNode\n...",
  "contract": {
    "node_type": "my_filter_v1",
    "category": "特征工程",
    "name": "我的过滤器",
    "inputs": [{"name": "df", "type": "DataFrame", "required": true}],
    "outputs": [{"name": "filtered_df", "type": "DataFrame"}],
    "params": [{"name": "threshold", "type": "float", "default": 0.5, "required": false}]
  },
  "visibility": "private",
  "requirements": "pandas>=2.0"
}
```

**响应**:
```json
{
  "custom_node_id": "uuid",
  "version_id": "uuid",
  "version_number": 1,
  "node_type": "my_filter_v1",
  "created_at": "2026-09-11T12:00:00Z"
}
```

#### 3.2.2 POST /custom-nodes/{id}/validate 请求/响应

**请求**:
```json
{
  "code": "..."
}
```

**响应** (静态校验):
```json
{
  "valid": false,
  "issues": [
    {
      "line": 3,
      "column": 1,
      "severity": "error",
      "rule": "import_blocked",
      "message": "禁止导入 os 模块"
    },
    {
      "line": 7,
      "column": 5,
      "severity": "error",
      "rule": "must_inherit_basemethod",
      "message": "类必须继承 BaseNode"
    }
  ],
  "ast_preview": {
    "class_name": "MyFilterNode",
    "has_run_method": true,
    "has_contract": true,
    "imports": ["import os"],
    "methods": ["__init__", "run"]
  }
}
```

#### 3.2.3 POST /custom-nodes/{id}/detect-contract 请求/响应

**请求**:
```json
{
  "code": "...",
  "sample_data": {
    "columns": ["score", "label"],
    "rows": [[0.9, 0], [0.3, 1]]
  }
}
```

**响应**:
```json
{
  "draft_contract": {
    "node_type": "my_filter_v1",
    "category": "特征工程",
    "name": "我的过滤器",
    "inputs": [{"name": "df", "type": "DataFrame", "required": true, "description": "由 AST 推断"}],
    "outputs": [{"name": "filtered_df", "type": "DataFrame", "description": "由试运行反推"}],
    "params": [{"name": "threshold", "type": "float", "default": 0.5}]
  },
  "ast_inferred": {
    "input_ports_from_inputs": ["df"],
    "output_ports_from_return": ["filtered_df"],
    "param_names_from_kwargs": ["threshold"]
  },
  "runtime_inferred": {
    "output_keys": ["filtered_df"],
    "output_types": {"filtered_df": "DataFrame"}
  },
  "warnings": [
    "output 类型只能反推为 DataFrame (无法确定具体 schema, 由前端人工确认)"
  ]
}
```

#### 3.2.4 POST /custom-nodes/{id}/test 请求/响应

**请求**:
```json
{
  "version_id": "uuid (可选, 默认 current)",
  "sample_inputs": {
    "df": "<DataFrame 列定义>"
  },
  "sample_params": {
    "threshold": 0.7
  },
  "sample_data": {
    "format": "csv",
    "content": "score,label\n0.9,0\n0.3,1\n0.8,1"
  }
}
```

**响应**:
```json
{
  "test_run_id": "uuid",
  "status": "success",  // 'success' / 'failed' / 'timeout' / 'oom'
  "duration_ms": 234,
  "outputs": {
    "filtered_df": {
      "type": "DataFrame",
      "shape": [723, 5],
      "columns": ["score", "label", "id", "ts", "feature"]
    }
  },
  "logs": [
    "[12:34:56] 开始执行",
    "[12:34:56] filtered 1000 → 723 rows",
    "[12:34:56] 完成"
  ],
  "resource_usage": {
    "cpu_seconds": 0.18,
    "mem_peak_mb": 156,
    "sandbox_backend": "subprocess"
  },
  "error": null
}
```

### 3.3 错误码

| HTTP | code | 含义 |
|---|---|---|
| 400 | `E_VALIDATION_ERROR` | 静态校验失败 (含 issues 详情) |
| 400 | `E_AST_PARSE_ERROR` | 代码语法错误 |
| 403 | `E_PERMISSION_DENIED` | 无权限 |
| 404 | `E_NODE_NOT_FOUND` | 节点不存在 |
| 409 | `E_NODE_TYPE_CONFLICT` | node_type 已存在 (创建时) |
| 409 | `E_NODE_LOCKED` | 节点被他人编辑锁定 |
| 422 | `E_CONTRACT_INVALID` | contract 不符合 Pydantic schema |
| 429 | `E_RATE_LIMITED` | 试运行频率限制 |
| 500 | `E_SANDBOX_TIMEOUT` | 试运行超时 |
| 500 | `E_SANDBOX_OOM` | 试运行 OOM |
| 500 | `E_SANDBOX_EXECUTION` | 试运行其他异常 |

### 3.4 静态校验规则 (AST 黑/白名单)

**黑名单 (禁止)**:
- `import os` / `from os` / `import subprocess` / `from subprocess`
- `import socket` / `import urllib.request` / `import urllib3`
- `import ctypes` / `import shutil`
- `import sys` (白名单 builtin 可用)
- `import pickle` / `import marshal` / `import cloudpickle`
- `eval()` / `exec()` / `compile()` 调用
- `open()` 调用 (除明确允许路径如 `data/`)
- `__import__()` 调用
- 任何 `__dunder__` 属性访问 (除 `_init_` `_str_` 等 SafeDunders 白名单)

**白名单 (允许的 builtin)**:
- `print` / `len` / `range` / `enumerate` / `zip` / `map` / `filter`
- `int` / `float` / `str` / `bool` / `list` / `dict` / `tuple` / `set`
- `isinstance` / `type` / `getattr` (受限) / `setattr` (受限)
- `sorted` / `reversed` / `min` / `max` / `sum` / `abs`
- `import math` / `import json` / `import re` / `import datetime`
- `import numpy as np` / `import pandas as pd`
- `from hscredit_studio.nodes.base import BaseNode`
- `from hscredit_studio.schemas.node_contract import NodeContract, PortSchema, ParamSpec, ...`

**必须满足**:
- 至少一个类继承 `BaseNode`
- 该类有 `contract = NodeContract(...)` 类变量
- 该类有 `def run(self, inputs, params)` 方法
- `run` 返回值必须是 `dict`

---

## 4. 前后端联合调度

### 4.1 节点创建全流程时序图

```
┌──────┐      ┌────────┐      ┌──────┐      ┌─────────┐      ┌──────┐
│ 用户 │      │ 前端   │      │ 后端 │      │ 沙箱    │      │  DB  │
└──┬───┘      └───┬────┘      └───┬──┘      └────┬────┘      └──┬───┘
   │  1.填写表单   │               │               │               │
   │─────────────►│               │               │               │
   │              │               │               │               │
   │              │ 2.POST /custom-nodes          │               │
   │              │  {code, contract, ...}        │               │
   │              │──────────────►│               │               │
   │              │               │ 3.静态校验    │               │
   │              │               │  (AST 检查)   │               │
   │              │               │               │               │
   │              │               │ 4. INSERT custom_nodes +     │
   │              │               │     INSERT custom_node_versions│
   │              │               │────────────────────────────►│
   │              │               │               │               │
   │              │               │ 5. 反推 contract (AST + 试运行)│
   │              │               │──────────────►│               │
   │              │               │  sample_inputs              │
   │              │               │               │ 6. 执行       │
   │              │               │◄──────────────│  outputs      │
   │              │               │               │               │
   │              │               │ 7. 加载到 NodeRegistry        │
   │              │               │  (DB → 内存)                 │
   │              │               │               │               │
   │              │ 8.201 Created │               │               │
   │              │  {custom_node_id, version_id}│               │
   │              │◄──────────────│               │               │
   │ 9.跳转       │               │               │               │
   │  /nodes/:id/edit           │               │               │
   │◄─────────────│               │               │               │
```

### 4.2 节点编辑保存流程 (防抖 + 心跳)

```
用户输入代码 (Monaco onChange)
    │
    ├─ 防抖 500ms ─► 调 POST /validate (静态校验)
    │                  │
    │                  ├─ valid=true → 显示 ✓
    │                  └─ valid=false → 显示 issues (squiggle)
    │
    ├─ 防抖 800ms ─► 调 POST /detect-contract (AST 反推)
    │                  │
    │                  └─ 更新右侧 contract 预览
    │
    ├─ 静默保存 (5s 无输入) ─► 调 PUT /draft (保存到 drafts 表)
    │                            │
    │                            └─ 后端返回 draft_id
    │
    ├─ 心跳 (每 2min) ─► POST /lock/heartbeat (续锁 5min)
    │
    └─ 手动 [保存版本] ─► 弹出版本提交对话框
                          │
                          └─ 调 PUT /custom-nodes/{id}/code (创建新 version)
```

### 4.3 试运行流程

```
用户点击 [▶ 试运行]
    │
    ├─ 弹出试运行面板 (Modal)
    │
    ├─ 用户填 sample_inputs + sample_params
    │
    ├─ 用户点击 [▶ 运行]
    │    │
    │    ├─ 前端调 POST /custom-nodes/{id}/test
    │    │     {sample_inputs, sample_params, sample_data}
    │    │
    │    ├─ 后端异步执行 (返回 test_run_id)
    │    │
    │    ├─ 前端轮询 GET /test-runs/{id} 或 WS 订阅
    │    │
    │    └─ 显示 results / logs / errors
    │
    └─ 用户可点 [复制为版本] (把试运行的代码作为新版本保存)
```

### 4.4 NodeRegistry 合并视图

**启动时**:
```
1. 加载所有内置节点 (代码 @register_node 装饰器)
2. 从 DB 加载所有 custom_nodes (enabled=true 且 visibility 可见)
3. 对每个 custom_node:
   a. 用其 latest version code 编译成 BaseNode 子类
   b. 调用 NodeRegistry.register(temp_cls)
   c. 记录 source='custom', owner_tenant_id=...
4. 前端 GET /node-definitions 返回合并视图 (含 is_custom 标识)
```

**自定义节点更新时**:
```
PUT /custom-nodes/{id}/code
    │
    ├─ DB: 创建新 CustomNodeVersion + 更新 custom_nodes.code/current_version
    │
    ├─ NodeRegistry.unregister(old_node_type)
    │
    ├─ 编译新代码 + NodeRegistry.register(new_cls)
    │
    └─ 通过 Redis pub/sub 通知所有 worker 进程 reload
        (Celery worker 多进程需要同步)
```

### 4.5 沙箱执行 (Subprocess + 资源限制)

```
后端收到 POST /test 请求
    │
    ├─ 写入 custom_node_test_runs (status=queued)
    │
    ├─ 生成 payload.pkl (含 node_type / sample_inputs / sample_params)
    │
    ├─ 调用 UserSandbox.execute_with_usage()
    │    │
    │    ├─ subprocess.Popen([python, -I -B, _sandbox_worker.py, payload.pkl])
    │    │   ├─ preexec_fn: setrlimit(RLIMIT_CPU, 60s), setrlimit(RLIMIT_AS, 2Gi)
    │    │   ├─ cwd: /tmp/sandbox_<random>
    │    │   └─ env: 限制 PATH, 无网络访问 (subprocess flags)
    │    │
    │    ├─ 子进程 _sandbox_worker.py:
    │    │   ├─ 加载用户代码 (RestrictedPython 编译, AST 黑名单二次校验)
    │    │   ├─ exec(code, restricted_globals)
    │    │   ├─ 查找 BaseNode 子类 + 实例化
    │    │   ├─ 加载 sample_inputs → inputs dict
    │    │   ├─ 调 node.run(inputs, sample_params)
    │    │   └─ 把 outputs pickle 到 stdout
    │    │
    │    ├─ 主进程读 stdout pickle → outputs dict
    │    │
    │    └─ 收集资源用量 (duration / mem_peak via psutil if available)
    │
    ├─ 写 test_run.log + 更新 status
    │
    └─ 返回结果
```

**关键决策**:
- **复用 SubprocessSandbox 框架**, 不引入新依赖
- **RestrictedPython 作为 defense-in-depth**, 但不作为唯一防线
- **setrlimit** 防止 CPU / 内存炸弹
- **subprocess wall-clock timeout** 防止死循环 (60s)
- **pickle 传输代码** (不是传输执行结果), 但代码本身要先通过 AST 黑名单

---

## 5. 关键决策总结 (再次确认)

| # | 决策 | 推荐方案 |
|---|---|---|
| D1 | 代码编辑器 | **Monaco Editor** (CDN 加载, ~1.7MB) |
| D2 | 代码存储 | **PostgreSQL TEXT** (不引入 SQLite/文件) |
| D3 | 沙箱安全 | **Subprocess + setrlimit + RestrictedPython 黑名单** (不做 Docker 隔离, v1 够用) |
| D4 | 节点覆盖 | **租户自定义 > 系统节点** (DB 层 unique constraint per tenant) |
| D5 | 删除语义 | 系统节点 enabled=false, 自定义节点 SoftDeleteMixin (已有) |
| D6 | 版本管理 | 完整 CustomNodeVersion 表 + 回滚 API |
| D7 | Contract 检测 | **AST 静态 + 试运行反推** 双轨 |
| D8 | RBAC | super_admin / tenant_admin / analyst 三档 |
| D9 | 资源限制 | 内存 2Gi / 超时 60s / CPU 1 核 (可按租户配置) |
| D10 | 文档位置 | `docs/node-plugin/` (新增目录) |
| D11 | 数据库迁移 | **沿用 PostgreSQL** (不引入 SQLite) |
| D12 | 草稿机制 | **新建 `node_definition_drafts` 表** (避免版本历史膨胀) |
| D13 | 编辑锁 | **新建 `node_definition_locks` 表** (TTL + 心跳) |

---

## 6. 文件清单

### 后端 (新增/修改)

```
backend/hscredit_studio/
├── alembic/versions/
│   └── 0015_node_plugin.py                      # 扩展字段 (新表 + ALTER)
├── schemas/
│   ├── custom_node.py                            # 新增: CustomNode CRUD schemas
│   └── node_contract.py                          # 扩展 (允许 partial validate)
├── services/
│   ├── custom_nodes.py                           # 新增: CRUD service
│   ├── ast_analyzer.py                           # 新增: AST 静态分析
│   └── node_loader.py                            # 新增: DB → NodeRegistry 加载
├── api/v1/
│   ├── nodes.py                                  # 扩展: 启停/meta/sync/详情
│   └── custom_nodes.py                           # 新增: 完整 CRUD + test/validate/detect
├── executor/
│   └── _user_sandbox_worker.py                   # 新增: 用户代码沙箱 worker
├── models/
│   └── node.py                                   # 扩展 (已有 CustomNode/Version/TestRun)
└── nodes/
    └── loader.py                                 # 新增: 运行时加载 custom 节点到 Registry
```

### 前端 (新增/修改)

```
frontend/src/
├── api/
│   ├── nodes.ts                                  # 扩展: enable/disable/update/sync
│   └── custom-nodes.ts                           # 新增: CRUD + validate/detect/test
├── types/
│   └── index.ts                                  # 扩展: CustomNode/CustomNodeVersion types
├── pages/
│   └── nodes/
│       ├── List.tsx                              # 节点管理主页
│       ├── New.tsx                               # 新增向导
│       ├── Edit.tsx                              # 编辑页 (Monaco)
│       ├── Detail.tsx                            # 详情页 (只读)
│       └── components/
│           ├── NodeTable.tsx                     # 表格
│           ├── MetaEditModal.tsx                 # 元数据编辑
│           ├── CodeEditor.tsx                    # Monaco 包装
│           ├── ContractPreview.tsx               # contract 实时预览
│           ├── TestRunPanel.tsx                  # 试运行面板
│           └── NewNodeWizard.tsx                 # 新增向导
├── components/
│   └── Auth/
│       └── RequireRole.tsx                       # RBAC 守卫
├── hooks/
│   └── useDraftAutosave.ts                       # 自动保存草稿 hook
├── router.tsx                                    # 注册 /nodes 路由
└── components/Layout/Sidebar.tsx                 # 加菜单
```

### 文档 (新增)

```
docs/node-plugin/
├── 00_DECISIONS_PENDING.md          # 待决策项
├── 01_DESIGN.md                      # 本文档
├── 02_IMPLEMENTATION.md              # 实施追踪
├── 03_TESTING.md                     # 测试文档
├── 04_VERIFICATION.md                # 验收文档
└── 05_OPERATIONS.md                  # 运维文档
```
