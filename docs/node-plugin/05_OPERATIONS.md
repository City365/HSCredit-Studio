# 节点可插拔改造 — 运维文档

> 本文档描述部署、监控、故障排查相关的运维知识.

---

## 1. 部署架构

### 1.1 进程拓扑

```
┌─────────────────────────────────────────────────────────────┐
│                     Load Balancer                            │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
   ┌────▼────┐  ┌────▼────┐  ┌────▼────┐
   │ Uvicorn │  │ Uvicorn │  │ Uvicorn │  ← FastAPI (3 replicas)
   │ 8003    │  │ 8003    │  │ 8003    │
   └────┬────┘  └────┬────┘  └────┬────┘
        │            │            │
        └────────────┼────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
   ┌────▼────┐  ┌────▼────┐  ┌────▼────┐
   │ Celery  │  │ Celery  │  │ Celery  │  ← Worker (3+ replicas)
   │ Worker  │  │ Worker  │  │ Worker  │
   └────┬────┘  └────┬────┘  └────┬────┘
        │            │            │
        └────────────┼────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
   ┌────▼────┐  ┌────▼────┐  ┌────▼────┐
   │ Sandbox │  │ Sandbox │  │ Sandbox │  ← User Code Sandbox (subprocess)
   │ Pool    │  │ Pool    │  │ Pool    │     (每节点运行一个子进程)
   └─────────┘  └─────────┘  └─────────┘
                     │
   ┌─────────────────▼─────────────────┐
   │       PostgreSQL / Redis / MinIO   │
   └─────────────────────────────────────┘
```

### 1.2 关键配置项

**后端 `.env`** (新增):
```bash
# 用户代码沙箱
USER_SANDBOX_TIMEOUT_SEC=60
USER_SANDBOX_MEMORY_MB=2048        # 2 GiB
USER_SANDBOX_CPU_SEC=60             # wall clock
USER_SANDBOX_CPU_COUNT=1
USER_SANDBOX_OPEN_FILE_LIMIT=64
USER_SANDBOX_MAX_PID=32
USER_SANDBOX_DIR_TEMP=/tmp/hscredit-sandbox
USER_SANDBOX_KEEP_TEMP=false        # 调试时设为 true

# 节点管理
NODE_PLUGIN_LOCK_TTL_SEC=300         # 编辑锁 5 min
NODE_PLUGIN_LOCK_HEARTBEAT_SEC=120  # 心跳 2 min
NODE_PLUGIN_DRAFT_AUTOSAVE_SEC=5    # 草稿自动保存 5s
NODE_PLUGIN_DRAFT_DEBOUNCE_MS=500   # AST 校验防抖
NODE_PLUGIN_MAX_DRAFT_AGE_DAYS=30   # 草稿保留
NODE_PLUGIN_MAX_TEST_RUN_AGE_DAYS=90 # 试运行记录保留

# 试运行频率限制 (按租户)
NODE_PLUGIN_TEST_RUN_RATE_LIMIT=10   # 每分钟最多 10 次

# 自定义节点代码大小限制
NODE_PLUGIN_MAX_CODE_SIZE_KB=500
```

### 1.3 依赖升级

```toml
# backend/pyproject.toml 依赖新增
dependencies = [
    ...
    # Phase 6 B36 节点可插拔
    "RestrictedPython>=6.0",   # AST 黑名单 (可选 [plugin] extra)
]
```

---

## 2. 监控指标 (Prometheus)

### 2.1 关键指标

```python
# backend/hscredit_studio/services/metrics.py (新增)

from prometheus_client import Counter, Histogram, Gauge

# 自定义节点相关
custom_node_created_total = Counter(
    'hscredit_custom_node_created_total',
    'Total custom nodes created',
    ['tenant_id', 'visibility']
)

custom_node_test_run_total = Counter(
    'hscredit_custom_node_test_run_total',
    'Total custom node test runs',
    ['tenant_id', 'status']  # status: success / failed / timeout / oom
)

custom_node_test_run_duration = Histogram(
    'hscredit_custom_node_test_run_duration_seconds',
    'Custom node test run duration',
    ['tenant_id', 'status'],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60]
)

sandbox_resource_usage = Histogram(
    'hscredit_sandbox_resource_usage',
    'Sandbox resource usage',
    ['resource'],  # cpu_seconds / mem_peak_mb
    buckets=[...]
)

custom_node_lock_count = Gauge(
    'hscredit_custom_node_lock_count',
    'Currently locked custom nodes'
)

node_validation_failures_total = Counter(
    'hscredit_node_validation_failures_total',
    'AST validation failures',
    ['rule']  # import_blocked / builtin_blocked / must_inherit_basemethod / ...
)
```

### 2.2 告警规则

```yaml
# alerts/custom_nodes.yaml
groups:
- name: custom_nodes
  rules:
  - alert: CustomNodeTestRunFailureRate
    expr: |
      rate(hscredit_custom_node_test_run_total{status="failed"}[5m])
      / rate(hscredit_custom_node_test_run_total[5m])
      > 0.5
    for: 10m
    annotations:
      summary: "试运行失败率 > 50%"

  - alert: CustomNodeSandboxTimeout
    expr: |
      rate(hscredit_custom_node_test_run_total{status="timeout"}[5m]) > 0.5
    for: 5m
    annotations:
      summary: "沙箱超时频繁"

  - alert: CustomNodeHighMemoryUsage
    expr: |
      histogram_quantile(0.95,
        hscredit_sandbox_resource_usage{resource="mem_peak_mb"}
      ) > 1800
    for: 5m
    annotations:
      summary: "P95 内存 > 1.8GB"

  - alert: NodeEditLockStuck
    expr: hscredit_custom_node_lock_count > 50
    for: 30m
    annotations:
      summary: "编辑锁未释放 > 50 个"
```

---

## 3. 日志规范

### 3.1 结构化日志字段

```python
# 所有自定义节点相关日志统一格式
logger.info(
    "custom_node_created",
    custom_node_id=str(cn_id),
    tenant_id=str(tenant_id),
    node_type=node_type,
    version_number=1,
    user_id=str(user.user_id),
)

logger.info(
    "custom_node_test_run_started",
    custom_node_id=str(cn_id),
    test_run_id=str(tr_id),
    node_type=node_type,
    version_id=str(vid),
)

logger.info(
    "custom_node_test_run_completed",
    test_run_id=str(tr_id),
    status=status,  # success / failed / timeout / oom
    duration_ms=duration,
    cpu_seconds=cpu,
    mem_peak_mb=mem,
)

logger.warning(
    "custom_node_validation_failed",
    custom_node_id=str(cn_id),
    rules=failed_rules,  # ['import_blocked', 'builtin_blocked']
    issues_count=len(issues),
)
```

### 3.2 关键日志位置

| 路径 | 用途 |
|---|---|
| `logs/app.log` | 主日志 (uvicorn) |
| `logs/celery.log` | Worker 日志 |
| `logs/sandbox.log` | 沙箱子进程日志 (含用户代码 stdout/stderr) |

---

## 4. 故障排查 (Runbook)

### 4.1 用户报告 "试运行一直超时"

**排查步骤**:

1. 查日志 `sandbox.log`, 找 `status=timeout`
2. 确认超时配置: `USER_SANDBOX_TIMEOUT_SEC=60`
3. 检查用户代码: 是否有死循环 / IO 阻塞?
4. 试运行不调用 `setrlimit(RLIMIT_CPU)` 也能终止 — subprocess `proc.communicate(timeout=)` 兜底
5. 升级方案: 增加 `USER_SANDBOX_TIMEOUT_SEC` (按租户覆盖)

**临时解决方案**: 给该租户临时提升到 300s, 联系用户优化代码.

### 4.2 用户报告 "自定义节点消失"

**排查步骤**:

1. 查 `custom_nodes` 表 `deleted_at`: 是否被误删?
2. 查 `enabled` 字段: 是否被禁用了?
3. 查 `visibility`: 跨租户吗? 如果是 `public`, 是不是被 `private` 改了?
4. 查 `node_definitions`: 自定义节点是否正确同步到 NodeRegistry?
5. 后端日志搜 `node_loader` 找编译错误

**恢复**: 软删除可逆 (`UPDATE custom_nodes SET deleted_at=NULL`); 硬删除不可逆.

### 4.3 "保存新版本失败"

**排查步骤**:

1. 看返回的 HTTP code:
   - 400 → 静态校验失败, 提示用户修复
   - 409 → node_type 重名, 提示用户改名
   - 422 → contract 字段缺失/格式错, 看详细 issues
2. 查 DB `custom_node_versions`: 是否创建了但 commit 失败?
3. 查 DB `node_definition_drafts`: 草稿是否被锁定?
4. 查日志: `custom_node_version_create_failed`

### 4.4 "试运行成功, 但 workflow Run 失败"

**排查步骤**:

1. 确认 `node_definitions.is_custom=true` 且 `enabled=true`
2. 确认 `custom_nodes.current_version_number` 是最新版本号
3. 查 Celery worker 日志, 确认 worker 能加载自定义节点
4. 查 Redis pub/sub: `node:reload` 是否有发布? 各 worker 是否订阅?
5. 重启 worker 强制重载 (`celery -A hscredit_studio.celery_app worker --reload`)

### 4.5 "沙箱内存超限 (OOM)"

**排查步骤**:

1. 查 `node_resource_usage` 表 `mem_peak_mb`
2. 增加 `USER_SANDBOX_MEMORY_MB` (按租户覆盖)
3. 检查代码是否用了 `pandas.read_csv` 读大文件, 建议分块
4. 检查代码是否创建了大对象 (建议 gc.collect())

---

## 5. 数据库维护

### 5.1 定期清理任务 (Celery beat)

```python
# backend/hscredit_studio/services/maintenance.py (新增)

@celery_app.task(name="hscredit_studio.maintenance.cleanup_drafts")
def cleanup_old_drafts():
    """每 6 小时清理 30 天前的草稿."""
    cutoff = datetime.utcnow() - timedelta(days=30)
    async with session_scope() as session:
        await session.execute(
            delete(NodeDefinitionDraft).where(
                NodeDefinitionDraft.updated_at < cutoff
            )
        )
        await session.commit()


@celery_app.task(name="hscredit_studio.maintenance.cleanup_test_runs")
def cleanup_old_test_runs():
    """每天清理 90 天前的试运行记录."""
    cutoff = datetime.utcnow() - timedelta(days=90)
    async with session_scope() as session:
        await session.execute(
            delete(CustomNodeTestRun).where(
                CustomNodeTestRun.created_at < cutoff
            )
        )
        await session.commit()


@celery_app.task(name="hscredit_studio.maintenance.cleanup_expired_locks")
def cleanup_expired_locks():
    """每 5 分钟清理过期的编辑锁."""
    now = datetime.utcnow()
    async with session_scope() as session:
        await session.execute(
            delete(NodeDefinitionLock).where(
                NodeDefinitionLock.expires_at < now
            )
        )
        await session.commit()
```

**Celery beat 调度**:

```python
celery_app.conf.beat_schedule = {
    "cleanup-drafts": {
        "task": "hscredit_studio.maintenance.cleanup_drafts",
        "schedule": 6 * 60 * 60,  # 6 hours
    },
    "cleanup-test-runs": {
        "task": "hscredit_studio.maintenance.cleanup_test_runs",
        "schedule": 24 * 60 * 60,  # 24 hours
    },
    "cleanup-expired-locks": {
        "task": "hscredit_studio.maintenance.cleanup_expired_locks",
        "schedule": 5 * 60,  # 5 minutes
    },
}
```

### 5.2 软删除清理任务 (30 天后硬删)

```python
@celery_app.task(name="hscredit_studio.maintenance.hard_delete_old_custom_nodes")
def hard_delete_old_custom_nodes():
    """每周清理 30 天前软删除的自定义节点."""
    cutoff = datetime.utcnow() - timedelta(days=30)
    async with session_scope() as session:
        # 先确认没有 workflow 引用
        ...
        # 硬删 (cascade delete versions + test_runs)
        await session.execute(
            delete(CustomNode).where(
                and_(
                    CustomNode.deleted_at.isnot(None),
                    CustomNode.deleted_at < cutoff,
                )
            )
        )
        await session.commit()
```

---

## 6. 安全审计

### 6.1 审计日志 (audit_events)

所有自定义节点操作记录到 `audit_events` 表 (Phase 5 B25):

| action | details |
|---|---|
| `custom_node.create` | user_id / node_type / visibility |
| `custom_node.update_meta` | 变更字段前后值 |
| `custom_node.update_code` | 新版本号 / change_summary |
| `custom_node.rollback` | 从版本 → 当前版本 |
| `custom_node.delete` | 软删除标志 |
| `custom_node.test_run` | test_run_id / status / duration |
| `custom_node.lock_acquire` / `lock_release` | user_id / lock_id |
| `custom_node.enabled_change` | enabled 前后值 |

### 6.2 代码审计

定期扫描:
- 自定义节点代码字符串搜敏感关键字 (`TODO: 改` `XXX: 临时`)
- 检测 `print()` / `console.log()` 残留 (调试代码)
- 检测 `assert` 残留 (生产代码不应有)

### 6.3 违规处理

发现违规代码 (如绕过 AST 黑名单):
1. 立即禁用该 custom_node (`enabled=false`)
2. 通知 super_admin
3. 通知租户管理员
4. 审计日志记录

---

## 7. 容量规划

### 7.1 数据库大小估算

假设每个租户平均 50 个自定义节点:

| 表 | 行数 | 单行大小 | 总大小 |
|---|---|---|---|
| `custom_nodes` | 50 × 租户数 | ~10 KB | 50 × 10 KB = 500 KB/租户 |
| `custom_node_versions` | 50 × 节点 × 100 版本 | ~30 KB | 50 × 100 × 30 = 150 MB/租户 |
| `custom_node_test_runs` | 50 × 节点 × 1000 次 | ~2 KB | 50 × 1000 × 2 = 100 MB/租户 |
| `node_definition_drafts` | 50 × 节点 × 1 | ~30 KB | 50 × 30 = 1.5 MB/租户 |

**每租户总**: ~250 MB. 100 租户 = 25 GB. 1000 租户 = 250 GB.

### 7.2 沙箱并发估算

假设:
- 每个试运行耗时 5s
- 每个 workflow run 平均 10 个自定义节点
- 平均 QPS = 1 run/s

并发沙箱数 = 1 × 10 = **10 个进程**

资源消耗: 10 × 2GB = **20 GB RAM** (仅沙箱)

建议: 沙箱 worker 独立部署, 不与 API 服务共享资源.

---

## 8. 升级与迁移

### 8.1 升级流程

1. alembic upgrade head (DB schema)
2. 重启 Celery workers (加载新 NodeRegistry)
3. 重启 Uvicorn (加载新 API)
4. 通知前端部署新版本

### 8.2 回滚

1. alembic downgrade -1 (DB schema)
2. 回滚代码到上一个 git tag
3. 重启所有服务

---

## 9. 联系与升级

文档维护人: Backend Team
Slack 频道: #hscredit-platform
升级窗口: 每周三 14:00-16:00 (UTC+8)
