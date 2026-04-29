# Taobao-Search-Skill

淘宝端到端 UI 自动化 Skill —— 从消息通道接收任务，自动完成淘宝登录、商品搜索、好评率筛选、加入购物车，并回传结构化结果。

适用于 **Claude Code**、**OpenClaw**、**Cursor** 等 AI Agent 工具，也支持直接 CLI 调用。

## 功能

- **会话持久化** — 首次人工登录后自动保存 `storage_state`，后续运行跳过登录
- **反检测拟人化** — playwright-stealth 注入 20 种反检测补丁，结合贝塞尔曲线鼠标轨迹、随机打字延迟、分段滚动，降低风控触发概率
- **验证码自动求解** — ddddocr ML 模型 + OpenCV Canny 边缘检测双引擎，支持淘宝 GeeTest v3/v4 滑块验证码
- **容错降级** — 登录/风控/验证码失败时暂停并请求人工接管，不绕过平台安全控制
- **结构化输出** — 每步产出执行记录，最终返回 JSON（含匹配商品、截图证据、错误码）
- **多通道适配** — 独立协议适配层，飞书/Slack/CLI 均可接入

## 安装

### 1. 克隆仓库

```bash
git clone https://github.com/GreenhandTan/Taobao-Search-Skill.git
cd Agent-Skill-Demo
```

### 2. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 3. 安装浏览器

```bash
python -m playwright install chromium
```

## 使用

### CLI 直接调用

```bash
# 从 JSON 文件读取配置
python scripts/run_workflow.py --task-file task_test.json

# 命令行参数
python scripts/run_workflow.py \
  --search-keyword "苹果手机" \
  --rating-threshold 0.95 \
  --max-candidates 10

# 无人值守模式
python scripts/run_workflow.py \
  --search-keyword "索尼耳机" \
  --rating-threshold 0.99 \
  --headless \
  --no-manual-approval
```

### 作为 Claude Code Skill

将 `SKILL.md` 复制到项目的 `.claude/skills/` 目录：

```bash
mkdir -p .claude/skills
cp SKILL.md .claude/skills/taobao-search.md
```

触发方式：

- **显式调用**：`/taobao-search 搜索苹果手机，好评率大于95%`
- **语义匹配**：直接说"帮我在淘宝搜一下索尼耳机并加购物车"

首次使用需要在 `.claude/settings.local.json` 中添加 Bash 权限：

```json
{
  "permissions": {
    "allow": [
      "Bash(python scripts/run_workflow.py *)"
    ]
  }
}
```

### 作为 OpenClaw Skill

将 `SKILL.md` 放置在 OpenClaw 的 skill 加载路径下，OpenClaw 会根据 description 中的关键词自动匹配任务路由。

### Python API

```python
from scripts.workflow import UiAutomationWorkflow
from scripts.browser_adapter import BrowserAdapter
from scripts.feishu_client import FeishuClient

payload = {
    "task_id": "task-001",
    "search_keyword": "苹果手机",
    "rating_threshold": 0.95,
    "max_candidates": 5,
    "need_screenshot": True,
    "manual_approval_required": True,
}

client = FeishuClient()
browser = BrowserAdapter()
workflow = UiAutomationWorkflow(client, browser)
result = workflow.run(payload)

print(f"状态: {result.status}")
print(f"匹配商品: {len(result.matched_items)} 件")
for item in result.matched_items:
    print(f"  - {item.title} | {item.price} | 好评率 {item.rating}")
```

## 架构

```
SKILL.md                          # Skill 定义（AI Agent 执行指令 + 规格说明）
scripts/
├── run_workflow.py               # CLI 入口
├── workflow.py                   # 主流程编排（7 步状态机）
├── browser_adapter.py            # 浏览器适配器（Playwright + stealth + 拟人化）
├── slider_solver.py              # 滑动验证码求解器（ddddocr + OpenCV）
├── session_manager.py            # 会话持久化管理
├── session_flow.py               # 会话恢复与捕获编排
├── feishu_client.py              # 消息通道协议适配层
├── config.py                     # 配置解析
└── models.py                     # 数据模型
.cache/taobao-search-skill/       # 会话缓存与截图（自动创建，已 gitignore）
```

## 工作流

```
接收任务 → 恢复会话 → 打开淘宝 → 确认登录态 → 搜索商品
    → 进入详情页提取好评率 → 筛选商品 → 加入购物车 → 验证加购 → 回传结果
```

## 配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `search_keyword` | str | `"索尼耳机"` | 搜索关键词 |
| `rating_threshold` | float | `0.99` | 最低好评率阈值（0~1，严格大于） |
| `max_candidates` | int | `5` | 最多检查的候选商品数 |
| `need_screenshot` | bool | `true` | 是否捕获证据截图 |
| `manual_approval_required` | bool | `true` | 登录/验证时是否等待人工接管 |
| `session_strategy` | str | `"storage_state"` | 会话恢复策略 |
| `session_auto_save` | bool | `true` | 登录后自动保存会话 |
| `headless` | bool | `false` | 无头模式运行 |

## 环境要求

- Python 3.11+
- Playwright Chromium
- 依赖：`playwright>=1.45`、`playwright-stealth>=2.0`、`ddddocr>=1.4`、`opencv-python>=4.8`、`numpy>=1.24`

## License

MIT
