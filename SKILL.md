---
name: Taobao-Search-Skill
description: "淘宝浏览器自动化，包括登录、商品搜索、按好评率筛选、加入购物车以及结果回传。支持任意消息通道（飞书/Slack/CLI）触发。keywords: Taobao, search, cart, rating, browser-automation, ecommerce"
---

# Taobao-Search-Skill

## AI Agent 执行指令

> 当 AI Agent（Claude Code、Cursor、Copilot 等）加载本 Skill 时，按以下步骤执行。

### 1. 参数提取

从用户自然语言输入中提取以下字段，缺失字段使用默认值：

| 参数 | 提取规则 | 默认值 |
|------|----------|--------|
| `search_keyword` | 搜索目标，如"苹果手机""索尼耳机" | `"索尼耳机"` |
| `rating_threshold` | "好评率大于 X%" → `X/100`；未提及则默认 | `0.99` |
| `max_candidates` | 用户指定的"最多 N 个"，未提及则默认 | `5` |
| `price_min` | "N 元以上""最低 N" → 数值；未提及则不限制 | `None` |
| `price_max` | "N 元以内""不超过 N""N 以下" → 数值 | `None` |
| `min_sales` | "付款人数超过 N""销量大于 N""至少 N 人付款" → 数值 | `None` |
| `require_free_shipping` | 提到"包邮""免邮""免运费"则为 `true` | `false` |
| `require_tmall` | 提到"只要天猫""天猫店"→ `true`；"只要淘宝""C店"→ `false` | `None` |
| `need_screenshot` | 提到"截图""证据"则为 `true` | `true` |
| `manual_approval_required` | 提到"自动""无人值守"则为 `false` | `true` |

### 2. 构造任务并执行

**方式 A — 使用 CLI（推荐）**：
```bash
python scripts/run_workflow.py \
  --search-keyword "<关键词>" \
  --rating-threshold <阈值> \
  --max-candidates <数量> \
  --price-min <最低价> --price-max <最高价> \
  --min-sales <最低销量> \
  --require-free-shipping --require-tmall yes
```

可选参数：`--task-file <task.json>`（从 JSON 文件读取完整配置）、`--price-min`、`--price-max`、`--min-sales`、`--require-free-shipping`、`--require-tmall yes/no`、`--no-screenshot`、`--no-manual-approval`、`--headless`。

**方式 B — 编程调用**：
```python
from scripts.workflow import UiAutomationWorkflow
from scripts.browser_adapter import BrowserAdapter
from scripts.feishu_client import FeishuClient

payload = {
    "search_keyword": "...",
    "rating_threshold": 0.95,
    "max_candidates": 5,
    "price_min": 50.0,
    "price_max": 500.0,
    "min_sales": 100,
    "require_free_shipping": True,
    "require_tmall": True,
    "need_screenshot": True,
    "manual_approval_required": True,
}
client = FeishuClient()
browser = BrowserAdapter()
workflow = UiAutomationWorkflow(client, browser)
result = workflow.run(payload)
```

### 3. 结果解读

执行完毕后，脚本输出一个 JSON，关键字段：

```
result.status        → "success" / "partial_success" / "failed"
result.login_status  → 登录态
result.matched_items → 符合条件并加购成功的商品列表
  └─ title, price, price_value, sales_count, rating, free_shipping, is_tmall, url, cart_added
result.error.code    → 错误码（失败时）
result.evidence      → 截图路径列表
```

向用户汇报时，用自然语言总结 `matched_items` 列表（商品名、价格、好评率），以及整体状态。

### 4. 中断与人工接管

以下场景必须暂停并提示用户在浏览器中手动操作：

- **登录**：提示"请在弹出的浏览器窗口中手动完成淘宝登录"
- **验证码/风控**：自动尝试滑块求解，失败后提示用户手动完成验证
- **会话失效**：提示用户重新登录

---

## Skill 规格说明

### 目标

编排一个端到端的淘宝 UI 自动化流程：

1. 接收任务（飞书 / Slack / CLI / AI Agent 均可）。
2. 优先恢复已持久化的淘宝会话。
3. 在受控浏览器会话中打开淘宝。
4. 当会话不存在或失效时，走一次人工登录。
5. 登录成功后自动保存新的会话状态。
6. 搜索目标关键词。
7. 按好评率阈值筛选商品。
8. 将符合条件的商品加入购物车。
9. 将结果回传到指定通道。

### 支持的输入

- `task_id`：任务唯一标识。
- `chat_message_id`：消息通道的消息标识（飞书 `feishu_message_id` 等）。
- `search_keyword`：搜索关键词。
- `rating_threshold`：最低好评率阈值，默认 `0.99`。
- `max_candidates`：最多检查的候选商品数量。
- `need_screenshot`：是否捕获证据截图。
- `manual_approval_required`：登录或校验时是否暂停等待人工接管。
- `session_state_path`：会话持久化文件路径，默认 `.cache/taobao-search-skill/taobao-session.json`。
- `session_strategy`：会话恢复策略，默认 `storage_state`。
- `session_auto_save`：人工登录成功后是否自动保存会话，默认 `true`。
- `price_min`：最低价格过滤（元），未设置则不限制。
- `price_max`：最高价格过滤（元），未设置则不限制。
- `min_sales`：最低付款人数过滤，未设置则不限制。
- `require_free_shipping`：是否只要包邮商品，默认 `false`。
- `require_tmall`：`true` 只要天猫、`false` 只要淘宝店、`None` 不限，默认 `None`。

### 期望输出

返回一个结构化结果对象，包含：

- `task_id`
- `status` (`success` / `partial_success` / `failed`)
- `login_status`
- `session_status`
- `search_status`
- `filter_status`
- `cart_status`
- `matched_items` — 商品列表，每项含 `title`、`item_id`、`price`、`rating`、`url`、`cart_added`
- `evidence` — 截图路径列表
- `steps` — 每步的执行记录（`name`、`status`、`message`）
- `error` — 错误码与详情

### 执行策略

- 优先使用确定性的浏览器操作，而非自由发挥式推理。
- 对短暂的导航或渲染失败使用重试。
- 优先恢复缓存会话，只有在会话不存在或失效时才进入人工登录。
- 每次进入淘宝后，必须先确认当前登录态；未登录时不得继续搜索、筛选或加购。
- 首次登录或会话失效时，提醒用户在浏览器中手动完成登录，然后立即提取存储状态并保存。
- 当登录、验证码或安全校验出现时，立即暂停并请求人工接管。
- 不尝试绕过平台安全控制。

### 消息通道适配

- `scripts/feishu_client.py` 是一个独立的协议适配层，负责 payload 归一化和报告封装，不直接调用任何消息平台 SDK。
- 接入新通道（Slack、钉钉、企业微信等）只需实现同样的 payload 归一化接口，无需改动核心工作流。

### 失败码

| 错误码 | 说明 |
|--------|------|
| `TASK_INVALID` | 任务字段缺失或格式错误 |
| `LOGIN_REQUIRED` | 未登录，需手动完成首次登录并保存会话 |
| `SEARCH_FAILED` | 无法加载或解析搜索结果页 |
| `SEARCH_BLOCKED` | 淘宝风控拦截搜索，需手动完成验证 |
| `FILTER_FAILED` | 无法可靠提取好评率 |
| `CART_FAILED` | 无法将商品加入购物车 |
| `REPORT_FAILED` | 无法投递结果回传 |
| `WORKFLOW_ERROR` | 工作流执行异常 |

---

## 依赖与启动约定

- Python 3.11 或更高版本。
- 安装依赖：`python -m pip install -r requirements.txt`。
- 安装浏览器：`python -m playwright install chromium`。
- 默认以 Chromium 启动，使用 Playwright 的 `storage_state` 恢复淘宝会话。
- 默认会话文件路径：`.cache/taobao-search-skill/taobao-session.json`。
- 推荐的启动方式：`python scripts/run_workflow.py --task-file <task.json>`。

如果要重建会话，只需删除会话文件，或在人工登录后由脚本自动覆盖保存。

---

## 多平台部署

### Claude Code

将本文件复制到 `.claude/skills/taobao-search.md`，Claude Code 会自动识别。触发方式：
- 显式：`/taobao-search 搜索苹果手机 好评率大于95%`
- 语义匹配：描述淘宝搜索/加购意图时自动匹配

### OpenClaw

将本文件作为 Skill 定义加载，由 OpenClaw 的消息路由机制匹配任务。保持 description 中的关键词覆盖触发场景即可。

### 其他 AI Agent 工具

任何支持 Markdown 前导 + 指令格式的 Agent 工具（Cursor Rules、Copilot Instructions 等），参考「AI Agent 执行指令」段即可直接使用。

### 直接 CLI

```bash
python scripts/run_workflow.py --search-keyword "苹果手机" --rating-threshold 0.95
```
