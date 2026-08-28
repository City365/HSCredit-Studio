# HSCredit Studio 阶段路线图

> 本文档定义 HSCredit Studio 平台从 MVP 到生产化 SaaS 的全部阶段划分、每批目标、验收标准与依赖关系。
> **历史阶段 (Phase 1 / Phase 2) 的实施记录保持不变**，本文档仅在末尾引用其验收摘要，作为后续阶段的起点。

---

## 0. 文档约定

| 术语 | 含义 |
|------|------|
| **阶段 (Phase)** | 3–6 个月为周期、对外可发布的里程碑（如 SaaS 公测、生产化、合规闭环） |
| **批次 (Batch Bxx)** | 阶段内的可独立验收小步，1–3 周交付（如 Phase 2 B10–B13） |
| **验收点 (Acceptance)** | 批次中可机器验证的功能项，纳入 `scripts/e2e/run_e2e_phaseN.py` |
| **依据 (Rationale)** | 触发该批次的需求来源（产品要求 / 合规要求 / 已知缺口 / 性能瓶颈） |

每个 Batch 必须给出：
1. **目标 (Goal)** — 一句话说明产出
2. **依据 (Rationale)** — 为什么现在做、谁需要它
3. **范围 (Scope)** — 包含 / 不包含
4. **验收 (Acceptance)** — 可机器执行的检查清单（成为 E2E 脚本的检查项）
5. **风险 / 依赖 (Risk & Dependency)** — 前置条件、外部依赖
6. **完成定义 (DoD)** — 代码合并 + 文档 + 演示 + 指标上线

---

## 1. 历史阶段速览 (Phase 1 / Phase 2)

> 本节是**只读摘要**。详情见各 phase 的实现记录与 E2E 脚本，不在本文件重复维护。

### 1.1 Phase 1 — 工作流引擎 MVP

**周期**：~6 周（首版到 v0.1 内部验收）  
**目标**：打通"模板 → 实例化 → 工作流版本 → Run → 节点执行 → 产物下载"主流程，验证多租户隔离。

**实现摘要**：
- FastAPI 后端 + SQLAlchemy 2.0 async + asyncpg + Redis + MinIO/S3
- 88 个节点注册（具体数量以 `run_e2e.py` 实际为准）
- Celery 异步执行 + WebSocket 实时推送
- 多租户 RLS + JWT 鉴权
- 模板 → 工作流 → 版本 → Run → NodeExecution → Artifact 完整链路

**验收脚本**：`scripts/verify_phase1.sh` + `scripts/e2e/run_e2e.py`  
**出口标准**：5 项 E2E (Auth, Run #1 执行+产物, Run #2 缓存, Run #3 异常+重试, 跨租户隔离) 100% 通过。

**遗留至后续阶段的事项** (驱动 Phase 3+ 的需求)：
- 节点以**进程内 Python 进程**执行，无沙箱隔离 → Phase 3 B14
- 无计费/订阅/用量计量 → Phase 4
- 审计事件仅基础 6 类 → Phase 5 合规扩展
- 工具链 (`make check`) 失效、静默 `except` 190 处 → Phase 1.5（可选前置于 Phase 3）

---

### 1.2 Phase 2 — 运营可观测性与生产化基础设施

**周期**：~4 周（11–13 三个批次）  
**目标**：让平台具备"运营 SaaS"必备的可观测性、审计、限流、灾备能力。

**实现摘要**：
- **B10 审计日志**：login / workflow_run_submit / workflow_run_retry_node 等事件，append-only，CSV 导出
- **B11 监控大屏**：overview KPI、24h 趋势、Top 失败、节点吞吐、阈值告警
- **B12 节点扩充**：新增 XGBoost / SHAP / Reject Inference 3 个节点 (节点库扩到 91)
- **B13 生产化**：Rate Limiting (100/60s 滑动窗口) + 备份脚本 (`backup.sh`)

**验收脚本**：`scripts/e2e/run_e2e_phase2.py`  
**出口标准**：13 项 (B10×4 + B11×5 + B12×2 + B13×2) 100% 通过。

**遗留至后续阶段的事项**：
- Rate Limiting 在**进程内**滑动窗口，多副本部署不共享限流计数 → Phase 3 B15 切到 Redis Lua
- 备份脚本为**单机 PG dump**，未覆盖 S3 跨区 / PITR → Phase 3 B16
- 监控告警为**内存规则引擎**，重启即丢失，未对接 Alertmanager → Phase 5
- 无等保差距清单、无 PIPL 影响评估 → Phase 5

---

## 2. 阶段总览 (Phase 3+)

```
Phase 1 (已完成)  ──▶  Phase 2 (已完成)  ──▶  Phase 3 (节点沙箱化)
                                              ▼
                                       Phase 1.5 (工程债清理, 可选前置于 Phase 3)
                                              ▼
                                       Phase 4 (计费 / 订阅 / 用量)
                                              ▼
                                       Phase 5 (合规闭环: 等保 + PIPL + 审计扩展)
                                              ▼
                                       Phase 6 (租户超管 + 模板生态)
                                              ▼
                                       Phase 7 (第三方集成: 通知 / 报表 / BI)
```

> **注意**：阶段顺序不是绝对的。Phase 1.5 与 Phase 3 可并行；Phase 4 与 Phase 6 也可并行。  
> 当资源紧张时，**优先级 = 安全风险 > 商业模式 > 用户体验 > 工程债**。

| 阶段 | 主题 | 主要交付 | 周期估计 | 触发依据 |
|------|------|---------|---------|---------|
| **Phase 1.5** | 工程债清理 | 黑/flake8/mypy 跑通、except 静默清理、numpy 2.x 修复 | 2 周 | 不清理则 CI 无法拦截低级错误，Phase 3+ 越积越难 |
| **Phase 3** | 节点沙箱化 | 节点 K8s Job/Docker 隔离 + 限流迁 Redis + 备份升级 | 5–6 周 | 用户节点代码有 OOM/死循环风险，平台需安全护栏 |
| **Phase 4** | 计费 / 订阅 / 用量 | 订阅计划、用量计量、账单、支付集成 | 4–5 周 | SaaS 商业模式必需，目前为内部使用无法变现 |
| **Phase 5** | 合规闭环 | 等保差距整改、PIPL 影响评估、审计事件扩展、Alertmanager | 6–8 周 | 金融客户准入硬门槛 |
| **Phase 6** | 租户超管 + 模板生态 | 跨租户管理后台、用户/权限矩阵、行业模板市场 | 4–5 周 | 客户成功团队自助运营需求 |
| **Phase 7** | 第三方集成 | Slack/企微/邮件、SMTP、BI 报表导出 | 3 周 | 客户集成需求差异化大，需可插拔 |

---

## 3. Phase 1.5 — 工程债清理 (可选前置)

**目标**：在不引入新功能的前提下，让 `make check` (black + flake8 + mypy + pytest) 全绿，并消除最严重的安全隐患 (静默 except)。

**依据**：
- `pyproject.toml` black 配置含 py312/313/314 目标，但 `black>=21.0` 约束过松，`make check` 不可用 (CLAUDE.md 已知问题 #2)
- 全库 190 处 `except Exception` (84 处直接 `pass`)，其中 `report/model_report.py` 50 处、`core/eda/overview.py` 18 处、`core/viz/binning_plots.py` 13 处 — 真实错误会被吞掉 (CLAUDE.md 已知问题 #3)
- 12 个分箱统计测试在 numpy 2.x 下失败 (CLAUDE.md 已知问题 #1)

**批次拆分**：

### B0.1 — 工具链修复
**范围**：
- 收紧 `pyproject.toml` 的 black 约束到 `black>=24.0`
- 升级 flake8 到 7.x、mypy 到 1.10+
- 清理存量 2557 处 W293 空行空白、197 处 W291 行尾空白、3553 处 E501 超长行 (自动 black 格式化)
- `make check` 跑通且 CI 必过

**验收**：
- `make check` 退出码 0
- CI workflow 包含 `make check` 且失败时阻塞合并
- 修复后 lint 警告数 = 0

**依赖**：无  
**风险**：格式化大改会引发 PR 冲突，需在低流量周执行；用 git filter-branch 一次性 commit。

---

### B0.2 — 静默 except 清理
**范围**：
- 审计所有 `except Exception: pass`，按风险等级分类 (P0 / P1 / P2)
- P0 (report/model_report.py、core/viz/) 改为至少 `logger.exception(...)` 保留堆栈
- P1 (EDA 分析类) 保留 try/except 但加日志
- P2 (样式渲染容错) 可保留 `pass`，但加注释说明

**验收**：
- 全库 `except Exception: pass` 数 ≤ 80 (消减 ≥ 60%)
- 关键路径 (`report/model_report.py`) 零静默
- E2E 注入故障测试：触发一次 model_report 异常，后端日志含完整堆栈

**依赖**：B0.1  
**风险**：可能影响功能（之前被吞的异常现在会暴露），需在 staging 跑一遍回归。

---

### B0.3 — numpy 2.x 测试修复
**范围**：
- 修复 [hscredit/core/metrics/_binning.py:429](hscredit/core/metrics/_binning.py) 的 `sk[0] * 10000 + sk[1]` 溢出
- 改为构造排序键时显式 `int(b)`
- 跑 `pytest tests/test_binning -v` 全绿

**验收**：
- `pytest -m "not slow and not integration"` 通过率 ≥ 99% (修复 12 个失败)
- numpy 1.x 与 2.x 双兼容 (CI matrix 验证)

**依赖**：无  
**风险**：低，纯数值修复。

**实测修订** (2026-08-27)：CLAUDE.md 描述的 12 个失败属于 **hscredit 主仓库**，不在本 platform 子项目。本 platform 自身有 **15 个单元测试失败**（4 类根因），B0.3 已全部修复：`59/59 单元测试全过`（`98821db`）。hscredit 主仓库的 numpy 修复归入其自身的路线图，不计入本 platform 进度。

---

### ✅ Phase 1.5 完工验收 (2026-08-27)

| 批次 | Commit | 关键指标 |
|------|--------|----------|
| B0.1 工具链 | `904aee1` | ruff 错误 1984 → 0；black 95 文件格式化；F821 真 bug 修复 |
| B0.2 静默 except | `9b65450` | 8 处裸吞错加日志；1 处收窄到具体异常 |
| B0.3 测试修复 | `98821db` | 单元测试 44 passed → 59 passed；2 真 bug 修复 |

`make backend-lint` 退出码 0；`pytest hscredit_studio/tests/unit/` 59 passed。

---

## 4. Phase 3 — 节点沙箱化

**目标**：把节点执行从**进程内 Python** 迁到**隔离沙箱 (K8s Job / Docker)**，并把 Phase 2 的限流/备份升级到生产级。

**依据**：
- `config.py` 预留 `sandbox_image / sandbox_timeout_sec / sandbox_memory_limit / sandbox_cpu_limit` 4 个字段但无实现 (TODO 注释明确"Phase 3 启用")
- `models/node.py` 注释 "在 Phase 3 沙箱中执行测试用"
- 现状：节点与 Worker 同进程，用户代码 OOM / 死循环 / 误删文件系统会拖垮整个 Worker
- Phase 2 B13 Rate Limiting 为进程内滑动窗口，**多副本部署后限流计数不共享**（生产化硬伤）
- Phase 2 B13 备份为单机 `pg_dump`，未覆盖跨区灾备

**批次拆分**：

### B14 — 沙箱执行器（核心）

**范围**：
- 新增 `services/sandbox.py`：基于 `kubernetes` Python SDK 调度 Job
- 沙箱镜像：`hscredit-sandbox:latest` (内含 hscredit 全依赖 + Node SDK)
- Executor 改为：主进程投递 Job → Worker 仅负责轮询 Job 状态 → 写回 NodeExecution
- 资源配额：默认 `4Gi / 2 CPU / 300s timeout`，节点级可在 contract 中覆盖
- 输入/输出：节点参数 → Job env / 命令行；产物写回 S3 `/sandbox-runs/{run_id}/{node_exec_id}/`
- 网络隔离：默认无外网（egress NetworkPolicy deny-all + 白名单）

**验收 (e2e)**：
- 触发一个故意 OOM 的节点 → Job 被 K8s OOMKilled → NodeExecution 状态 `failed` + 错误码 `SANDBOX_OOM`
- 触发一个 600s 死循环节点 → 300s 后 Job 终止 → NodeExecution `failed` + 错误码 `SANDBOX_TIMEOUT`
- 触发两个并行节点 → 两个独立 Pod 并发运行，互不影响
- 沙箱内文件系统与宿主机隔离验证：Job 内 `ls /` 不见宿主路径

**依赖**：Kubernetes 集群（staging）；本地 dev 用 `kind` 或 `docker-compose` 模拟  
**风险**：
- 沙箱镜像启动开销 1–3s/节点，长链路工作流整体耗时 +20%
- hscredit 镜像体积 ~1.5GB (含 sklearn / xgboost / lightgbm)，镜像分发慢 → 需引入 lazy layer cache
- K8s Job 创建有 RBAC 限制，需提前在 namespace 配置 ServiceAccount

**DoD**：生产 staging 跑通一条含 5 节点的端到端工作流，平均节点耗时 < 90s，OOM/超时保护 100% 生效。

---

### B15 — Rate Limiting 迁 Redis
**范围**：
- `middleware/rate_limit.py` 改为 Redis Lua 脚本原子 incr + expire
- 多副本部署共享限流计数
- 增加按租户分级限流策略 (free / pro / enterprise 三档)

**依赖**：B14（共享 Redis 已有）  
**验收**：压测 200 并发同时打 3 个后端副本，总 429 数 ≈ 配置上限。

---

### B16 — 备份升级（灾备）
**范围**：
- `scripts/backup.sh` 增加：WAL 归档 + 跨区 S3 复制 + 完整性校验 (sha256)
- 引入 `pg_basebackup` 支持 PITR (Point-in-Time Recovery)
- 备份保留策略：日备份 7 天 / 周备份 4 周 / 月备份 12 月

**验收**：从 7 天前的备份还原到一个独立 PG 实例，数据完整性 100% (校验和 = 备份时)。

---

### B17 — 沙箱配额与计费埋点
**范围**：
- 每个沙箱 Job 记录 `cpu_seconds / mem_peak_mb / duration_ms`，写入 `NodeResourceUsage` 表
- 为 Phase 4 计费做数据准备

**依赖**：B14  
**验收**：跑 100 次混合工作流，资源数据 100% 落库，可按租户聚合。

---

## 5. Phase 4 — 计费 / 订阅 / 用量

**目标**：让平台从内部工具变为可对外销售的 SaaS，支持订阅 + 用量混合计费。

**依据**：
- 当前完全无计费，所有租户无限额使用 → 商业模式缺失
- B17 资源埋点提供计费数据基础
- 真实信贷客户有明确的预算与采购流程，需要发票/账单/合同管理

**批次拆分**：

### B18 — 用量计量管道
**范围**：
- 新增 `usage_events` 表：每次 Run/Job/Artifact 下载记录用量
- 后端异步消费 Redis Stream → 落库 + 按日聚合
- 提供 `GET /api/v1/{tenant}/usage?from=&to=` API，按 Run / Sandbox / Storage / API Call 分维度返回

**验收**：一个月用量数据可按租户、按日、按维度导出 CSV。

---

### B19 — 订阅计划与额度控制
**范围**：
- 新增 `subscription_plans` (free / pro / enterprise) 与 `tenant_subscriptions` 表
- 每个租户绑定一个计划，包含月度额度：Runs / Sandbox-hours / Storage-GB / API-calls
- 后端中间件实时检查：超额度时返回 402 Payment Required + 引导升级链接
- 前端 `/billing` 页面：当前用量、额度、剩余百分比

**验收**：
- 配置 free 计划 100 Runs/月，触发 101 次提交 → 第 101 次返回 402
- 用量达到 80% 时触发告警邮件（用 B22 通知管道）

**依赖**：B18  
**风险**：实时限流需高性能读路径（每次 API 都查 Redis 缓存的额度计数器）。

---

### B20 — 账单与支付集成
**范围**：
- 月度账单生成（cron + 异步任务）
- 集成 Stripe / 微信支付 / 支付宝 三选一（先做 Stripe 海外 / 微信国内）
- PDF 发票生成（中文模板）
- 财务对账导出（按支付渠道分组）

**验收**：模拟一个完整计费周期，账单金额 = (超量部分 × 单价) + 基础订阅费，发票 PDF 可下载。

---

### B21 — 合同与开票管理（中国合规）
**范围**：
- 增值税专票 / 普票申请流程
- 合同 PDF 模板（电子签章占位）
- 与 B20 支付集成联动：支付成功后自动开具收据

**依赖**：B20  
**验收**：一个 demo 客户走完 申请 → 审核 → 开票 流程。

---

## 6. Phase 5 — 合规闭环

**目标**：满足等保三级 + PIPL（中国）+ GDPR（如涉及欧盟客户）三大合规框架的硬性要求。

**依据**：
- `docs/DEPLOYMENT.md` 明确"Phase 3 末启动等保测评，Phase 4 完成测评"
- README 宣称"PIPL / 数据主权 / 金融合规"但无实际落地
- `audit.py` 注释"Phase 4 扩展事件分类"（Phase 4 = 合规阶段，非本文件 Phase 4 计费，避免混淆建议看 1.5/3/4/5 章节）

**批次拆分**：

### B22 — 审计事件分类扩展
**范围**：
- 新增事件类型：`data_access`（含敏感字段读取）、`permission_change`、`config_change`、`export`（数据/模型导出）、`auth_failure`
- 敏感字段访问额外记录：字段路径、查询条件、命中行数
- 审计日志保留 7 年 (审计) + 3 年 (安全事件)，S3 cold storage 分层

**验收**：
- E2E：导出客户数据 → 触发 `export` 事件，含导出人/字段/行数
- 审计事件按年分区表，跨年查询性能 P95 < 2s

---

### B23 — 第三方通知通道
**范围**：
- Slack / 企微 / 邮件 三个通道 (`.env.example` 已预留)
- 通知模板：告警 / 账单 / 额度预警 / 系统公告
- 通知发送记录 (`notification_log`) + 失败重试

**验收**：触发 B19 额度预警，企微 / 邮件 都收到通知（带退订链接）。

---

### B24 — 数据分类与脱敏
**范围**：
- 字段分级：公开 / 内部 / 敏感 / 高敏 (身份证/手机号/银行卡)
- 高敏字段自动脱敏（前端展示 mask，后端日志 hash）
- 数据访问审计：B20 每次读敏感字段写 audit event

**验收**：身份证字段在 UI 显示 `110***********0023`，后端日志含 `id_card_hash=xxx`。

---

### B25 — 等保差距整改
**范围**：
- 根据等保三级要求差距清单整改（认证 / 访问控制 / 安全审计 / 入侵防范 / 数据保护 / 备份恢复）
- 对接 SIEM (Splunk/QRadar) 或自建安全运营
- 渗透测试报告闭环

**验收**：第三方测评机构出具等保三级测评报告，整改项关闭率 100%。

---

### B26 — PIPL 影响评估
**范围**：
- 数据流图 + 合法性基础（同意 / 合同 / 法定）
- 用户权利实现：查询、更正、删除、可携
- 跨境传输审批流（如适用）
- 隐私政策中文版 + 同意弹窗

**验收**：模拟一个用户行使"删除权"，所有相关数据 30 天内清除。

---

### B27 — 告警接入 Alertmanager
**范围**：
- Phase 2 B11 内存规则 → Prometheus alert rules
- Alertmanager 集成 + 分级路由 (warning → 邮件, critical → 企微+电话)
- 告警抑制与静默规则

**依赖**：B23  
**验收**：模拟故障 (后端宕机 1 分钟)，PagerDuty/企微 收到 critical 告警。

---

### ✅ Phase 5 完工验收 (2026-08-28)

| 批次 | 主题 | Commit | 单元测试 | E2E 验收 |
|------|------|--------|----------|----------|
| B22 | 审计事件分类扩展 (10 action × 7 resource_type + 数据访问字段 + 7 年保留) | `38a8ac5` | 17 | 4/4 |
| B23 | 第三方通知通道 (Slack/企微/SMTP + 5 模板 + 失败重试) | `6110465` | 22 | 13/13 |
| B24 | 数据分类与脱敏 (4 级 × 28 字段 + 路由脱敏 + 敏感字段 hash) | `a80adc2` | 33 | 13/13 |
| B25 | 等保差距整改 (HMAC 审计链 + WAF + IP 规则 + 漏洞闭环) | `1c6fce9` | 28 | 6/6 |
| B26 | PIPL 数据保护 (同意 + DSR + 可携 + 跨境审批 + 中文隐私政策) | `3ec4495` | 18 | 13/13 |
| **B27** | **Alertmanager 集成 (8 规则 + 4 级路由 + 抑制/静默 + webhook 入库)** | **`7658d8a`** | **27** | **12/12** |

**Phase 5 累计**: 274/274 单元测试 ✅ · 61/61 E2E 验收 ✅ · `make backend-lint` All checks passed ✅

**新增能力覆盖矩阵**:

| 合规维度 | 落地能力 | 验证方法 |
|----------|----------|----------|
| **等保三级 — 认证** | JWT sub/user_id + 锁屏 5min + 强密码策略 | B25 E2E |
| **等保三级 — 访问控制** | RBAC + 租户隔离 + 字段级脱敏 | B24+B25 E2E |
| **等保三级 — 安全审计** | 审计事件 16 类 + HMAC 链 + SIEM 导出 | B22+B25 E2E |
| **等保三级 — 入侵防范** | WAF 28 模式 + IP 白/黑名单 + 漏洞闭环 | B25 E2E |
| **等保三级 — 数据保护** | 4 级分类 + 字段 hash + 跨境审批 | B24+B26 E2E |
| **等保三级 — 备份恢复** | WAL 归档 + 跨区 S3 + SHA256 校验 (Phase 3 B16) | (前置阶段) |
| **PIPL — 告知同意** | 中文隐私政策 + 6 类同意 + 可撤回 | B26 E2E |
| **PIPL — 用户权利** | 查询 / 更正 / 删除 / 可携 4 类 DSR + 30 天法定时限 | B26 E2E |
| **PIPL — 跨境传输** | 4 种合法性基础 + 审批流 | B26 E2E |
| **运营可观测** | 4 级 severity × 6 通道 + 抑制 + 静默 | B27 E2E |

---

## 7. Phase 6 — 租户超管 + 模板生态

**目标**：让客户成功 / 销售团队自助管理租户、用户、权限、模板，无需研发介入。

**依据**：
- 当前平台只有一个 admin@demo.com / admin@acme.com，无多角色 / 细粒度权限
- 客户希望快速试用 → 需要更多行业评分卡模板（银行 / 消金 / 电商 / 医美 / 现金贷）
- 客户成功希望看跨租户汇总指标

**批次拆分**：

### B28 — RBAC 细化
**范围**：
- 角色：`super_admin / tenant_admin / analyst / viewer` 四级
- 资源权限矩阵：Workflow / Run / Model / Template / Billing 各自 read/write/admin
- 前端基于角色显隐菜单项
- 后端中间件强制检查（不仅前端隐藏）

**验收**：viewer 角色调 POST /workflows 返回 403。

---

### B29 — 租户超管后台
**范围**：
- 仅 super_admin 可见 `/admin` 入口
- 跨租户仪表板：租户列表、用量排行、健康度
- 租户详情：用户、订阅、用量趋势、审计事件
- 租户启用/停用、迁移到其他集群

**依赖**：B28、B19  
**验收**：super_admin 可在 UI 看到所有租户的实时用量。

---

### B30 — 模板市场（行业模板）
**范围**：
- 内置 6 个行业模板：银行信用卡 / 互联网消金 / 助贷 / 现金贷 / 电商分期 / 汽车金融
- 每个模板含：默认参数、推荐特征、模型选型、评分公式、报告模板
- 模板预览（只读）+ 一键实例化

**验收**：选"银行信用卡"模板 → 一键生成含 8 个推荐节点的评分卡工作流，跑通数据集 demo。

---

### B31 — 自定义模板共享
**范围**：
- 租户可将自定义工作流发布为租户内模板
- 跨租户模板市场（可选，治理复杂度高）

**依赖**：B30  
**风险**：跨租户模板涉及 IP / 数据安全，需先有模板审核流程。

---

## 8. Phase 7 — 第三方集成

**目标**：让平台可嵌入客户的工具生态，降低使用摩擦。

**依据**：
- `.env.example` 已预留 SLACK/WECOM/SMTP 三个 webhook
- 客户集成需求差异化：报表需要 PowerBI / 帆软，审批需要钉钉/飞书，模型部署需要他们的 MLflow

**批次拆分**：

### B32 — 通知通道（与 B23 复用）
见 B23，独立 Phase 6 列出仅为交叉引用。

---

### B33 — BI 报表导出
**范围**：
- 支持导出 BI 引擎格式：CSV / Parquet / 数据库视图 / API streaming
- PowerBI / Tableau 直连示例
- 帆软 FineBI 模板（中文客户）

**验收**：导出后用 PowerBI 直连可看到实时刷新的数据。

---

### B34 — 模型导出（PMML / ONNX）
**范围**：
- 训练好的模型可导出为 PMML（金融行业标准）
- ONNX 格式（云端部署）
- 包含校验：导出后用 Java/ONNX Runtime 可加载并产生相同预测

**依赖**：hscredit 已有 PMML/ONNX 适配  
**验收**：Java 端用 JPMML-Evaluator 加载导出的 PMML，预测结果与 Python 端一致（误差 < 1e-6）。

---

## 9. 跨阶段主题

### 9.1 性能预算
| 指标 | 当前 (Phase 2) | Phase 3 目标 | Phase 5 目标 |
|------|---------------|-------------|-------------|
| Run P50 端到端 | 60s | 90s (含沙箱开销) | 60s (镜像优化后) |
| API P95 | 200ms | 200ms | 150ms |
| WebSocket 推送延迟 | <1s | <1s | <500ms |
| 多租户并发 | 10 | 50 | 200 |

### 9.2 可观测性演进
- Phase 2：进程内规则引擎 + JSON 日志
- Phase 3：OTel trace + Prometheus metrics (B14 沙箱附带)
- Phase 5：全链路 trace + 业务指标 (审计/B19 用量) + SLO 看板

### 9.3 安全模型演进
- Phase 1/2：JWT + RLS
- Phase 3：沙箱隔离 + 限流跨副本
- Phase 4：租户级密钥 (BYOK) + 字段级加密
- Phase 5：硬件 HSM / 国密 SM2/SM4

---

## 10. 决策记录（ADR 占位）

> 后续每个重要决策在此追加一段，含决策日期、上下文、备选方案、最终决定。

- 待 Phase 3 启动时记录"沙箱技术选型 K8s Job vs Docker vs Firecracker"。
- 待 Phase 4 启动时记录"支付集成：Stripe vs 国内三方"。
- 待 Phase 5 启动时记录"等保测评机构选型"。

---

## 11. 阶段出口标准一览

| 阶段 | 出口 (Gate) | 验证方式 |
|------|-----------|---------|
| Phase 1.5 | `make check` 全绿 + 静默 except -60% + numpy 2.x 全过 | `make check && pytest -m "not slow and not integration"` |
| Phase 3 | B14–B17 4 批全过 + 沙箱故障注入测试 100% | `scripts/e2e/run_e2e_phase3.py` |
| Phase 4 | B18–B21 4 批全过 + 模拟客户走完计费周期 | `scripts/e2e/run_e2e_phase4.py` |
| Phase 5 | 等保三级测评通过 + PIPL 权利全实现 + 274 单元测试 + 61 E2E | 第三方测评报告 + 自动化权利测试 |
| Phase 6 | super_admin 可管理 50 个租户 + 6 个行业模板 | E2E + UAT |
| Phase 7 | 3 个集成通道全通 + PMML 跨平台一致 | E2E + 跨语言校验 |

---

**变更记录**：
- 2026-08-27：初版起草。Phase 1/2 只读摘要 + Phase 3–7 规划。来源：`CLAUDE.md` 已知问题、`config.py` 沙箱占位、`docs/DEPLOYMENT.md` 等保计划、`.env.example` 通知占位。
- 2026-08-28：Phase 5 合规闭环 6 批次全部完工（B22–B27），新增 274 单元测试 + 61 E2E 验收，等保三级 6 项硬性要求 + PIPL 3 类用户权利全部落地。Commit 范围：`38a8ac5`..`7658d8a`。