# 节点可插拔改造 — 决策记录 (含用户审批)

> 本文档记录所有关键决策, 含推荐方案 + 用户审批状态.
> 用户审批后, 决策项状态从 "待定" → "已决".

---

## 决策汇总表

| ID | 主题 | 方案 | 状态 | 备注 |
|---|---|---|---|---|
| D1 | 代码编辑器 | Monaco Editor (CDN 加载) | ⏳ 待审批 | 调研推荐 |
| D2 | 代码存储 | PostgreSQL TEXT (TOAST) | ⏳ 待审批 | 不引入 SQLite |
| D3 | 沙箱安全 | Subprocess + setrlimit + AST 黑名单 | ⏳ 待审批 | v1 够用 |
| D4 | 节点覆盖 | 租户自定义 > 系统节点 | ⏳ 待审批 | 租户隔离 |
| D5 | 删除语义 | 系统 enabled=false / 自定义软删除 | ⏳ 待审批 | |
| D6 | 版本管理 | CustomNodeVersion + 回滚 API | ⏳ 待审批 | 已存在表 |
| D7 | Contract 检测 | AST 静态 + 试运行反推 | ⏳ 待审批 | Mage 风格 |
| D8 | RBAC | super_admin / tenant_admin / analyst | ⏳ 待审批 | 已有体系 |
| D9 | 资源限制 | 内存 2Gi / 超时 60s | ⏳ 待审批 | 可配置 |
| D10 | 文档位置 | docs/node-plugin/ | ⏳ 待审批 | |
| D11 | 数据库 | 沿用 PostgreSQL (不引入 SQLite) | ⏳ 待审批 | 调研决定 |
| D12 | 草稿机制 | 新建 node_definition_drafts 表 | ⏳ 待审批 | 避免版本膨胀 |
| D13 | 编辑锁 | 新建 node_definition_locks 表 | ⏳ 待审批 | TTL + 心跳 |
| D14 | 编辑器后端补全 | 先不做 (Phase 2) | ⏳ 待审批 | 调研建议: jedi/pylsp |
| D15 | 文件存储 | 不存 (代码全部 DB TEXT) | ⏳ 待审批 | |
| D16 | 试运行 UI 位置 | 弹窗 Modal (非独立页) | ⏳ 待审批 | 用户体验 |
| D17 | 代码同步 (多 worker) | Redis pub/sub | ⏳ 待审批 | 已有 Redis |
| D18 | sandbox 增强 | v1 不做 Docker, v2 再考虑 | ⏳ 待审批 | 渐进式 |

---

## 详细决策 (含调研依据 + 推荐 + 备选)

### D1. 代码编辑器: Monaco vs CodeMirror vs Ace

**调研依据**:
- **Mage.ai**: 用 Monaco (Notebook UI) — 行业参考
- **n8n**: 用 Monaco + AI completion
- **Node-RED**: 用 Ace (老旧)
- **业界报告**: Monaco bundle ~1.7MB (lazy), CodeMirror ~80KB core + ~200KB Python

**推荐方案**: **Monaco Editor (CDN 加载)**
- 优势: VS Code 同款, IntelliSense / syntax highlight / 多光标 / 查找替换 全
- 加载: `@monaco-editor/react` 默认 CDN 加载, 零 bundle cost
- 后续扩展: 可加 `monaco-languageclient` 接 pylsp 提供 Python IntelliSense

**备选方案**:
- A. CodeMirror 6: 轻量 ~80KB, 但 IntelliSense 弱
- B. Ace: 老旧, 弱 Python tokenizer, **不推荐**

**风险**:
- Monaco 加载慢 (CDN 网络), 加 `Suspense + lazy`
- 后续加 pylsp 需要独立 LSP server, 增加运维

**用户决策**: _(_待你确认_)_

---

### D2. 代码存储: PostgreSQL TEXT vs 文件 vs 对象存储

**调研依据**:
- Postgres TOAST: TEXT 字段 >2KB 自动压缩外置, 1GB 上限
- Prefect / Mage / n8n: 都把 workflow 定义存 JSON 在 DB

**推荐方案**: **PostgreSQL TEXT**
- 不引入 SQLite (避免多库)
- 不存文件 (避免路径管理 / git 同步)
- 已有 CustomNode.code 字段 (TEXT), 无需扩展
- 代码平均 < 50KB, 10000 个节点总占用 ~500MB (可接受)

**备选方案**:
- A. MinIO (对象存储): 大代码 (>500KB) 时迁移
- B. 文件系统: 调试场景可导出 (可选增强)

**用户决策**: _(_待你确认_)_

---

### D3. 沙箱安全: Subprocess + setrlimit + AST 黑名单 (v1)

**调研依据**:
- pysandbox (2015): 项目废弃, 作者明确说 "CPython sandbox 根本性坏了"
- RestrictedPython (Zope): 仅 AST 防御, 绕过示例 (pyjailbreaker)
- Replit / OpenAI Code Interpreter: Docker + gVisor
- Anthropic Artifacts: Firecracker
- 业界共识: **语言层沙箱不可信**, 必须加 OS 层防御

**推荐方案 (v1)**: **Subprocess + setrlimit + AST 黑名单 + RestrictedPython**
- Subprocess 隔离: 主进程不被影响
- setrlimit: CPU/AS/FSIZE/NOFILE/NPROC 限制
- AST 黑名单: `import os/subprocess/socket/pickle`, `eval/exec/open`
- RestrictedPython: defense-in-depth (可选)
- 没用 Docker (避免引入额外运维)

**升级路径 (v2)**:
- Docker 容器 + seccomp + AppArmor
- gVisor / Firecracker 微 VM

**风险**:
- v1 安全等级中等, 适合受信任租户 (付费用户)
- 不适合完全不可信场景 (公网爬虫等)

**用户决策**: _(_待你确认_)_

---

### D4. 节点覆盖: 租户自定义 > 系统节点

**调研依据**:
- Prefect: 用户可覆盖任务默认实现
- Mage: 用户 block 覆盖标准 block
- 业界惯例: 用户级覆盖系统级

**推荐方案**: **租户自定义覆盖系统节点**
- 租户 A 创建 `node_type="xgboost"` 的自定义节点 → A 的工作流用自定义版本
- 租户 B 不受影响, 仍用系统版本
- super_admin 可强制锁定 (避免覆盖)

**风险**:
- 用户期望与实际行为不符 → 文档清楚说明
- 调试困难 → 显示 "覆盖中" 标识

**用户决策**: _(_待你确认_)_

---

### D5. 删除语义: 系统 enabled=false / 自定义软删除

**推荐方案**:
- 系统节点: 不删, `enabled=false` 等同删除
- 自定义节点: SoftDeleteMixin (已有), 30 天后硬删

**风险**: 无

**用户决策**: _(_待你确认_)_

---

### D6. 版本管理: 完整 CustomNodeVersion + 回滚

**调研依据**:
- Prefect: deployment versioning + rollback
- Mage: Git-based versioning
- 业界共识: 用户代码必须有版本历史

**推荐方案**: **完整版本管理 + 回滚 API**
- CustomNodeVersion 表 (已有, 含 version_number / code / contract / change_summary)
- 提交新版本: 自动 version_number+1
- 回滚: 把旧版本 code 拷回 custom_nodes.code
- 不删旧版本 (历史可查)

**风险**: 存储增长 — 已规划定期清理 (Phase 5 B25)

**用户决策**: _(_待你确认_)_

---

### D7. Contract 检测: AST 静态 + 试运行反推 (混合)

**调研依据**:
- Mage: 纯代码优先 (positional args)
- Prefect: 纯类型注解优先
- n8n/Node-RED: 纯表单优先
- 业界最佳实践: **Yin-Yang (代码 + UI 双向同步)** — VS Code Rename Symbol 风格

**推荐方案**:
- **静态 (AST)**: 推断 input/output/param names + types
- **动态 (试运行)**: 用 sample 跑一次, 推断 outputs 类型
- **混合**: 静态给结构, 动态给类型验证
- **必须人工确认**: contract_preview 是 draft, 用户可编辑

**风险**: 反推不准 → 显示 warnings, 用户必须确认

**用户决策**: _(_待你确认_)_

---

### D8. RBAC: 三档角色

**调研依据**:
- 现有 RBAC 体系 (Phase 6 B28): super_admin / tenant_admin / analyst / viewer

**推荐方案**: 沿用现有体系
- **super_admin**: 系统节点启停 + 任意租户
- **tenant_admin**: 本租户节点 CRUD
- **analyst**: 只读 (节点列表 + 详情, 不能编辑)
- **viewer**: 只读

**用户决策**: _(_待你确认_)_

---

### D9. 资源限制: 内存 2Gi / 超时 60s

**推荐方案** (起步):
- 内存: 2 GiB
- CPU: 1 核 / 60s wall clock
- 进程数: 32
- 文件描述符: 64
- 后续可按租户配置 (Phase 5 计费集成)

**用户决策**: _(_待你确认_)_

---

### D10. 文档位置: docs/node-plugin/

**推荐方案**: 子目录, 不污染主架构文档

**用户决策**: _(_待你确认_)_

---

### D11. 数据库: 沿用 PostgreSQL (不引入 SQLite)

**理由**:
- 已有 CustomNode / Version / TestRun 表
- SQLite 增加运维负担
- 多库一致性 / 备份复杂

**用户决策**: _(_待你确认_)_

---

### D12. 草稿机制: 新建 node_definition_drafts 表

**理由**:
- 用户频繁编辑时, 不想每次都创建 version
- 草稿可丢弃, 不污染版本历史
- 缓存 contract_preview (AST 反推结果), 减少后端计算

**用户决策**: _(_待你确认_)_

---

### D13. 编辑锁: 新建 node_definition_locks 表

**理由**:
- 防止多人同时编辑导致覆盖
- TTL + 心跳 (避免锁泄露)
- 不引入 Redis 分布式锁 (DB 锁够用, 减少依赖)

**用户决策**: _(_待你确认_)_

---

### D14. 编辑器后端补全 (LSP): 先不做 (Phase 2)

**调研依据**:
- 业界建议: pylsp / jedi-language-server 接 LSP over WebSocket
- 需要独立进程 (pylsp), 运维成本
- v1 仅依赖 Monaco 内置 Python 高亮 + AST 静态校验

**推荐方案**: **v1 不做 LSP**, Phase 2 评估
- 触发条件: 用户反馈补全体验差, 或代码超过 5000 字符 / 节点

**用户决策**: _(_待你确认_)_

---

### D15. 文件存储: 不存 (代码全部 DB TEXT)

**理由**: 见 D2

**用户决策**: _(_待你确认_)_

---

### D16. 试运行 UI 位置: 弹窗 Modal (非独立页)

**调研依据**:
- Mage: 测试按钮在 block 卡片上
- n8n Code node: 弹窗编辑 + 右侧结果
- 业界惯例: 试运行是辅助操作, 不抢用户视线

**推荐方案**: **Modal 弹窗** (非独立路由)
- 从编辑页 / 详情页点 [▶ 试运行] 弹出
- 关闭后回到原页面

**用户决策**: _(_待你确认_)_

---

### D17. 多 worker 同步: Redis pub/sub

**调研依据**:
- Celery 多 worker 进程不共享内存
- NodeRegistry 是进程级单例
- 必须有同步机制

**推荐方案**: **Redis pub/sub 频道 `node:reload`**
- 发布: 提交新版本时
- 订阅: 所有 Celery worker 进程
- 收到消息: `unregister(old) + register(new)`

**备选**: 数据库轮询 (低频)
**风险**: Redis 故障 → 同步失败 → worker 用旧版本 (兜底: 启动时加载所有)

**用户决策**: _(_待你确认_)_

---

### D18. sandbox v1 vs v2 (Docker 增强)

**推荐方案**: **v1 = subprocess + setrlimit + AST 黑名单** (本计划)
**v2 = Docker 容器 + seccomp** (Phase 2, 评估后再做)

**触发 v2 的条件**:
- 用户报告 sandbox 逃逸
- 合规要求 (金融级)
- 多租户干扰投诉

**用户决策**: _(_待你确认_)_

---

## 风险登记 (实施前)

| ID | 风险 | 缓解 | 优先级 |
|---|---|---|---|
| R1 | Monaco CDN 网络抖动 | 加 Suspense fallback + retry | Medium |
| R2 | 用户代码沙箱逃逸 | v1 防御深度 (AST + setrlimit + RestrictedPython); v2 Docker | High |
| R3 | 多 Celery worker 不同步 | Redis pub/sub + 启动全量加载 | Medium |
| R4 | 编辑锁泄露 | TTL + heartbeat + Celery beat 清理 | Low |
| R5 | AST 反推不准确 | 显示 warnings + 用户必须确认 | Medium |
| R6 | 草稿数据膨胀 | 30 天自动清理 + LIMIT 数量 | Low |
| R7 | 版本无限增长 | 软上限 100 version/节点, 提示用户清理 | Low |

---

## 用户审批签字栏

请逐项审批, 不同意的请在备注中说明:

- [ ] **D1** Monaco Editor — _审批:___ 备注:___
- [ ] **D2** PostgreSQL TEXT — _审批:___ 备注:___
- [ ] **D3** Subprocess + setrlimit + AST 黑名单 (v1) — _审批:___ 备注:___
- [ ] **D4** 租户自定义 > 系统节点 — _审批:___ 备注:___
- [ ] **D5** 系统 enabled=false / 自定义软删除 — _审批:___ 备注:___
- [ ] **D6** 完整版本管理 + 回滚 — _审批:___ 备注:___
- [ ] **D7** AST + 试运行混合 — _审批:___ 备注:___
- [ ] **D8** 三档 RBAC — _审批:___ 备注:___
- [ ] **D9** 内存 2Gi / 超时 60s — _审批:___ 备注:___
- [ ] **D10** docs/node-plugin/ — _审批:___ 备注:___
- [ ] **D11** 沿用 PostgreSQL — _审批:___ 备注:___
- [ ] **D12** drafts 表 — _审批:___ 备注:___
- [ ] **D13** locks 表 — _审批:___ 备注:___
- [ ] **D14** LSP Phase 2 — _审批:___ 备注:___
- [ ] **D15** 不存文件 — _审批:___ 备注:___
- [ ] **D16** 试运行 Modal — _审批:___ 备注:___
- [ ] **D17** Redis pub/sub 同步 — _审批:___ 备注:___
- [ ] **D18** sandbox v2 Docker 后续 — _审批:___ 备注:___

---

## 重新规划 / 修改

如有决策需要修改, 请在本节说明, 我会重新设计并更新相关文档:

### 修改记录
_(空)_
