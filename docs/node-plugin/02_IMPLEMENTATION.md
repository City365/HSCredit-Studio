# 节点可插拔改造 — 实施追踪清单

> 本文档按阶段记录每一步的实施细节、问题、决策.
> 每完成一步, 在末尾追加 commit hash 和实际遇到的问题.

---

## 📌 关键决策 (调研后确认)

| 决策项 | 方案 | 调研依据 |
|---|---|---|
| 代码编辑器 | **Monaco Editor** (CDN 加载) | 业界主流 (Mage.ai / n8n / Streamlit 都在用), Pyodide LSP 后续可加 |
| 代码存储 | **PostgreSQL TEXT** (TOAST) | 业界研究: < 1MB 代码用 PG TEXT + TOAST 完全够用 |
| 沙箱安全 | **Subprocess + setrlimit + AST 黑名单** (不引入 Docker/Firecracker) | 调研: RestrictedPython 单独不够, 必须加 OS 层防御; v1 用 subprocess 兜底 |
| Contract 检测 | **AST 静态 + 试运行反推** 混合 | Mage 风格: 代码 + 实时预览; Prefect 用类型注解 |
| 编辑锁 | **DB 表 + TTL + 心跳** | 不引入 Redis 分布式锁 (减少依赖) |
| 版本管理 | **DB 表 + 内容哈希** | 业界主流 (Prefect / Mage / n8n 都用 git-SHA 或类似) |

**注**: 用户决策 D1-D13 已写入 `00_DECISIONS_PENDING.md`, 本计划采纳所有默认推荐, 用户可在审批时调整.

---

## 总览

| 阶段 | 内容 | 计划工期 | 实际工期 | 状态 | commit |
|------|------|----------|----------|------|--------|
| 0    | DB 迁移 + 基础工具 | 0.5d | - | ⏳ | - |
| 1    | 后端: 系统节点启停 API | 0.5d | - | ⏳ | - |
| 2    | 后端: 自定义节点 CRUD + 版本 + 软删除 + 锁 | 2.5d | - | ⏳ | - |
| 3    | 后端: AST 校验 + 沙箱执行 + Contract 反推 | 3d | - | ⏳ | - |
| 4    | 后端: NodeRegistry 合并视图 + Celery pub/sub | 1d | - | ⏳ | - |
| 5    | 前端: API 客户端 + 类型 | 0.5d | - | ⏳ | - |
| 6    | 前端: 节点列表页面 (/nodes) | 2d | - | ⏳ | - |
| 7    | 前端: 代码编辑器页 (/nodes/:id/edit) | 3d | - | ⏳ | - |
| 8    | 前端: 新增节点向导 + 详情页 | 2d | - | ⏳ | - |
| 9    | 前端: 路由 + 侧边栏 + RBAC | 0.5d | - | ⏳ | - |
| 10   | 端到端测试 + 文档收尾 | 1d | - | ⏳ | - |
| **总计** | | **~16.5d** | - | | |

---

## 阶段 0 — DB 迁移 + 基础工具 (0.5d)

### 任务清单

#### 0.1 创建 alembic migration (1h)
- [ ] 创建 `0015_node_plugin.py`
- [ ] ALTER TABLE node_definitions 加 4 字段
- [ ] ALTER TABLE custom_nodes 加 7 字段
- [ ] CREATE TABLE node_definition_drafts (含 unique 约束)
- [ ] CREATE TABLE node_definition_locks (含 unique 约束)
- [ ] 4 个新索引
- [ ] 测试 upgrade / downgrade

**文件**: `backend/hscredit_studio/alembic/versions/0015_node_plugin.py`

#### 0.2 同步 SQLAlchemy 模型 (0.5h)
- [ ] `models/node.py` 添加新字段定义
- [ ] 添加 NodeDefinitionDraft 模型
- [ ] 添加 NodeDefinitionLock 模型
- [ ] 更新 `models/__init__.py` 导出

#### 0.3 创建通用工具模块 (1h)
- [ ] `services/ast_analyzer.py` - AST 静态分析核心 (300 行)
- [ ] `services/contract_inference.py` - Contract 反推 (200 行)
- [ ] `nodes/loader.py` - DB → NodeRegistry 加载器
- [ ] `executor/_user_sandbox_worker.py` - 用户代码沙箱 worker (200 行)

#### 0.4 添加依赖 (0.5h)
- [ ] pyproject.toml: 加 `RestrictedPython>=6.0` (optional [plugin] extra)

### 验收
- [ ] alembic upgrade head 成功
- [ ] 数据库无破坏 (76 系统节点 + 已有 custom_nodes)
- [ ] SQLAlchemy 模型可正常 import

### 实际遇到的问题 / 决策

_(实施时填写)_

---

## 阶段 1 — 系统节点启停 API (0.5d)

### 任务清单

#### 1.1 新增 schemas/node.py (0.5h)
- [ ] `NodeMetaUpdateRequest` schema
- [ ] `SyncResponse` schema

#### 1.2 扩展 api/v1/nodes.py (1h)
- [ ] PUT /enable
- [ ] PUT /disable
- [ ] PUT /meta
- [ ] POST /sync (super_admin only)
- [ ] GET /{node_type} 单节点详情

#### 1.3 RBAC 守卫 (0.5h)
- [ ] super_admin 检查 (PUT enable/disable/meta/sync)
- [ ] 审计日志记录 (Phase 5 B25)

#### 1.4 OpenAPI 文档更新 (0.5h)
- [ ] 新端点 docstring
- [ ] 测试 /api/docs 反映

### 验收
- [ ] 所有端点 HTTP 200/403 正确
- [ ] 启停无需重启后端
- [ ] 前端拉取看到正确 enabled 状态

### 实际遇到的问题 / 决策

_(实施时填写)_

---

## 阶段 2 — 自定义节点 CRUD (2.5d)

### 任务清单

#### 2.1 创建 schemas/custom_node.py (2h)
- [ ] `CustomNodeCreateRequest`
- [ ] `CustomNodeUpdateMetaRequest`
- [ ] `CustomNodeUpdateCodeRequest`
- [ ] `CustomNodeResponse`
- [ ] `CustomNodeVersionResponse`
- [ ] `CustomNodeListResponse` (含分页)
- [ ] `CustomNodeDraftResponse`
- [ ] `LockResponse`

#### 2.2 创建 services/custom_nodes.py (8h)
- [ ] `CustomNodeService.create()` - 创建节点 + v1 版本
- [ ] `CustomNodeService.list()` - 列表 (含可见性过滤)
- [ ] `CustomNodeService.get()` - 详情
- [ ] `CustomNodeService.update_meta()` - 改 name/desc/icon/enabled
- [ ] `CustomNodeService.update_code()` - 提交新版本 (创建 version 记录)
- [ ] `CustomNodeService.list_versions()` - 版本列表
- [ ] `CustomNodeService.rollback()` - 回滚
- [ ] `CustomNodeService.soft_delete()` - 软删除
- [ ] `CustomNodeService.get_draft()` / `save_draft()` / `discard_draft()`
- [ ] `CustomNodeService.acquire_lock()` / `release_lock()` / `heartbeat()`
- [ ] 事务管理 (异常回滚)
- [ ] 错误处理 (E_VALIDATION_ERROR / E_NODE_TYPE_CONFLICT / E_NODE_LOCKED)

#### 2.3 创建 api/v1/custom_nodes.py (4h)
- [ ] 10+ 端点注册
- [ ] 租户隔离 (TenantDep)
- [ ] RBAC (require_role)
- [ ] 注册到 `api/v1/__init__.py`

#### 2.4 测试 (2h)
- [ ] 单元测试: 10 个 service 方法
- [ ] 集成测试: 端到端 CRUD 流程

### 验收
- [ ] CRUD 全部 HTTP 200/201/204
- [ ] 软删除生效
- [ ] 版本管理 + 回滚
- [ ] 租户隔离
- [ ] RBAC 正确

### 实际遇到的问题 / 决策

_(实施时填写)_

---

## 阶段 3 — 沙箱 + 校验 + Contract 反推 (3d)

### 任务清单

#### 3.1 AST 静态分析 (4h)
- [ ] `services/ast_analyzer.py`:
  - [ ] `parse_user_code(code)` → AST tree
  - [ ] `validate_basics(tree)` - 检查类继承 / contract / run 方法
  - [ ] `validate_imports(tree)` - 黑名单 (os/subprocess/socket/ctypes/pickle/...)
  - [ ] `validate_builtins(tree)` - 扫描 eval/exec/__import__/open 调用
  - [ ] `validate_dunder_access(tree)` - 拦截 `__xxx__` 属性
  - [ ] 返回 `ValidationResult { valid, issues, ast_preview }`
- [ ] 单元测试: 20+ 测试用例 (覆盖所有 rule)

#### 3.2 RestrictedPython 集成 (3h)
- [ ] `_user_sandbox_worker.py`:
  - [ ] `compile_restricted(user_code)` 编译
  - [ ] exec 到受限命名空间
  - [ ] 查找 BaseNode 子类
  - [ ] 实例化 + 调 run()
  - [ ] 把 outputs pickle 到 stdout
- [ ] 失败捕获 (HSCreditWorkflowError / MemoryError / Exception)
- [ ] 测试: 合法 + 非法代码各 5 例

#### 3.3 Subprocess 沙箱执行 (4h)
- [ ] `services/user_sandbox.py` (新文件):
  - [ ] `UserSandbox.execute(code, inputs, params, contract)` 方法
  - [ ] 生成 payload.pkl (含 code/inputs/params/contract)
  - [ ] `subprocess.run([python, -I -B, _user_sandbox_worker.py, payload.pkl])`
  - [ ] `preexec_fn=setrlimit(...)`: CPU/AS/FSIZE/NOFILE/NPROC
  - [ ] timeout=`USER_SANDBOX_TIMEOUT_SEC`
  - [ ] 资源用量收集 (duration / cpu / mem_peak_mb)
  - [ ] 异常分类: Timeout / OOM / Other
  - [ ] 临时文件清理
- [ ] 测试: 死循环 → Timeout, 大数组 → OOM

#### 3.4 POST /test 端点 (3h)
- [ ] 解析 sample_data (CSV / JSON)
- [ ] 写入 custom_node_test_runs (status=queued)
- [ ] 调 UserSandbox.execute
- [ ] 更新 test_run 记录 (status / log / resource_usage)
- [ ] 返回结果
- [ ] 频率限制 (每租户每分钟 10 次)

#### 3.5 POST /validate 端点 (2h)
- [ ] 调 AST 分析器
- [ ] 返回 valid + issues + ast_preview

#### 3.6 POST /detect-contract 端点 (3h)
- [ ] `services/contract_inference.py`:
  - [ ] AST 推断: input ports (从 `inputs["xxx"]`)、output ports (从 return dict)、param names (从 kwargs)
  - [ ] 试运行反推: output keys + 启发式 types (DataFrame / Series / 其他 → "object")
  - [ ] 合并 AST + 试运行结果
  - [ ] 返回 draft_contract + ast_inferred + runtime_inferred + warnings

#### 3.7 测试 (3h)
- [ ] 静态校验 16 测试用例 (见 04_VERIFICATION.md 3.1)
- [ ] 沙箱执行 10 测试用例
- [ ] Contract 反推 7 测试用例
- [ ] 性能测试 (校验 < 200ms / 反推 < 1s)

### 验收
- [ ] 静态校验拦截所有黑名单
- [ ] 沙箱执行正确 (success / timeout / oom 都能分类)
- [ ] Contract 反推合理

### 实际遇到的问题 / 决策

_(实施时填写)_

---

## 阶段 4 — NodeRegistry 合并视图 + Celery 同步 (1d)

### 任务清单

#### 4.1 CustomNodeLoader 服务 (3h)
- [ ] `services/custom_nodes.py` 加 `load_to_registry(custom_node_id)`
- [ ] 编译 user_code → BaseNode 子类
- [ ] `NodeRegistry.register(cls)`
- [ ] 异常处理 (编译失败不污染 registry)

#### 4.2 启动加载 (1h)
- [ ] `main.py` lifespan 启动后, 遍历 enabled custom_nodes, 加载到 Registry

#### 4.3 更新时同步 (2h)
- [ ] 提交新版本后: `NodeRegistry.unregister(old_type)` + `register(new_cls)`
- [ ] Redis pub/sub: `node:reload` 频道发布 (含 node_type + version)
- [ ] 所有 Celery worker 订阅, 收到后 reload

#### 4.4 测试 (2h)
- [ ] 启动加载: 自定义节点出现在 `list_contracts()`
- [ ] 更新同步: A worker 更新, B worker 能拿到新版本
- [ ] 隔离: 租户 A 自定义节点不影响 B

### 验收
- [ ] 自定义节点在工作流编辑器可见
- [ ] 自定义节点能成功 Run
- [ ] 多 worker 同步生效

### 实际遇到的问题 / 决策

_(实施时填写)_

---

## 阶段 5 — 前端 API 客户端 (0.5d)

### 任务清单

#### 5.1 TypeScript 类型 (1h)
- [ ] `types/index.ts` 加 CustomNode / CustomNodeVersion / Lock / Draft / TestRun 类型
- [ ] ParamSpec 补 `workflow_scoped` (已有, 确认)
- [ ] PortSchema 补 `aliases` 字段

#### 5.2 API client (2h)
- [ ] `api/custom-nodes.ts`:
  - [ ] list / get / create / update / delete
  - [ ] updateCode / listVersions / getVersion / rollback
  - [ ] getDraft / saveDraft / discardDraft
  - [ ] acquireLock / releaseLock / heartbeatLock
  - [ ] validate / detectContract / test / listTestRuns
- [ ] 扩展 `api/nodes.ts`: enable / disable / updateMeta / sync

#### 5.3 类型检查 (0.5h)
- [ ] `npm run type-check` 通过

### 验收
- [ ] TypeScript 编译通过
- [ ] 类型完整

### 实际遇到的问题 / 决策

_(实施时填写)_

---

## 阶段 6 — 节点列表页面 /nodes (2d)

### 任务清单

#### 6.1 路由 + 页面骨架 (1h)
- [ ] `pages/nodes/List.tsx` - 基础布局
- [ ] Table + 搜索框 + 过滤下拉
- [ ] 顶部按钮 (同步系统节点 + 新增)

#### 6.2 NodeTable 组件 (4h)
- [ ] 列定义 (节点类型/名称/分类/来源/状态/操作)
- [ ] 来源 Tag 区分 (系统/自定义)
- [ ] 启停 Switch (RBAC 控制)
- [ ] 行内操作菜单 ("...")

#### 6.3 操作菜单实现 (4h)
- [ ] 查看详情抽屉 → contract JSON
- [ ] 编辑元数据 Modal → PUT /meta
- [ ] 编辑代码 → 跳转 /nodes/:id/edit
- [ ] 试运行 → 跳转 /nodes/:id/test (或 Modal)
- [ ] 删除确认弹窗 → DELETE

#### 6.4 过滤 + 搜索 + 分页 (3h)
- [ ] 搜索 (按 name/description/node_type)
- [ ] 分类过滤 (下拉)
- [ ] 来源过滤
- [ ] 状态过滤
- [ ] 分页 (前/后/跳转)

#### 6.5 RBAC 集成 (1h)
- [ ] 按钮级 RBAC (useAuthStore.role)
- [ ] 后端二次校验

#### 6.6 同步系统节点按钮 (1h)
- [ ] 仅 super_admin 可见
- [ ] 点击 → 弹确认 → POST /sync → 刷新表格

#### 6.7 响应式 + 加载状态 (2h)
- [ ] loading spinner
- [ ] empty illustration
- [ ] 1280 / 1024 / 768 px 三档测试

### 验收
- [ ] 全部 T-UI-001 测试用例通过

### 实际遇到的问题 / 决策

_(实施时填写)_

---

## 阶段 7 — 代码编辑器页 /nodes/:id/edit (3d)

### 任务清单

#### 7.1 Monaco 集成 (3h)
- [ ] 安装 `@monaco-editor/react` (npm install)
- [ ] `components/CodeEditor/index.tsx` 通用组件
- [ ] 配置 Python 语言 + dark theme
- [ ] 配置 minimap / fontSize / lineNumbers

#### 7.2 页面骨架 (2h)
- [ ] `pages/nodes/Edit.tsx` 左右分栏
- [ ] 顶部: 节点名 + 版本下拉 + 启停 + 保存版本 + 试运行
- [ ] 底部: 状态条 (试运行次数 / 最近保存)

#### 7.3 实时 contract 预览 (4h)
- [ ] `components/ContractPreview.tsx`
- [ ] 防抖 800ms 调 /detect-contract
- [ ] 显示 inputs / outputs / params
- [ ] 输入端口/输出端口可视化

#### 7.4 实时校验 (3h)
- [ ] 防抖 500ms 调 /validate
- [ ] Monaco markers API 显示 squiggle
- [ ] 悬停看 issue 详情

#### 7.5 自动保存草稿 (2h)
- [ ] `hooks/useDraftAutosave.ts`
- [ ] 5s 无输入触发 PUT /draft
- [ ] 静默调用 (不弹 toast)

#### 7.6 编辑锁 (3h)
- [ ] 进入页面 → POST /lock
- [ ] 心跳 2min → POST /lock/heartbeat
- [ ] 关闭页面 → navigator.sendBeacon DELETE /lock
- [ ] 他人占用 → 显示只读模式 + 提示

#### 7.7 版本切换 + 回滚 (3h)
- [ ] 顶部版本下拉
- [ ] 切换时 GET /versions/{vid}
- [ ] Monaco 显示该版本 code (只读)
- [ ] "回滚到此版本" 按钮

#### 7.8 保存版本 (2h)
- [ ] Modal 输入 change_summary
- [ ] 调 PUT /custom-nodes/{id}/code
- [ ] 成功 → 提示 + 刷新版本列表

#### 7.9 测试运行面板 (3h)
- [ ] `components/TestRunPanel.tsx`
- [ ] Modal 弹出
- [ ] 输入 sample_inputs (DataFrame 列定义) + sample_params
- [ ] 调 POST /test
- [ ] 显示 outputs / logs / resource_usage
- [ ] "复制为版本" 按钮

#### 7.10 主题适配 (1h)
- [ ] 亮/暗主题切换
- [ ] Monaco theme 跟随

### 验收
- [ ] 全部 T-UI-003 测试用例通过

### 实际遇到的问题 / 决策

_(实施时填写)_

---

## 阶段 8 — 新增节点向导 + 详情页 (2d)

### 任务清单

#### 8.1 Stepper 框架 (2h)
- [ ] `pages/nodes/New.tsx` 5 步 wizard
- [ ] Ant Design Steps 组件
- [ ] 步骤间导航

#### 8.2 Step 1: 起点选择 (1h)
- [ ] 三个 radio 选项
- [ ] 复制模式加载 contract 模板

#### 8.3 Step 2: 基础信息 (2h)
- [ ] node_type 输入 (实时校验唯一性)
- [ ] category 下拉
- [ ] name / icon / visibility 字段

#### 8.4 Step 3: 代码编辑 (2h)
- [ ] Monaco + 模板代码
- [ ] 实时校验状态显示

#### 8.5 Step 4: 测试样本 + 试运行 (3h)
- [ ] 上传 CSV / 粘贴 JSON
- [ ] 自动识别列名
- [ ] 试运行按钮
- [ ] 显示 outputs

#### 8.6 Step 5: 确认 (1h)
- [ ] 摘要显示所有信息
- [ ] 调 POST /custom-nodes
- [ ] 跳转 /nodes/:id/edit

#### 8.7 详情页 (3h)
- [ ] `pages/nodes/Detail.tsx` 只读
- [ ] 显示完整 contract + versions 列表
- [ ] "编辑代码" / "试运行" / "删除" 按钮

### 验收
- [ ] T-UI-002 全部通过
- [ ] T-UI-004 (详情页) 全部通过

### 实际遇到的问题 / 决策

_(实施时填写)_

---

## 阶段 9 — 路由 + 侧边栏 + RBAC (0.5d)

### 任务清单

#### 9.1 router.tsx (0.5h)
- [ ] 注册 /nodes, /nodes/new, /nodes/:id/edit, /nodes/:id
- [ ] 用 React.lazy 懒加载

#### 9.2 RequireRole 守卫 (1h)
- [ ] `components/Auth/RequireRole.tsx`
- [ ] 检查 authStore.role
- [ ] 不通过 → 重定向 /403

#### 9.3 Sidebar.tsx (1h)
- [ ] "节点管理" 菜单项 (admin)
- [ ] 图标: CodeOutlined / ApiOutlined

#### 9.4 面包屑 (1h)
- [ ] 各页面顶部面包屑 (返回上级)

#### 9.5 权限矩阵测试 (1h)
- [ ] super_admin: 全功能
- [ ] tenant_admin: 本租户管理
- [ ] analyst: 只读
- [ ] viewer: 只读

### 验收
- [ ] 全部菜单/路由按角色显隐
- [ ] 直接 URL 访问也受守卫

### 实际遇到的问题 / 决策

_(实施时填写)_

---

## 阶段 10 — 端到端测试 + 文档收尾 (1d)

### 任务清单

#### 10.1 E2E 测试脚本 (3h)
- [ ] T-E2E-001: 完整生命周期 (创建→试用→保存→workflow 使用→Run→编辑→回滚→删除)
- [ ] T-E2E-002: 多租户隔离
- [ ] T-E2E-003: RBAC
- [ ] T-E2E-004: 沙箱安全
- [ ] T-E2E-005: 性能 (列表 < 1s / 试运行 < 10s / 冷启动 < 5s)

#### 10.2 文档收尾 (2h)
- [ ] 检查 5 份文档完整性
- [ ] OpenAPI 截图
- [ ] 更新 ROADMAP.md

#### 10.3 演示视频 / GIF (2h)
- [ ] 录一段演示创建+试运行+workflow 使用的 GIF
- [ ] 嵌入 docs/node-plugin/README.md

### 验收
- [ ] 5 个 E2E 全部通过
- [ ] 5 份文档完整

### 实际遇到的问题 / 决策

_(实施时填写)_

---

## 实施过程遇到的问题与决策 (汇总)

| 日期 | 阶段 | 问题 | 决策 | commit |
|------|------|------|------|--------|
| _(填)_ | _(填)_ | _(填)_ | _(填)_ | _(填)_ |

---

## 进度跟踪 (Git commit 时间线)

```
git log --oneline | grep -E "node.plugin|node_plugin"
```

| commit | 阶段 | 内容 |
|---|---|---|
| _(填)_ | 0 | DB 迁移 |
| ... | ... | ... |
