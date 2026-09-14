# 节点可插拔功能演示 (Walkthrough)

> 本文档用 **真实 E2E 输出 + 截图占位 + 终端会话** 演示 Phase 6 B36 节点可插拔功能的完整闭环.
>
> 适用版本: v0.1.x · 最后验证: 2026-09-14

---

## 演示路径 (5 步)

1. **节点库总览** — 列出全部 78 个节点 (76 系统 + 2 自定义)
2. **创建一个新自定义节点** — 5 步向导
3. **编辑代码 (Monaco Editor)** — AST 实时校验
4. **试运行** — 沙箱执行, 拿到 outputs
5. **回滚到旧版本** — 版本管理

下面每一步附:
- ASCII 截图 (可视化结构)
- 真实 E2E 命令 / 响应 (可复现)
- 后端日志片段 (展示内部行为)

---

## 第 1 步: 节点库总览

### 1.1 访问 `/nodes` 页面

浏览器路径: `http://localhost:3000/nodes` (前端 dev) 或 `https://app.hscredit.example.com/nodes` (生产).

页面结构:

```
┌──────────────────────────────────────────────────────────────────────┐
│ ☰  HSCredit Studio                          admin@demo.com [登出]    │
├──────────────────────────────────────────────────────────────────────┤
│ ⌂ 工作流  ▶ 运行  📊 监控  📚 模板  🧩 节点管理  ...                  │
├──────────────────────────────────────────────────────────────────────┤
│  节点管理                                                            │
│                                                                      │
│  [系统节点 (76)] [自定义节点 (2)]  ← 双 Tab 切换                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ 节点类型       │ 名称       │ 分类       │ 状态  │ 来源 │ ... │   │
│  ├──────────────────────────────────────────────────────────────┤   │
│  │ missing_rate   │ 缺失率     │ EDA        │ 🟢   │ 系统 │     │   │
│  │ standard_scaler│ 标准差标准化│ 特征工程   │ 🟢   │ 系统 │     │   │
│  │ woe_binning    │ WOE 分箱  │ 特征工程   │ 🟢   │ 系统 │     │   │
│  │ ... 76 行 ...  │           │            │      │      │     │   │
│  └──────────────────────────────────────────────────────────────┘   │
│  [+ 新建自定义节点]  [⚡ 同步系统节点 (super_admin)]                  │
└──────────────────────────────────────────────────────────────────────┘
```

### 1.2 真实 E2E 输出

```bash
$ python scripts/e2e/run_e2e_phase6_b36.py

============================================================
🚀 Phase 6 B36 节点可插拔 E2E 验收
============================================================
[✓] admin 登录成功 (admin@demo.com)
[ℹ] viewer 登录跳过: Login failed: 401 ...  (本 DB 未 seed viewer)

── 第 1 部分: 系统节点 ──
[✓] 列出节点: 总数=78, 系统=76, 自定义=2
[✓] 节点详情: iv_analysis, category=EDA
[✓] 分类筛选: 18 个特征工程节点
[✓] 搜索命中: 3 个 (search='missing')
[✓] 启停切换: eda_overview ✓
[✓] 元数据更新: eda_overview description 已变更
[✓] 系统节点同步端点可达 ✓
```

**关键点**: 76 个系统节点 = 衡枢真信评分卡工具箱的全量建模能力 + 自定义扩展点.

---

## 第 2 步: 创建自定义节点 (5 步向导)

### 2.1 入口: `/nodes/new`

```
┌──────────────────────────────────────────────────────────────────────┐
│ ← 返回    🆕 新增自定义节点                                          │
├──────────────────────────────────────────────────────────────────────┤
│  ● 起点选择 ── ○ 基础信息 ── ○ 代码编辑 ── ○ 试运行 ── ○ 确认保存    │
│                                                                      │
│  ┌─ 选择起点 ─────────────────────────────────────────────────────┐  │
│  │ 选择起点:  [🆕 从空白创建          ▼]                          │  │
│  │   或       [📋 从系统节点复制]                                  │  │
│  │                                                              │  │
│  │                              [下一步 →]                       │  │
│  └──────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 基础信息 (Step 2)

用户填:

| 字段 | 值 | 验证规则 |
|---|---|---|
| `node_type` | `my_filter` | 小写字母/数字/下划线, 字母开头 |
| `name` | `我的过滤器节点` | 1-128 字符 |
| `category` | `特征工程` | 7 个固定分类 |
| `icon` | `🛠️` | emoji |
| `visibility` | `private` | private/tenant/public |

### 2.3 代码编辑 (Step 3) — Monaco Editor

模板自动预填:

```python
from hscredit_studio.nodes.base import BaseNode
from hscredit_studio.schemas.node_contract import (
    NodeContract, PortSchema, ParamSpec
)

class MyNode(BaseNode):
    contract = NodeContract(
        node_type='my_filter',
        category='特征工程',
        name='我的过滤器节点',
        inputs=[PortSchema(name='df', type='Any', required=True)],
        outputs=[PortSchema(name='result', type='Any')],
        params=[ParamSpec(name='threshold', type='float',
                          label='阈值', default=0.5)],
    )

    def run(self, inputs, params):
        df = inputs['df']
        threshold = params.get('threshold', 0.5)
        return {'result': df[df['score'] > threshold]}
```

**实时校验 squiggle** (右上角 Monaco markers):

| 错误类型 | 触发 | 显示 |
|---|---|---|
| `blocked_import` | `import os` | ❌ 红波浪线 + "import_blocked: os 在黑名单中" |
| `no_basenoide_class` | 没继承 BaseNode | ❌ 整文件红 |
| `no_run_method` | 没 `def run` | ⚠️ 黄波浪线 |
| `param_label_missing` | ParamSpec 没 `label=` | ⚠️ 黄波浪线 |

### 2.4 试运行 (Step 4)

(本步在新节点向导里是**预告**,真正试运行到编辑页.)

### 2.5 确认保存 (Step 5)

```
┌── 节点摘要 ─────────────────────────────────────┐
│ 类型: my_filter                                │
│ 名称: 我的过滤器节点                           │
│ 分类: 特征工程                                 │
│ 可见性: private                                │
│ 代码长度: 728 字符                              │
│                                                  │
│  [← 上一步]   [✅ 创建节点]                    │
└──────────────────────────────────────────────────┘
```

### 2.6 真实 E2E 输出 (后端)

```bash
[✓] 创建自定义节点: id=ee406a4c..., v1 自动创建 ✓
[✓] 列出自定义节点: total=3
[✓] 自定义节点详情: current_version=1
```

**后端响应** (curl 复现):

```bash
$ curl -X POST http://localhost:8003/api/v1/demo/custom-nodes \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d @payload.json

HTTP/1.1 201 Created
{
  "custom_node_id": "ee406a4c-...-...",
  "tenant_id": "87cb252d-...",
  "node_type": "e2e_b36_xxxxxxxx",
  "name": "E2E 翻倍节点",
  "category": "特征工程",
  "enabled": true,
  "current_version_number": 1,
  "test_run_count": 0,
  "created_at": "2026-09-14T02:23:14.123Z",
  ...
}
```

---

## 第 3 步: 编辑代码 (Monaco)

### 3.1 进入编辑页 `/nodes/{id}/edit`

```
┌──────────────────────────────────────────────────────────────────────┐
│ ← 返回  🧪 E2E 翻倍节点 [自定义] e2e_b36_xxxxxxxx [v3] [🟢启用]    │
│                                          [切换版本 ▼] [▶ 试运行]      │
│                                          [💾 保存版本] [🗑 删除]      │
├─────────────────────────────────────────────────────────────────┬─┤
│ Python Code                                          [校验通过 ✓] │ │
│ 1  from hscredit_studio.nodes.base import BaseNode           │C│ │
│ 2  from hscredit_studio.schemas.node_contract import (...    │o│ │
│ 3                                                          │n│ │
│ 4  class Doubler(BaseNode):                                │t│ │
│ 5      contract = NodeContract(                            │r│ │
│ 6          node_type='e2e_b36_xxxxxxxx',                   │a│ │
│ ...                                                        │c│ │
│ 15     def run(self, inputs, params):                     │t│ │
│ 16         return {'result': inputs['x'] * params.get('factor', 2)}│ │ │
│                                                                │P│ │
│ [Monaco 编辑器, 深色主题, Python 语法高亮 + 自动补全]          │r│ │
│                                                                │e│ │
│                                                                │v│ │
└─────────────────────────────────────────────────────────────────┴─┘
```

### 3.2 编辑锁 (幕后)

进入页面瞬间, 前端 hook 触发:

```
[POST /custom-nodes/{id}/lock] → lock_id=1d9f720a...
                                 locked_by=admin_user_id
                                 expires_at=2026-09-14T02:25:14Z

(每 2 分钟) → [POST /custom-nodes/{id}/lock/heartbeat] → expires_at+2min
(离开页面) → [DELETE /custom-nodes/{id}/lock] → 204
```

**防抖自动保存草稿** (5s):

```
(用户停止输入 5 秒) → [PUT /custom-nodes/{id}/draft]
                     {code: "...", validation_status: "draft"}
                     → 200, draft_id 返回
```

### 3.3 提交新版本

点 [💾 保存版本] → 弹窗要求填"变更说明":

```
┌── 保存新版本 ──────────────────────────────┐
│ ℹ 保存后会创建新版本 (旧版本保留, 可回滚) │
│                                            │
│ 本次变更说明 (必填)                        │
│ ┌────────────────────────────────────────┐ │
│ │ E2E v2 - factor 改为 3                 │ │
│ └────────────────────────────────────────┘ │
│                          [取消] [确定]    │
└────────────────────────────────────────────┘
```

### 3.4 真实 E2E 输出

```bash
[✓] 提交 v2: version_id=54389430...
[✓] 版本列表: total=2
[✓] 版本详情: v2 - E2E v2 - factor 改为 3
```

**版本表** (DB):

| version_number | code | change_summary | created_at |
|---|---|---|---|
| 1 | `... factor=2 ...` | (初版) | 2026-09-14T02:23:14Z |
| 2 | `... factor=3 ...` | E2E v2 - factor 改为 3 | 2026-09-14T02:23:18Z |

---

## 第 4 步: 试运行 (沙箱执行)

### 4.1 入口: `/nodes/{id}/test`

```
┌──────────────────────────────────────────────────────────────────────┐
│ ← 返回  🧪 试运行: E2E 翻倍节点 (v3)                                │
├──────────────────────────────────────────────────────────────────────┤
│ 输入数据:                                                            │
│ ┌──────────────────────────────────────────────────────────────────┐ │
│ │ {                                                                │ │
│ │   "x": 5                                                         │ │
│ │ }                                                                │ │
│ └──────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│ 参数:                                                                │
│ ┌──────────────────────────────────────────────────────────────────┐ │
│ │ {                                                                │ │
│ │   "factor": 2                                                    │ │
│ │ }                                                                │ │
│ └──────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│ [▶ 试运行]                                                          │
│                                                                      │
│ ── 输出 ────────────────────────────────────────────────────────────│
│ 状态: ✅ success                                                     │
│ 耗时: 3750 ms                                                        │
│ 内存峰值: 0.0 MB                                                     │
│                                                                      │
│ outputs:                                                             │
│ ┌──────────────────────────────────────────────────────────────────┐ │
│ │ {                                                                │ │
│ │   "result": 10                                                   │ │
│ │ }                                                                │ │
│ └──────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.2 真实 E2E 输出

```bash
[✓] 沙箱试运行: status=success,
    outputs={'result': 10},
    duration=3750ms

[✓] 沙箱超时拦截: status=timeout, code=SANDBOX_TIMEOUT  ← 死循环
[✓] 沙箱黑名单拦截: status=failed, code=E_VALIDATION_ERROR  ← import os
```

### 4.3 沙箱内部行为 (后端日志)

```log
[INFO] user_sandbox_started node_type=e2e_b36_xxxxxxxx timeout_sec=30
[INFO] restricted_python_compile ast_nodes=87 duration_ms=42
[INFO] subprocess_spawned pid=12345 venv_python=/backend/.venv/Scripts/python.exe
[INFO] user_code_executed duration_ms=3708 outputs={'result': 10}
[INFO] custom_node_test_run_recorded status=success duration_ms=3750
```

**沙箱关键点**:
- ✅ **子进程隔离** (`setrlimit` 限制 CPU/AS/文件数/子进程数)
- ✅ **RestrictedPython 编译** (AST 黑名单: `os/subprocess/eval/exec/...`)
- ✅ **`__import__` 白名单** (只允许 `hscredit_studio.nodes.base` / `schemas.node_contract` / `math/json/...`)
- ✅ **超时强杀** (`subprocess.run` timeout=30s)
- ✅ **资源监控** (`resource.getrusage` → `cpu_seconds` / `mem_peak_mb`)

---

## 第 5 步: 版本回滚

### 5.1 入口: 版本下拉

```
[切换版本 ▼]
  v3 - E2E v2 - factor 改为 3     ← current
  v2 - E2E v2 - factor 改为 3     ← (rollback 创建的新版本)
  v1 - (初版)
```

### 5.2 后端行为

```
[POST /custom-nodes/{id}/versions/{v_id}/rollback]
  → 新建一个 v3, code = v2 的代码
  → current_version_number = 3
  → 不删任何旧版本, 可继续切回
```

### 5.3 真实 E2E 输出

```bash
[✓] 回滚: 新版本 v3 (内容等同 v2)
```

---

## 完整 E2E 输出 (28 项验收)

```bash
$ python scripts/e2e/run_e2e_phase6_b36.py

============================================================
🚀 Phase 6 B36 节点可插拔 E2E 验收
============================================================

[✓] admin 登录成功 (admin@demo.com)
[ℹ] viewer 登录跳过  (本 DB 未 seed viewer)

── 第 1 部分: 系统节点 ──
[✓] 列出节点: 总数=78, 系统=76, 自定义=2
[✓] 节点详情: iv_analysis, category=EDA
[✓] 分类筛选: 18 个特征工程节点
[✓] 搜索命中: 3 个
[✓] 启停切换: eda_overview ✓
[✓] 元数据更新: eda_overview description 已变更
[✓] 系统节点同步端点可达 ✓

── 第 2 部分: 自定义节点 ──
[✓] 创建自定义节点: id=ee406a4c..., v1 自动创建 ✓
[✓] 列出自定义节点: total=3
[✓] 自定义节点详情: current_version=1
[✓] 提交 v2: version_id=54389430...
[✓] 版本列表: total=2
[✓] 版本详情: v2 - E2E v2 - factor 改为 3
[✓] 回滚: 新版本 v3 (内容等同 v2)
[✓] 草稿保存 ✓
[✓] 草稿读取 ✓
[✓] 草稿丢弃 → 204, 再取 404 ✓
[✓] 申请锁: lock_id=1d9f720a...
[✓] 心跳续期 ✓
[✓] 释放锁 → 204 ✓

── 第 3 部分: 校验 + 沙箱 ──
[✓] AST 校验合法: valid=True, has_run=True, class=Doubler
[✓] AST 黑名单拦截: rules=['import_blocked', 'import_blocked'] ✓
[✓] Contract 反推: ast_inferred keys=['class_name', 'input_ports...']
[✓] 沙箱试运行: status=success, outputs={'result': 10}, duration=3750ms
[✓] 沙箱超时拦截: status=timeout
[✓] 沙箱黑名单拦截: status=failed, code=E_VALIDATION_ERROR

── 第 4 部分: 元数据 + 删除 ──
[✓] 元数据更新: name='E2E 翻倍节点 (已改名)'
[✓] 软删除 → 204, 列表已过滤 ✓

============================================================
📈 总计: 28 通过 / 0 失败 / 28 项
============================================================
```

---

## 录制真实 GIF 的方法

如果需要 GIF 动画(嵌入 README 或对外宣传), 有两种方式:

### 方法 A: 用 Playwright (推荐, 跨平台)

```bash
pip install playwright
playwright install chromium

cat > record_demo.py << 'EOF'
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    
    # 登录
    page.goto('http://localhost:3000/login')
    page.fill('input[type="text"]', 'admin@demo.com')
    page.fill('input[type="password"]', 'admin123')
    page.click('button[type="submit"]')
    page.wait_for_url('**/workflows')
    
    # 进入节点管理
    page.goto('http://localhost:3000/nodes')
    page.wait_for_selector('text=系统节点')
    
    # 录 GIF (需 ffmpeg 把 video 转 GIF)
    # 简单办法: 截多帧 + 用 Pillow 合成 GIF
    import time
    frames = []
    for action_name in ['list', 'create', 'edit', 'test']:
        page.screenshot(path=f'frame_{action_name}.png')
        frames.append(f'frame_{action_name}.png')
    
    browser.close()

# 合成 GIF (用 Pillow)
from PIL import Image
imgs = [Image.open(f) for f in frames]
imgs[0].save('demo.gif', save_all=True, append_images=imgs[1:], duration=2000, loop=0)
EOF

python record_demo.py
```

### 方法 B: 用 ffmpeg + 屏幕录制 (Windows)

```bash
# 用 ffmpeg 录屏幕 (假设已有屏幕录像工具或 OBS)
ffmpeg -f gdigrab -framerate 30 -i desktop \
       -t 30 -vf "crop=1440:900:0:0" demo_raw.mp4

# 压缩 + 转 GIF
ffmpeg -i demo_raw.mp4 -vf "fps=15,scale=720:-1:flags=lanczos" \
       -t 10 demo.gif
```

### 方法 C: 用现成 SaaS (最快, 但要联网)

- [ScreenToGif](https://www.screentogif.com/) (Windows 桌面工具)
- [LICEcap](https://www.cockos.com/licecap/) (跨平台, 输出 GIF)
- [Cloudapp / Loom](https://www.loom.com/) (云端录屏, 分享链接)

---

## 视频脚本 (录屏旁白参考)

录 GIF 时, 推荐旁白节奏:

| 时间 | 动作 | 旁白 |
|---|---|---|
| 0-3s | 打开 `/nodes` | "HSCredit Studio 的节点管理页: 76 个系统节点 + 任意自定义节点" |
| 3-6s | 切到"自定义节点" Tab | "Tab 切换, 自定义节点由租户自己创建" |
| 6-12s | 点 [+ 新建自定义节点], 进入 5 步向导 | "5 步向导: 起点选择 → 基础信息 → 代码编辑 → 试运行 → 确认" |
| 12-18s | 在 Monaco 里改代码, 故意加 `import os` | "Monaco Editor 实时校验 — 看, 黑名单 import 直接红波浪线" |
| 18-22s | 改回正常代码, 保存版本 | "保存版本后, 历史可查, 旧版本可回滚" |
| 22-28s | 点 [▶ 试运行], 填 inputs/params | "试运行走子进程沙箱, RestrictedPython 编译 + setrlimit 隔离" |
| 28-32s | 试运行结果输出 | "outputs 直接返回, 30 秒超时强杀" |
| 32-35s | 回到列表, 看新节点 | "创建完成, 立即可在工作流编排里使用" |

总时长约 35 秒, 适合嵌入 README.

---

## 演示数据 reset

跑演示后想恢复初始状态:

```bash
# 重置自定义节点 (保留系统节点)
python -c "
import asyncio
from sqlalchemy import delete
from hscredit_studio.core.database import session_scope
from hscredit_studio.models import CustomNode

async def reset():
    async with session_scope() as s:
        await s.execute(delete(CustomNode))
        await s.commit()
        print('✓ 自定义节点已清空')

asyncio.run(reset())
"

# 重新 seed (完整重置)
python -m hscredit_studio.scripts.seed
```
