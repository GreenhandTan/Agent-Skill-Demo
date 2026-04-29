---
name: Taobao-Search-Skill
description: "淘宝浏览器自动化，包括会话持久化、登录、商品搜索、多维度筛选（好评率/价格/销量/包邮/天猫）、SKU规格匹配、加入购物车、验证码自动求解以及结果回传。支持任意消息通道（飞书/Slack/CLI）触发。keywords: Taobao, search, cart, rating, price, sales, shipping, tmall, SKU, captcha, session, browser-automation, ecommerce"
---

# Taobao-Search-Skill

## AI Agent 执行指令

> 当 AI Agent（Claude Code、Cursor、Copilot 等）加载本 Skill 时，按以下步骤执行。

### 1. 参数提取

从用户自然语言输入中提取以下字段，缺失字段使用默认值：

| 参数 | 提取规则 | 默认值 |
|------|----------|--------|
| `search_keyword` | 搜索目标，如"苹果手机""索尼耳机" | `"索尼耳机"` |
| `rating_threshold` | 用户明确要求时 → `X/100`；未提及则不筛选 | `0` |
| `max_candidates` | 用户指定的"最多 N 个"，未提及则默认 | `5` |
| `price_min` | "N 元以上""最低 N" → 数值；未提及则不限制 | `None` |
| `price_max` | "N 元以内""不超过 N""N 以下" → 数值 | `None` |
| `min_sales` | "付款人数超过 N""销量大于 N""至少 N 人付款" → 数值 | `None` |
| `require_free_shipping` | 提到"包邮""免邮""免运费"则为 `true` | `false` |
| `require_tmall` | 提到"只要天猫""天猫店"→ `true`；"只要淘宝""C店"→ `false` | `None` |
| `sku_keywords` | 用户指定规格如"16+512""16G 512G"→ 空格分隔关键词匹配SKU选项 | `None` |
| `need_screenshot` | 提到"截图""证据"则为 `true` | `true` |
| `manual_approval_required` | 提到"自动""无人值守"则为 `false` | `true` |
| `headless` | 提到"无头""后台静默"则为 `true` | `false` |

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

可选参数：`--task-file <task.json>`（从 JSON 文件读取完整配置）、`--price-min`、`--price-max`、`--min-sales`、`--require-free-shipping`、`--require-tmall yes/no`、`--sku-keywords "16G 512G"`（指定SKU规格关键词）、`--no-screenshot`、`--no-manual-approval`、`--no-session-auto-save`、`--session-state-path`、`--headless`。

**方式 B — 编程调用**：
```python
from scripts.workflow import UiAutomationWorkflow
from scripts.browser_adapter import BrowserAdapter
from scripts.report_channel import FeishuClient

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
result.status          → "success" / "partial_success" / "failed"
result.login_status    → 登录态 ("success" / "waiting_manual" / "failed")
result.session_status  → 会话态 ("restored" / "captured" / "missing")
result.search_status   → 搜索状态
result.filter_status   → 筛选状态
result.cart_status     → 加购状态 ("success" / "empty" / "error")
result.matched_items   → 符合条件并加购成功的商品列表
  └─ title, item_id, price, price_value, sales_count, rating, free_shipping, is_tmall, url, cart_added
result.evidence        → 截图路径列表
result.steps           → 每步执行记录 [{name, status, message, details}]
result.error.code      → 错误码（失败时）
```

向用户汇报时，用自然语言总结 `matched_items` 列表（商品名、价格、好评率），以及整体状态。

### 4. 中断与人工接管

以下场景必须暂停并提示用户在浏览器中手动操作：

- **登录**：提示"请在弹出的浏览器窗口中手动完成淘宝登录"，每 30 秒检测一次登录态，最长等待约 3.5 分钟；登录成功后自动保存会话
- **验证码/风控**：自动尝试滑块求解（ddddocr + OpenCV 双引擎），失败后每 30 秒检测一次验证状态，最长等待约 3.5 分钟，期间不刷新页面以免打断用户操作
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
- `feishu_message_id`：消息通道的消息标识（飞书消息 ID 等）。
- `report_channel`：结果回传通道标识，默认 `"feishu"`。
- `search_keyword`：搜索关键词。
- `rating_threshold`：最低好评率阈值，`0` 表示不筛选，默认 `0`。
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
- `sku_keywords`：规格关键词，空格分隔（如 `"16G 512G"`），用于匹配商品详情页的 SKU 选项。

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
- 所有 DOM 选择器集中管理在 `scripts/selectors.py`，淘宝改版时只需更新该文件，无需修改 `browser_adapter.py`。
- 优先恢复缓存会话，只有在会话不存在或失效时才进入人工登录。
- 每次进入淘宝后，必须先确认当前登录态；未登录时不得继续搜索、筛选或加购。
- 首次登录或会话失效时，提醒用户在浏览器中手动完成登录，然后立即提取存储状态并保存。
- 当登录、验证码或安全校验出现时，立即暂停并请求人工接管。
- 加购时如遇到 SKU 规格选择弹窗：若指定了 `sku_keywords`，按空格分隔的关键词逐一匹配选项文本，已选中的跳过以防止取消选中，任一关键词匹配失败则跳过该商品；若未指定关键词，则选择第一个可见选项作为默认规格。
- 不尝试绕过平台安全控制。

### 消息通道适配

- `scripts/report_channel.py` 是消息通道抽象层：`ReportChannel` 基类定义 `send_report()` / `normalize_task_payload()` 接口，`FeishuClient` 是飞书实现。接入新通道（Slack、钉钉、企业微信等）只需新增子类并注册到 `CHANNEL_REGISTRY`。

### 失败码

| 错误码 | 说明 |
|--------|------|
| `LOGIN_REQUIRED` | 未登录，需手动完成首次登录并保存会话 |
| `SEARCH_BLOCKED` | 淘宝风控拦截搜索，需手动完成验证 |
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
