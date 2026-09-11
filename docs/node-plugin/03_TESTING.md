# 节点可插拔改造 — 测试文档

> 本文档定义每个阶段的测试用例, 包含:
> - 测试目的
> - 前置条件
> - 操作步骤 (含 demo)
> - 预期结果
> - 实际结果 (执行时填写)
> - 通过/失败

---

## 测试总览

| 编号 | 测试类别 | 用例数 | 通过率要求 |
|------|----------|--------|-----------|
| T-API | 后端 API 测试 | 30+ | 100% |
| T-UI  | 前端页面测试 | 20+ | 100% |
| T-E2E | 端到端测试 | 5+  | 100% |
| T-SEC | 安全测试 | 5+ | 100% |

---

# 一、后端 API 测试 (T-API)

## 阶段 0 — DB 迁移

### T-API-001: alembic upgrade head 成功
- **前置**: 数据库连接正常
- **步骤**: `cd backend && ./.venv/Scripts/python.exe -m alembic upgrade head`
- **预期**: 退出码 0, 无错误
- **实际**: _(执行时填写)_

### T-API-002: node_definitions 新字段存在
- **前置**: T-API-001 通过
- **步骤**: `psql -c "\d node_definitions"` 或 SQL 查询
- **预期**: is_custom / owner_tenant_id / source / icon / updated_at 字段存在
- **实际**: _(执行时填写)_

### T-API-003: 现有 76 个系统节点无破坏
- **前置**: T-API-001 通过
- **步骤**: `SELECT COUNT(*) FROM node_definitions WHERE is_custom = FALSE`
- **预期**: 返回 76 (或当前系统节点数)
- **实际**: _(执行时填写)_

---

## 阶段 1 — 系统节点启停 API

### T-API-010: 启用节点
- **前置**: super_admin token
- **步骤**:
  ```bash
  curl -X PUT http://localhost:8003/api/v1/node-definitions/xgboost/enable \
    -H "Authorization: Bearer $TOKEN"
  ```
- **预期**: HTTP 200, 返回 `{"node_type": "xgboost", "enabled": true}`
- **实际**: _(执行时填写)_

### T-API-011: 禁用节点
- **步骤**:
  ```bash
  curl -X PUT http://localhost:8003/api/v1/node-definitions/xgboost/disable \
    -H "Authorization: Bearer $TOKEN"
  ```
- **预期**: HTTP 200, 返回 `{"node_type": "xgboost", "enabled": false}`
- **实际**: _(执行时填写)_

### T-API-012: 禁用后 GET 列表不返回
- **步骤**:
  ```bash
  curl "http://localhost:8003/api/v1/node-definitions?enabled_only=true" \
    -H "Authorization: Bearer $TOKEN" | jq '.definitions[].node_type' | grep xgboost
  ```
- **预期**: 无输出 (xgboost 不在 enabled_only=true 列表)
- **实际**: _(执行时填写)_

### T-API-013: 禁用后再启用, 列表恢复
- **步骤**: 调用 enable, 再查 enabled_only=true 列表
- **预期**: xgboost 重新出现
- **实际**: _(执行时填写)_

### T-API-014: 修改元数据 (name/desc/icon)
- **步骤**:
  ```bash
  curl -X PUT http://localhost:8003/api/v1/node-definitions/xgboost/meta \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name":"XGBoost训练(自定义名)","description":"测试描述","icon":"🚀"}'
  ```
- **预期**: HTTP 200, 数据库对应字段更新
- **实际**: _(执行时填写)_

### T-API-015: 非 super_admin 调用启用接口返回 403
- **步骤**: 用 analyst token 调用 enable 接口
- **预期**: HTTP 403
- **实际**: _(执行时填写)_

---

## 阶段 2 — 自定义节点 CRUD

### T-API-020: 创建自定义节点
- **前置**: tenant_admin token
- **步骤**:
  ```bash
  curl -X POST http://localhost:8003/api/v1/custom-nodes \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "node_type": "my_filter_v1",
      "name": "我的过滤器",
      "category": "特征工程",
      "description": "过滤掉 score < 0.5 的样本",
      "code": "from hscredit_studio.nodes.base import BaseNode\nfrom hscredit_studio.schemas.node_contract import NodeContract, ParamSpec, PortSchema\n\nclass MyFilterNode(BaseNode):\n    contract = NodeContract(\n        node_type=\"my_filter_v1\",\n        category=\"特征工程\",\n        name=\"我的过滤器\",\n        inputs=[PortSchema(name=\"df\", type=\"DataFrame\", required=True)],\n        outputs=[PortSchema(name=\"filtered_df\", type=\"DataFrame\")],\n        params=[ParamSpec(name=\"threshold\", type=\"float\", default=0.5)],\n    )\n    def run(self, inputs, params):\n        df = inputs[\"df\"]\n        threshold = params[\"threshold\"]\n        return {\"filtered_df\": df[df[\"score\"] >= threshold]}\n",
      "visibility": "private"
    }'
  ```
- **预期**: HTTP 201, 返回 custom_node_id
- **实际**: _(执行时填写)_

### T-API-021: 列出自定义节点
- **步骤**: `curl http://localhost:8003/api/v1/custom-nodes`
- **预期**: 返回刚创建的节点
- **实际**: _(执行时填写)_

### T-API-022: 获取节点详情
- **步骤**: `curl /custom-nodes/{id}`
- **预期**: 返回完整 code + contract
- **实际**: _(执行时填写)_

### T-API-023: 提交新版本 (code)
- **步骤**:
  ```bash
  curl -X PUT /custom-nodes/{id}/code \
    -H "..." \
    -d '{"code": "<修改后的代码>", "change_summary": "增加 column 参数"}'
  ```
- **预期**: HTTP 200, CustomNodeVersion 表新增 v2
- **实际**: _(执行时填写)_

### T-API-024: 列出版本
- **步骤**: `curl /custom-nodes/{id}/versions`
- **预期**: 返回 [v1, v2] 列表
- **实际**: _(执行时填写)_

### T-API-025: 回滚到 v1
- **步骤**: `curl -X POST /custom-nodes/{id}/versions/v1/rollback`
- **预期**: HTTP 200, custom_nodes.code 变成 v1 的代码
- **实际**: _(执行时填写)_

### T-API-026: 更新元数据
- **步骤**: PUT /custom-nodes/{id} 修改 name/icon/enabled
- **预期**: HTTP 200, 数据库更新
- **实际**: _(执行时填写)_

### T-API-027: 软删除
- **步骤**: DELETE /custom-nodes/{id}
- **预期**: HTTP 204, GET 列表不再返回, 但 DB 记录在 (含 deleted_at)
- **实际**: _(执行时填写)_

### T-API-028: analyst 不能创建
- **步骤**: 用 analyst token POST
- **预期**: HTTP 403
- **实际**: _(执行时填写)_

### T-API-029: 跨租户隔离 (A 创建的 B 看不到)
- **前置**: 两个租户各自的 token
- **步骤**: 租户 A 创建 → 租户 B 列表 → 不应返回
- **预期**: HTTP 200, 但列表为空
- **实际**: _(执行时填写)_

### T-API-030: node_type 与系统节点重名 → 覆盖生效
- **步骤**: 创建 node_type="xgboost" 的自定义节点
- **预期**: HTTP 201, 工作流编辑器使用 xgboost 时实际执行自定义版本
- **实际**: _(执行时填写)_

---

## 阶段 3 — 用户代码沙箱执行

### T-API-040: 静态校验通过 (合法代码)
- **前置**: 自定义节点已创建
- **步骤**: `POST /custom-nodes/{id}/validate`
- **预期**: HTTP 200, `{"valid": true, "issues": []}`
- **实际**: _(执行时填写)_

### T-API-041: 静态校验拦截 (import os)
- **步骤**: code 含 `import os`
- **预期**: HTTP 200, `{"valid": false, "issues": [{"line": 1, "msg": "禁止 import os"}]}`
- **实际**: _(执行时填写)_

### T-API-042: 静态校验拦截 (未继承 BaseNode)
- **步骤**: code 定义 `class Foo: pass`, 不继承 BaseNode
- **预期**: HTTP 200, valid=false, issues 含 "未继承 BaseNode"
- **实际**: _(执行时填写)_

### T-API-043: 静态校验拦截 (无 contract)
- **步骤**: code 类继承 BaseNode 但无 contract 变量
- **预期**: valid=false, issues 含 "未定义 contract"
- **实际**: _(执行时填写)_

### T-API-044: 静态校验拦截 (无 run 方法)
- **步骤**: code 类继承 BaseNode 有 contract 但无 run
- **预期**: valid=false, issues 含 "未实现 run()"
- **实际**: _(执行时填写)_

### T-API-045: 静态校验拦截 (eval/exec)
- **步骤**: code 含 `eval("1+1")`
- **预期**: valid=false, issues 含 "禁止使用 eval"
- **实际**: _(执行时填写)_

### T-API-046: 沙箱执行成功
- **前置**: 合法代码 + sample inputs
- **步骤**: `POST /custom-nodes/{id}/test` 含 sample_data
  ```json
  {
    "sample_inputs": {"df": <DataFrame 列定义>},
    "sample_params": {"threshold": 0.7},
    "sample_data": {
      "columns": ["score", "label"],
      "rows": [[0.9, 0], [0.3, 1], [0.8, 1]]
    }
  }
  ```
- **预期**: HTTP 200, `{"status": "success", "outputs": {...}, "duration_ms": <n>, "log": "..."}`
- **实际**: _(执行时填写)_

### T-API-047: 沙箱执行超时 (死循环)
- **步骤**: code 含 `while True: pass`
- **预期**: HTTP 200, status=failed, error 含 SANDBOX_TIMEOUT, duration ≈ 60s
- **实际**: _(执行时填写)_

### T-API-048: 沙箱执行内存超限
- **步骤**: code 创建大数组 > 2Gi
- **预期**: HTTP 200, status=failed, error 含 SANDBOX_OOM
- **实际**: _(执行时填写)_

### T-API-049: Contract 反推 (AST 推断)
- **步骤**: `POST /custom-nodes/{id}/detect-contract`
- **预期**: 返回 draft contract (含推断的 inputs/outputs/params)
- **实际**: _(执行时填写)_

---

## 阶段 4 — NodeRegistry 合并视图

### T-API-060: 自定义节点在工作流编辑器里可见
- **前置**: 自定义节点已创建, 启停启用
- **步骤**: 前端打开工作流编辑器, 节点库搜索 node_type
- **预期**: 出现在分类列表, 可拖入画布
- **实际**: _(执行时填写)_

### T-API-061: 自定义节点成功 Run
- **前置**: T-API-060 通过
- **步骤**: 提交 Run 工作流
- **预期**: 节点执行成功, 输出端口数据正确
- **实际**: _(执行时填写)_

### T-API-062: 租户隔离 (A 的自定义不影响 B)
- **前置**: 两个租户, 各自有同名自定义节点, 内容不同
- **步骤**: 租户 A 列表 vs 租户 B 列表
- **预期**: 各自只看到自己的
- **实际**: _(执行时填写)_

---

# 二、前端页面测试 (T-UI)

> 使用 preview 工具进行 UI 验证. 每个页面都要:
> 1. 截图首屏
> 2. 点击主要交互元素
> 3. 验证响应正确
> 4. 记录预期 vs 实际

## T-UI-001: 节点列表页面 (/nodes)

### 1. 进入页面
- **步骤**: 登录 → 左侧菜单点击"节点管理" → URL 跳到 /nodes
- **预期**: 显示节点表格, 列含: 节点类型/名称/分类/来源/状态/操作
- **实际**: _(截图 + 描述)_

### 2. 搜索功能
- **步骤**: 在搜索框输入 "xgboost"
- **预期**: 表格只显示 xgboost 节点
- **实际**: _(截图 + 描述)_

### 3. 分类过滤
- **步骤**: 分类下拉选"特征工程"
- **预期**: 表格只显示特征工程分类
- **实际**: _(截图 + 描述)_

### 4. 启停开关
- **步骤**: 点击某行的 Switch 关闭
- **预期**: 弹出确认 → 确认后 Switch 关闭, 刷新页面后保持关闭
- **实际**: _(截图 + 描述)_

### 5. 操作菜单
- **步骤**: 点击某行的 "..." 按钮
- **预期**: 下拉菜单含: 查看详情 / 编辑元数据 / 编辑代码(自定义) / 测试运行(自定义) / 删除(自定义)
- **实际**: _(截图 + 描述)_

### 6. 元数据编辑
- **步骤**: 操作菜单 → "编辑元数据" → 修改 name → 保存
- **预期**: 模态框关闭, 表格更新
- **实际**: _(截图 + 描述)_

### 7. 查看详情抽屉
- **步骤**: 操作菜单 → "查看详情"
- **预期**: 右侧抽屉显示 contract JSON
- **实际**: _(截图 + 描述)_

### 8. 删除自定义节点
- **步骤**: 操作菜单 → "删除" → 确认
- **预期**: 弹出确认 → 确认后表格移除该行, 后端软删除
- **实际**: _(截图 + 描述)_

### 9. 同步系统节点按钮
- **步骤**: 顶部"同步系统节点"按钮
- **预期**: 弹出确认 → 确认后从 NodeRegistry 重新同步, 表格刷新
- **实际**: _(截图 + 描述)_

---

## T-UI-002: 新增节点向导 (/nodes/new)

### 1. 进入向导
- **步骤**: 列表页 → 顶部"+新增"按钮 → URL /nodes/new
- **预期**: 显示向导第 1 步: 起点选择
- **实际**: _(截图)_

### 2. 选择"从空白创建"
- **步骤**: 单选"从空白创建" → 下一步
- **预期**: 进入第 2 步: 代码编辑
- **实际**: _(截图)_

### 3. 编辑代码 (Monaco)
- **步骤**: Monaco 编辑器显示 Python 模板代码, 包含 from imports 和 BaseNode 类骨架
- **预期**: 编辑器可输入, 语法高亮正确
- **实际**: _(截图)_

### 4. 输入测试样本
- **步骤**: 粘贴 CSV 数据或 JSON
- **预期**: 自动识别列名
- **实际**: _(截图)_

### 5. 试运行
- **步骤**: 点击"试运行"
- **预期**: 后端沙箱执行, 返回 outputs
- **实际**: _(截图 + 输出展示)_

### 6. 填元数据
- **步骤**: 输入 name/category/icon/visibility → 保存
- **预期**: 数据库新增 custom_node 记录
- **实际**: _(截图 + 描述)_

### 7. 保存后跳转
- **步骤**: 保存成功
- **预期**: 跳转到该节点的编辑页 /nodes/{id}/edit
- **实际**: _(截图)_

---

## T-UI-003: 节点编辑页 (/nodes/:id/edit)

### 1. Monaco 加载
- **步骤**: 进入编辑页
- **预期**: 异步加载 Monaco (~3s), 显示 Python 语法高亮
- **实际**: _(截图)_

### 2. Contract 实时预览
- **步骤**: 修改 code 中的 contract (改 name)
- **预期**: 右侧面板 name 实时更新
- **实际**: _(截图)_

### 3. 保存版本
- **步骤**: 修改 code → 填写 change_summary → 保存版本
- **预期**: 后端创建新 version, 页面提示"已保存 v3"
- **实际**: _(截图)_

### 4. 测试运行
- **步骤**: 点击"测试运行"按钮
- **预期**: 弹出测试运行面板, 后端沙箱执行, 显示 outputs
- **实际**: _(截图 + 输出)_

### 5. 版本切换 (下拉)
- **步骤**: 顶部版本下拉选 v1
- **预期**: Monaco 显示 v1 的代码, 可对比
- **实际**: _(截图)_

### 6. 回滚
- **步骤**: 在 v1 上点击"回滚到此版本"
- **预期**: 弹出确认 → 确认后 custom_nodes.code 变成 v1 内容
- **实际**: _(截图)_

### 7. 启停切换
- **步骤**: 顶部 Switch 关闭节点
- **预期**: 后端 enabled=false, 工作流编辑器不再显示该节点
- **实际**: _(截图)_

---

# 三、端到端测试 (T-E2E)

## T-E2E-001: 完整生命周期

### 场景
从零创建一个自定义节点, 在真实工作流中使用, 验证完整流程.

### 步骤

1. **创建**: tenant_admin 登录 → /nodes/new → 写一个"按分数过滤"的自定义节点 → 试运行通过 → 保存
2. **在工作流中使用**: 进入 /workflows/{id} → 节点库搜索 "my_filter" → 拖入画布 → 连线 → 设置参数 → 保存
3. **Run**: 点击"运行" → 观察节点执行 → 看到 outputs
4. **编辑**: /nodes/{id}/edit → 修改 code → 保存 v2 → 在工作流刷新 → 用 v2 执行
5. **回滚**: 编辑页切到 v1 → 回滚 → 在工作流验证用回 v1
6. **删除**: /nodes/{id} → 删除 → 在工作流看该节点变错误状态 (因为节点不可用)

### 验收
- [ ] 所有 6 步成功
- [ ] 数据库状态符合预期
- [ ] 工作流 Run 结果符合逻辑

---

## T-E2E-002: 多租户隔离

### 场景
租户 A 的自定义节点对租户 B 不可见.

### 步骤

1. 租户 A 创建自定义节点 "secret_node"
2. 切换到租户 B 登录
3. /nodes 列表 → 不应包含 secret_node
4. /workflows/{id} 节点库 → 不应包含 secret_node
5. 如果 B 尝试直接访问 /nodes/secret_node/edit → 403

### 验收
- [ ] 严格隔离, 没有任何泄露

---

## T-E2E-003: RBAC

### 场景
不同角色看到不同的操作能力.

### 步骤

1. analyst 登录 → /nodes → 看不到 "+新增" 按钮 → 操作菜单只有"查看详情"
2. tenant_admin 登录 → /nodes → 看到完整操作
3. super_admin 登录 → /nodes → 还能看到 "同步系统节点" 按钮

### 验收
- [ ] 权限边界正确

---

## T-E2E-004: 沙箱安全

### 场景
恶意代码不能执行.

### 步骤

1. 创建自定义节点, code 含 `import os; os.system("rm -rf /tmp/test")"`
2. 静态校验 → 应拦截, 不允许保存
3. 如果绕过静态校验 (手动改 DB), 试运行 → 沙箱应拦截或子进程被杀

### 验收
- [ ] 静态校验拦截
- [ ] 沙箱不能执行危险操作

---

## T-E2E-005: 性能

### 场景
- 自定义节点冷启动 < 5s
- 沙箱执行 < 10s (普通任务)
- 列表页加载 < 1s

### 步骤

1. 测冷启动时间
2. 测执行时间
3. 测列表加载时间 (用 Chrome DevTools)

### 验收
- [ ] 性能达标

---

# 四、安全测试 (T-SEC)

## T-SEC-001: import 黑名单
- **代码**: `import subprocess; subprocess.run(["ls"])`
- **预期**: 静态校验拦截

## T-SEC-002: 内置函数黑名单
- **代码**: `eval("1+1")`
- **预期**: 静态校验拦截

## T-SEC-003: 文件系统访问
- **代码**: `open("/etc/passwd")`
- **预期**: 静态校验拦截 (open 是危险 builtin)

## T-SEC-004: 网络访问
- **代码**: `import urllib.request; urllib.request.urlopen("http://evil.com")`
- **预期**: 静态校验拦截 (urllib 黑名单)

## T-SEC-005: 资源耗尽
- **代码**: 死循环
- **预期**: 沙箱超时 (60s) 终止

---

# 执行追踪

| 测试编号 | 执行时间 | 结果 | 备注 |
|----------|----------|------|------|
| T-API-001 | _(执行时填)_ | ⏳ | |
| ... | ... | ... | |

---

# 测试结果汇总

_(所有测试完成后填写)_

| 类别 | 通过 | 失败 | 通过率 |
|------|------|------|--------|
| T-API | ?/30 | ? | ?% |
| T-UI | ?/20 | ? | ?% |
| T-E2E | ?/5 | ? | ?% |
| T-SEC | ?/5 | ? | ?% |
| **总计** | **?/?** | **?** | **?%** |

验收门槛: 总体通过率 ≥ 95%, 每个类别 ≥ 90%
