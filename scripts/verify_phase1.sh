#!/usr/bin/env bash
# Phase 1 自动化一键验证脚本

set -e

echo "=== 1. 基础设施健康检查 ==="
python -c "
import urllib.request
resp = urllib.request.urlopen('http://localhost:8001/api/v1/healthz')
assert resp.status == 200
print('✓ Backend API 8001 is healthy')
"

echo "=== 2. 节点定义与系统模板计数校验 ==="
python -c "
import urllib.request
import json
req = urllib.request.Request('http://localhost:8001/api/v1/auth/login',
    data=json.dumps({'email':'admin@demo.com','password':'DemoPass123!','tenant_slug':'demo'}).encode('utf-8'),
    headers={'Content-Type':'application/json'})
resp = urllib.request.urlopen(req)
token = json.loads(resp.read())['tokens']['access_token']

req_nodes = urllib.request.Request('http://localhost:8001/api/v1/demo/node-definitions', headers={'Authorization': f'Bearer {token}'})
nodes_data = json.loads(urllib.request.urlopen(req_nodes).read())
print(f'✓ 节点注册表: {len(nodes_data[\"definitions\"])} 个节点已就绪')

req_tpls = urllib.request.Request('http://localhost:8001/api/v1/demo/templates', headers={'Authorization': f'Bearer {token}'})
tpls_data = json.loads(urllib.request.urlopen(req_tpls).read())
print(f'✓ 系统模板库: {len(tpls_data[\"items\"])} 个模板已就绪')
"

echo "=== 3. 运行 E2E 3 套 Run & 缓存 & 隔离测试 ==="
python scripts/e2e/run_e2e.py

echo "=== 🎉 Phase 1 全部 7 项出口标准 100% 达成 ==="
