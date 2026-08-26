# 部署指南

## 部署方式概览

| 环境 | 方式 | 触发 |
|---|---|---|
| 开发 | Docker Compose | 手动 |
| Staging | Kubernetes + Helm | push 到 main |
| Production | Kubernetes + Helm | 手动审批 |

## 1. 开发环境部署

```bash
make dev-up
make migrate
make seed
make backend-dev
make frontend-dev
```

访问 http://localhost:3000

## 2. Staging 部署

### 自动部署

push 到 `main` 分支自动触发：

```bash
git checkout main
git pull
git merge feature/my-feature
git push origin main
# GitHub Actions 自动跑 CI + CD
```

### 手动部署

```bash
make helm-install-staging
```

### 验证

```bash
# 健康检查
curl https://staging.hscredit.example.com/healthz

# 查看 Pod 状态
kubectl get pods -n hscredit-staging

# 查看日志
kubectl logs -n hscredit-staging -l app.kubernetes.io/component=api -f
```

## 3. Production 部署

### 前置条件

- [ ] Staging 至少跑 1 周无重大问题
- [ ] Phase 1 验收清单全部完成
- [ ] 安全扫描无高危
- [ ] 备份已配置
- [ ] 监控已配置
- [ ] 域名 + TLS 证书已就绪
- [ ] DBA 已审核数据库迁移

### 部署步骤

```bash
# 1. 准备生产配置
# （已有 values-production.yaml，需根据实际环境调整）

# 2. 部署（需手动审批）
make helm-install-prod

# 3. 验证
make helm-test-prod

# 4. 配置 DNS
# 将 app.hscredit.example.com 指向 K8s Ingress IP

# 5. 配置 TLS
# 使用 cert-manager 自动签发 Let's Encrypt 证书
```

### 蓝绿部署

```bash
# 部署到 green
helm upgrade --install hscredit-green charts/hscredit-studio \
  -f charts/hscredit-studio/values-production.yaml \
  --set deployment.selector.matchLabels.version=green \
  --namespace hscredit-prod --create-namespace

# 烟雾测试
kubectl exec -n hscredit-prod deploy/hscredit-green -- \
  curl -f http://localhost:8000/healthz

# 切换流量
kubectl patch service hscredit-studio-api -n hscredit-prod -p \
  '{"spec":{"selector":{"version":"green"}}}'

# 观察 5 分钟
sleep 300

# 移除 blue
helm uninstall hscredit-blue -n hscredit-prod || true
```

### 回滚

```bash
# 查看历史
helm history hscredit-prod -n hscredit-prod

# 回滚到上一个版本
helm rollback hscredit-prod -n hscredit-prod

# 或指定版本
helm rollback hscredit-prod 3 -n hscredit-prod
```

## 4. 数据库迁移

迁移通过 Helm Hook 在 `helm upgrade` 时自动执行。

### 手动迁移（紧急情况）

```bash
# 进入后端 Pod
kubectl exec -it -n hscredit-prod deploy/hscredit-studio-api -- /bin/sh

# 在 Pod 内
alembic upgrade head

# 退出
exit
```

### 迁移前检查

```bash
# 1. 备份数据库
./scripts/backup.sh

# 2. dry-run
cd backend && alembic upgrade head --sql > /tmp/migration.sql
cat /tmp/migration.sql | less

# 3. 在 staging 验证
make migrate

# 4. 生产部署
```

## 5. 监控与告警

- Prometheus: http://prometheus.hscredit.example.com
- Grafana: http://grafana.hscredit.example.com
- Alertmanager: http://alertmanager.hscredit.example.com

### 关键看板

- 系统总览
- 工作流执行
- 数据库监控
- 业务指标

## 6. 备份

### 自动备份

```bash
# 每日凌晨 2 点自动备份
crontab: 0 2 * * * /opt/hscredit/scripts/backup.sh
```

### 手动备份

```bash
./scripts/backup.sh
# 输出: /tmp/backups/hscredit_20260825_020000.dump
```

### 恢复演练

每季度一次：

```bash
# 1. 在 staging 环境启动空 PG
# 2. 从 S3 拉取最新备份
# 3. pg_restore 还原
# 4. 验证数据完整性
# 5. 跑集成测试
# 6. 记录演练结果
```

## 7. 灾备

### L4 区域故障切换

详见 [docs/design/12-deployment-architecture.md 第 12.11.3 节](../hscredit/docs/design/12-deployment-architecture.md)

```
1. 确认主区域不可用
2. DNS 健康检查失败
3. 决策（工程总监）
4. DR 启动（K8s 自动扩容）
5. DNS 切到 DR（TTL 60s）
6. 验证 + 通知
7. 后续：修复主区域 → 反向同步 → 切回
```

## 8. 性能调优

### HPA 配置

```yaml
# charts/hscredit-studio/values-production.yaml
api:
  autoscaling:
    enabled: true
    minReplicas: 3
    maxReplicas: 20
  resources:
    requests: { cpu: 500m, memory: 1Gi }
```

### 数据库调优

参见 [docs/design/09-database-design.md 第 9.10 节](../hscredit/docs/design/09-database-design.md)

### 缓存策略

参见 [docs/design/06-non-functional.md 第 6.6 节](../hscredit/docs/design/06-non-functional.md)

## 9. 安全加固

- [ ] TLS 1.3 全站
- [ ] CORS 白名单
- [ ] 速率限制
- [ ] RLS 启用
- [ ] 密钥用 Vault
- [ ] 镜像扫描（trivy）
- [ ] 依赖审计（pip-audit）
- [ ] 渗透测试（季度）

## 10. 合规

### 等保测评

- Phase 3 末启动
- Phase 4 完成测评
- 每年复测

### 审计日志

- `audit_events` 表保留 7 年
- `security_events` 保留 3 年
- 不可篡改（append-only）

### 数据主权

- 国内数据不出境
- 跨境需用户明示同意
- 加密存储 + 加密传输

## 常见问题

### Q: 部署失败怎么办？

```bash
# 1. 查看 Helm 历史
helm history hscredit-prod -n hscredit-prod

# 2. 回滚
helm rollback hscredit-prod -n hscredit-prod

# 3. 查看日志
kubectl logs -n hscredit-prod -l app.kubernetes.io/component=api --tail=100

# 4. 检查事件
kubectl get events -n hscredit-prod --sort-by='.lastTimestamp' | head -20
```

### Q: 数据库连接数耗尽？

```bash
# 1. 查看当前连接
psql -c "SELECT count(*) FROM pg_stat_activity;"

# 2. 杀掉空闲连接
psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < now() - interval '10 minutes';"

# 3. 临时调大 pgbouncer pool
```

### Q: 节点任务积压？

```bash
# 1. 查看队列长度
kubectl exec -n hscredit-prod deploy/hscredit-studio-api -- \
  redis-cli -h redis LLEN celery

# 2. 临时扩容 Worker
kubectl scale -n hscredit-prod deploy/hscredit-studio-worker --replicas=8
```
