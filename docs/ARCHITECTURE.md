# HSCredit Studio 架构设计

> 平台架构概览, 系统组件图, 数据流, 技术栈, 安全边界
>
> 适用版本: v0.1.x · 最近更新: 2026-08-28

---

## 1. 系统定位

HSCredit Studio 是**多租户 SaaS 信用风险建模平台**, 在衡枢真信 (hscredit) 评分卡工具箱基础上提供:

- **可视化工作流编排** — React Flow 拖拽式节点编排
- **多租户隔离** — 租户级 RLS + JWT 鉴权
- **节点沙箱化执行** — Celery 异步任务队列
- **合规闭环** — 等保三级 + PIPL + GDPR
- **计费计量** — 订阅 + 用量 + 账单

**核心价值**: 把 hscredit 的 Python 评分卡建模能力包装成可订阅的 SaaS 服务, 让金融机构客户无需自建工程团队即可使用。

---

## 2. 顶层架构

```mermaid
graph TB
    subgraph Client["客户端"]
        UI[React 前端<br/>Vite + Ant Design]
        SDK[TypeScript SDK<br/>@hscredit/api]
    end

    subgraph Edge["边缘层"]
        LB[负载均衡<br/>Nginx / K8s Ingress]
        CDN[CDN<br/>静态资源]
    end

    subgraph App["应用层"]
        API[FastAPI 后端<br/>8003 端口]
        Worker[Celery Worker<br/>异步执行]
        Beat[Celery Beat<br/>定时任务]
    end

    subgraph Data["数据层"]
        PG[(PostgreSQL 16<br/>主库)]
        ReadReplica[(只读副本<br/>analytics)]
        Redis[(Redis 7<br/>缓存/限流/Stream)]
        S3[MinIO/S3<br/>产物存储]
    end

    subgraph Obs["可观测性"]
        Prom[Prometheus<br/>指标]
        AM[Alertmanager<br/>告警]
        Graf[Grafana<br/>面板]
        Loki[Loki<br/>日志]
    end

    subgraph External["外部集成"]
        WeCom[企业微信]
        Slack[Slack]
        SMTP[SMTP]
        Tenant[租户系统<br/>Webhook 接收方]
    end

    UI --> CDN
    UI --> LB
    SDK --> LB
    LB --> API
    API --> Worker
    Worker --> S3
    API --> PG
    API --> Redis
    Worker --> Redis
    Worker --> PG
    Beat --> PG
    API --> ReadReplica
    API --> Prom
    Worker --> Prom
    API --> WeCom
    API --> Slack
    API --> SMTP
    API --> Tenant
    Prom --> AM
    AM --> WeCom
    AM --> Slack
    Prom --> Graf
```

---

## 3. 后端模块架构

后端按"业务域"划分, 每个域有独立的 service + schemas + API 路由:

```mermaid
graph LR
    subgraph Core["核心"]
        Auth[auth.py<br/>JWT 登录]
        RBAC[rbac.py<br/>5×5×3 权限矩阵]
        Audit[audit.py<br/>append-only 事件]
    end

    subgraph Workflow["工作流域"]
        Workflows[workflows.py]
        Runs[runs.py]
        Templates[templates.py]
        IndustryTpl[industry_templates.py]
        TplShare[template_sharing.py]
    end

    subgraph Exec["执行域"]
        Sandbox[sandbox.py<br/>K8s Job]
        Contracts[contracts.py<br/>节点契约]
        NodeDef[nodes.py]
    end

    subgraph Billing["计费域"]
        Billing[billing.py]
        Quota[quota.py]
        Contracts2[contracts.py<br/>业务合同]
        VAT[vat_invoice.py]
    end

    subgraph Compliance["合规域"]
        PIPL[pipl.py]
        DataClass[data_classification.py]
        Security[security_hardening.py]
    end

    subgraph Observability["可观测性"]
        Alerts[alert_rules.py]
        Notify[notification.py]
        Monitor[monitor.py]
        Webhook[webhooks.py]
    end

    subgraph Admin["管理域"]
        Admin[admin_console.py]
        RBAC2[rbac.py]
    end

    subgraph BI["报表域"]
        BIExport[bi_export.py]
        ModelExport[model_export.py]
    end

    Core --> Workflow
    Core --> Exec
    Core --> Billing
    Core --> Compliance
    Core --> Observability
    Compliance --> Admin
    Observability --> Admin
    Workflow --> BI
```

---

## 4. 数据模型 (PostgreSQL)

### 4.1 核心实体关系图

```mermaid
erDiagram
    Tenant ||--o{ UserMember : "has"
    Tenant ||--o{ Workflow : "owns"
    Tenant ||--o{ Template : "owns"
    Tenant ||--o{ Bill : "receives"
    Tenant ||--o{ WebhookSubscription : "subscribes"
    Tenant ||--o{ AuditEvent : "logs"
    Tenant ||--o{ NotificationConfig : "configures"
    Tenant ||--o{ AlertRule : "monitors"
    Tenant ||--o{ DsrRequest : "PIRs"
    Tenant ||--o{ DataSubjectRequest : "PIPL"

    Workflow ||--|| WorkflowVersion : "has"
    Workflow ||--o{ Run : "executes"
    Run ||--o{ NodeExecution : "contains"
    NodeExecution ||--o{ NodeExecutionLog : "logs"
    Run ||--o{ RunArtifact : "produces"
    NodeExecution ||--o{ NodeArtifact : "produces"

    Template ||--o{ TemplateVersion : "versions"
    Template ||--o{ TemplateRating : "rated"
    Template ||--o{ TemplateReviewLog : "reviewed"
    WorkflowVersion ||--|| Workflow : "belongs"

    Bill ||--o{ Invoice : "invoiced"
    Bill }o--|| SubscriptionPlan : "subscribed"
    Contract ||--o{ VatInvoice : "vat"

    User ||--o{ UserRoleAudit : "audit"
    RolePolicy }o--|| Tenant : "tenant_override"

    AuditEvent ||--o{ AuditChainCheckpoint : "checkpointed"

    WebhookSubscription ||--o{ WebhookDelivery : "delivers"
    AlertRule ||--o{ AlertInstance : "fires"
    AlertInstance ||--o{ AlertHistory : "history"
    AlertSilence ||--o{ AlertInstance : "silences"

    ApiKey ||--o{ Tenant : "auth"
    LockoutAccount ||--|| User : "locks"
    Vulnerability }o--|| Tenant : "tracked"
    CrossBorderTransfer }o--|| Tenant : "PIPL"
    ConsentRecord }o--|| User : "consent"
```

### 4.2 数据库迁移历史

| 版本 | 阶段 | 主要变更 |
|------|------|----------|
| 0001 | Phase 1 | 初始 schema (12 张表) |
| 0002 | Phase 2 | node_resource_usage |
| 0003 | Phase 4 | billing + invoices |
| 0004 | Phase 4 | contracts + vat_invoice |
| 0005 | Phase 5 | notifications (B23) |
| 0006 | Phase 5 | security (B25) |
| 0007 | Phase 5 | PIPL (B26) |
| 0008 | Phase 5 | alerts (B27) |
| 0009 | Phase 6 | RBAC (B28) |
| 0010 | Phase 6 | rbac 修补 (B29) |
| 0011 | Phase 6 | template_sharing (B31) |
| 0012 | Phase 7 | BI views (B33) |
| **0013** | **Phase 8** | **webhook_subscriptions + webhook_deliveries (B35)** |

### 4.3 BI 视图清单 (0012)

| 视图 | 来源 | 用途 |
|------|------|------|
| `v_bi_audit_recent` | audit_events | 近 90 天审计事件 (扁平化 JSONB) |
| `v_bi_run_summary` | runs | Run 汇总 (含 node_count / duration_ms) |
| `v_bi_usage_daily` | runs | 用量按日聚合 (run/duration/failed/success) |
| `v_bi_billing_summary` | bills | 账单汇总 |

---

## 5. 关键技术决策

### 5.1 选型理由

| 组件 | 选型 | 备选 | 理由 |
|------|------|------|------|
| 后端框架 | FastAPI | Flask / Django | 异步原生 + OpenAPI 自动生成 |
| ORM | SQLAlchemy 2.0 async | Tortoise / Piccolo | 成熟 + 异步 + 类型提示完善 |
| 数据库 | PostgreSQL 16 | MySQL | RLS + JSONB + CTE |
| 缓存 | Redis 7 | Memcached | Stream + Pub/Sub + Lua 原子 |
| 异步任务 | Celery | Dramatiq / RQ | 生态最广 + Beat 调度 |
| 对象存储 | MinIO / S3 | 本地文件 | 大产物 + 跨区复制 |
| 鉴权 | JWT (sub=user_id) | Session | 无状态 + 跨域 |
| 前端 | React + Vite | Next.js | 部署轻量 + SPA |
| 节点沙箱 | K8s Job | Docker / Firecracker | 隔离强 + 自动重启 |
| 通知 | Slack/WeCom/SMTP | 邮件全栈 | 客户集成习惯 |

### 5.2 安全模型

```mermaid
graph TB
    subgraph AuthN["认证 (AuthN)"]
        JWT[JWT sub=user_id<br/>HS256 签名]
        Refresh[Refresh Token<br/>7 天滚动]
        Lockout[5 分钟锁屏<br/>5 次失败]
    end

    subgraph AuthZ["授权 (AuthZ)"]
        RBAC[5×5×3 权限矩阵<br/>后端强制]
        Role[super_admin/<br/>tenant_admin/<br/>analyst/viewer]
    end

    subgraph DataProtection["数据保护"]
        RLS[PostgreSQL RLS<br/>tenant_id 隔离]
        Mask[字段脱敏<br/>4 级 × 28 字段]
        Hash[敏感字段 hash<br/>id_card_hash]
        CrossBorder[跨境审批<br/>4 种合法性基础]
    end

    subgraph Audit["审计"]
        Append[append-only 事件<br/>16 类]
        HMAC[HMAC 链<br/>链完整性]
        SIEM[SIEM 导出<br/>Splunk/QRadar]
    end

    subgraph Network["网络安全"]
        WAF[28 模式 WAF<br/>SQL/XSS/Path]
        IPRule[IP 白/黑名单<br/>租户级]
        RateLimit[100 req/60s<br/>滑动窗口]
    end

    AuthN --> AuthZ
    AuthZ --> DataProtection
    DataProtection --> Audit
    Network --> AuthN
```

### 5.3 可观测性矩阵

| 组件 | 指标 (Prometheus) | 日志 (Loki) | 追踪 (OTel) | 告警 (Alertmanager) |
|------|-------------------|-------------|-------------|---------------------|
| FastAPI | request_total / duration_seconds | 结构化 JSON | HTTP span | 5xx 率 > 5% |
| Celery Worker | task_total / duration | 任务日志 | Task span | 队列长度 > 1000 |
| PostgreSQL | connections / qps / locks | pg_log | DB span | 慢查询 > 5s |
| Redis | memory / hit_rate | - | - | OOM 风险 |
| Sandbox (K8s) | pod_restarts / cpu / mem | kubectl logs | Job span | OOMKilled > 3/min |
| Webhook | delivery_success_rate | webhook_sent | - | 失败率 > 10% |
| Audit | events_per_min | audit_log | - | 链断裂 |

---

## 6. 关键数据流

### 6.1 工作流执行流程

```mermaid
sequenceDiagram
    participant U as 用户 (前端)
    participant API as FastAPI
    participant DB as PostgreSQL
    participant Queue as Redis Stream
    participant Worker as Celery Worker
    participant S3 as MinIO/S3
    participant Hook as 租户 Webhook

    U->>API: POST /workflows/{id}/runs
    API->>DB: 创建 Run (status=pending) + N 个 NodeExecution (status=queued)
    API->>DB: 写 audit event (workflow_run_submit)
    API->>Queue: 投递到 Celery 队列
    API-->>U: 202 Accepted + run_id

    Queue->>Worker: 拉取 Run 任务
    Worker->>DB: 更新 Run.status=running
    loop 对每个节点
        Worker->>DB: 更新 NodeExecution.status=running
        Worker->>S3: 拉取输入产物
        Worker->>Worker: 执行节点逻辑
        Worker->>S3: 写入输出产物
        Worker->>DB: 更新 NodeExecution.status=success + 写日志
    end
    Worker->>DB: 更新 Run.status=success
    Worker->>DB: 写 audit event (workflow_run_complete)
    Worker->>Hook: 异步发布 webhook (run.completed)

    Note over U,Hook: 用户可订阅 webhook 接收完成通知
    Hook-->>U: HTTP POST + HMAC 签名
```

### 6.2 Webhook 投递流程

```mermaid
sequenceDiagram
    participant Trigger as 事件触发器
    participant API as publish_event
    participant DB as PostgreSQL
    participant Worker as Webhook Worker
    participant Tenant as 租户 endpoint

    Trigger->>API: publish_event(run.completed, payload)
    API->>DB: 查询匹配的 WebhookSubscription
    DB-->>API: N 个订阅
    loop 每个订阅
        API->>DB: 插入 WebhookDelivery (status=pending)
    end
    API-->>Trigger: PublishedEvent(enqueued_count=N)

    Note over Worker: 定时扫描 status=pending 的投递
    Worker->>DB: SELECT * FROM webhook_deliveries WHERE status='pending'
    loop 每条
        Worker->>Tenant: POST URL + HMAC 签名 + 5 个 header
        alt 2xx 响应
            Worker->>DB: UPDATE status=success, response_status=200
        else 4xx/5xx 或网络失败
            Worker->>DB: UPDATE status=retrying, scheduled_at=now+1min
            Note over Worker: 5 次指数退避后 status=failed
        end
    end
```

### 6.3 合规审计流 (PIPL DSR)

```mermaid
sequenceDiagram
    participant User as 用户
    participant API as /pipl/dsr
    participant DB as PostgreSQL
    participant Admin as 平台管理员
    participant Audit as 审计日志

    User->>API: POST /pipl/dsr {type: "delete", reason: "撤回同意"}
    API->>DB: 插入 DataSubjectRequest (status=pending, due_at=now+30d)
    API->>Audit: 写 audit event (pipl_dsr_submit)
    API-->>User: 202 + request_id

    Note over Admin: 30 天内审核
    Admin->>API: GET /admin/pipl/dsr?status=pending
    API->>DB: 查询待处理 DSR
    API-->>Admin: 列表
    Admin->>API: POST /admin/pipl/dsr/{id}/process {action: "approve"}
    API->>DB: 软删除用户数据 (status=approved)
    API->>DB: 匿名化 fields (id_card_hash)
    API->>Audit: 写 audit event (pipl_dsr_process)
    API-->>Admin: 200 + 清除结果摘要
```

---

## 7. 部署架构

### 7.1 生产部署 (Kubernetes)

```mermaid
graph TB
    subgraph K8s["Kubernetes Cluster"]
        subgraph NS1["ns: hscredit-prod"]
            Ingress[Ingress NGINX<br/>TLS 终止]
            API1[FastAPI Pod x3]
            API2[FastAPI Pod x3]
            API3[FastAPI Pod x3]
            Worker1[Celery Worker Pod x5]
            Worker2[Celery Worker Pod x5]
            Beat[Celery Beat Pod x1]
        end
        subgraph NS2["ns: hscredit-data"]
            PGMaster[(PostgreSQL Primary)]
            PGReplica[(PostgreSQL Replica x2)]
            RedisM[(Redis Master)]
            RedisS[(Redis Slave)]
            S3API[MinIO 4 节点]
        end
        subgraph NS3["ns: hscredit-obs"]
            Prom[Prometheus]
            AM[Alertmanager]
            Graf[Grafana]
            Loki[Loki]
        end
    end

    Ingress --> API1
    Ingress --> API2
    Ingress --> API3
    API1 --> PGMaster
    API1 --> RedisM
    API1 --> S3API
    Worker1 --> PGMaster
    Worker1 --> S3API
    Worker1 --> RedisM
    Beat --> PGMaster
    PGMaster -.复制.-> PGReplica
    RedisM -.复制.-> RedisS
```

### 7.2 本地开发

参见 [DEVELOPMENT.md](DEVELOPMENT.md):

- 后端: Python 3.11 + venv (`.venv/Scripts/python.exe`)
- 前端: Node.js 18+ + Vite
- 数据库: PostgreSQL 16 (Docker / 本地)
- 缓存: Redis 7
- 对象存储: MinIO (Docker)

启动命令:

```bash
make dev-up         # docker compose up
make backend-dev    # cd backend && ./.venv/Scripts/python.exe -m uvicorn hscredit_studio.main:app --reload --port 8003
make frontend-dev   # cd frontend && npm run dev
```

---

## 8. 性能预算

| 指标 | 当前 (v0.1) | 目标 (v0.2) | Phase 5 目标 |
|------|-------------|-------------|--------------|
| Run P50 端到端 (10 节点) | 60s | 90s (沙箱) | 60s (镜像优化) |
| API P95 响应 | 200ms | 200ms | 150ms |
| WebSocket 推送延迟 | <1s | <1s | <500ms |
| 多租户并发 | 10 | 50 | 200 |
| Webhook 投递 P95 | <2s | <2s | <1s |
| 审计事件写入吞吐 | 100/s | 1000/s | 5000/s |

性能优化方向:

- **缓存层**: Redis 缓存配额查询 (B19 用量)、节点契约 (B12)、权限矩阵 (B28)
- **批量 API**: Run 批量提交、NodeExecution 批量状态更新
- **数据库**: 连接池 (20 → 50), 读副本分担 BI 查询
- **沙箱**: 镜像层缓存 (lazy layer), 节点间共享依赖

---

## 9. 安全边界

### 9.1 信任域

```
┌─────────────────────────────────────────┐
│ 不可信域 (Internet)                       │
│   - 攻击者 (WAF / 限流保护)                │
│   - 客户端 (前端)                          │
│   - 第三方集成 (Slack/WeCom/SMTP)         │
└────────────┬────────────────────────────┘
             │ TLS 1.3 + JWT
             ▼
┌─────────────────────────────────────────┐
│ 半可信域 (DMZ)                             │
│   - K8s Ingress                           │
│   - 负载均衡                              │
└────────────┬────────────────────────────┘
             │ 网络策略 + mTLS
             ▼
┌─────────────────────────────────────────┐
│ 可信域 (核心)                              │
│   - API Pods (FastAPI)                   │
│   - Worker Pods (Celery)                 │
│   - 数据库 / Redis / S3                   │
└─────────────────────────────────────────┘
```

### 9.2 密钥管理

| 密钥类型 | 存储 | 轮转策略 |
|----------|------|----------|
| JWT Secret | 环境变量 + K8s Secret | 90 天 |
| 数据库密码 | K8s Secret + Vault | 180 天 |
| Webhook 签名密钥 | PostgreSQL (加密列) | 用户手动 |
| 加密数据密钥 | HSM (生产) / env (dev) | 1 年 |
| SMTP 密码 | K8s Secret | 90 天 |

---

## 10. 未来演进方向

| 方向 | 触发条件 | 优先级 |
|------|----------|--------|
| **多区域部署** | 海外客户接入 | P1 |
| **硬件 HSM** | 金融客户合同要求 | P0 |
| **节点插件市场** | 客户自研节点需求 | P2 |
| **联邦学习** | 跨租户数据合作 | P3 |
| **i18n 多语言** | 海外客户 | P2 |
| **GraphQL API** | 移动端 SDK 需求 | P3 |

---

## 附录 A: 术语表

| 术语 | 含义 |
|------|------|
| **租户 (Tenant)** | SaaS 客户单位, 数据完全隔离 |
| **工作流 (Workflow)** | 评分卡建模的节点编排 DAG |
| **Run** | 工作流的一次执行实例 |
| **节点 (Node)** | 工作流中的单个步骤 (数据读取 / 特征工程 / 模型训练 ...) |
| **节点执行 (NodeExecution)** | Run 中某个节点的执行记录 |
| **模板 (Template)** | 可复用的工作流定义 (含默认参数) |
| **配额 (Quota)** | 租户的用量上限 (Runs / Sandbox-hours / Storage) |
| **Webhook** | 平台向租户系统推送事件的 HTTP POST |
| **PMML** | 预测模型标记语言 (金融行业标准) |
| **ONNX** | 开放神经网络交换格式 |
| **DSR** | Data Subject Request (PIPL 用户权利请求) |

---

## 附录 B: 变更历史

| 日期 | 版本 | 主要变更 |
|------|------|----------|
| 2026-08-28 | v0.1.0 | 初版架构文档 (Phase 1-8 完工后) |
