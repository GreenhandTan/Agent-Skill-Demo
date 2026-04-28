---
name: taobao-skill-test
description: "适用于飞书任务下发后，需要在淘宝进行浏览器自动化的场景，包括登录、商品搜索、按好评率筛选、加入购物车以及回传结果；keywords: Feishu, Taobao, login, search, cart, report"
---

# UI 自动化测试 Skill

## 目标

这个 Skill 用于编排一个端到端的 UI 自动化测试流程：

1. 接收飞书任务。
2. 优先恢复已持久化的淘宝会话。
3. 在受控浏览器会话中打开淘宝。
4. 当会话不存在或失效时，走一次人工登录。
5. 登录成功后自动保存新的会话状态。
6. 搜索目标关键词。
7. 按好评率阈值筛选商品。
8. 将符合条件的商品加入购物车。
9. 将结果回传到飞书。

## 支持的输入

- `task_id`：任务唯一标识。
- `feishu_message_id`：飞书消息标识。
- `search_keyword`：搜索关键词。
- `rating_threshold`：最低好评率阈值，默认 `0.99`。
- `max_candidates`：最多检查的候选商品数量。
- `need_screenshot`：是否捕获证据截图。
- `manual_approval_required`：登录或校验时是否暂停等待人工接管。
- `session_state_path`：会话持久化文件路径，默认 `.cache/ui-automation-test/taobao-session.json`。
- `session_strategy`：会话恢复策略，默认 `storage_state`，也可选 `cookie_localstorage`。
- `session_auto_save`：人工登录成功后是否自动保存会话，默认 `true`。

## 期望输出

返回一个结构化结果对象，包含：

- `task_id`
- `status`
- `login_status`
- `search_status`
- `filter_status`
- `cart_status`
- `matched_items`
- `evidence`
- `error`

## 执行策略

- 优先使用确定性的浏览器操作，而不是自由发挥式推理。
- 对短暂的导航或渲染失败使用重试。
- 优先恢复缓存会话，只有在会话不存在或失效时才进入人工登录。
- 当登录、验证码或安全校验出现时，立即暂停并请求人工接管。
- 不尝试绕过平台安全控制。

## 通讯边界

- 如果 OpenClaw 已经接入飞书通讯插件，则由 OpenClaw 负责消息收发。
- 这个 Skill 只负责解析进入的任务 payload，以及构造回传给 OpenClaw 的结果封装。
- `scripts/feishu_client.py` 只做 payload 归一化和报告封装，不直接调用飞书 SDK。

## 依赖与启动约定

- Python 3.11 或更高版本。
- 先安装依赖：`python -m pip install -r requirements.txt`。
- 再安装浏览器：`python -m playwright install chromium`。
- 默认以 Chromium 启动，使用 Playwright 的 `storage_state` 文件恢复淘宝会话。
- 默认会话文件路径为 `.cache/ui-automation-test/taobao-session.json`。
- 推荐的启动方式：`python scripts/run_workflow.py --task-file <task.json>`。

如果要重建会话，只需删除会话文件，或者在人工登录后由脚本自动覆盖保存。

## 流程骨架

### 1. 接收任务

- 解析飞书载荷。
- 校验必填字段。
- 构建运行上下文。

### 2. 准备浏览器

- 启动隔离的浏览器上下文。
- 导航到 `https://www.taobao.com`。
- 检查当前会话是否已经登录。

### 3. 认证登录

- 如果需要登录，等待用户接管或已授权交互。
- 在继续前确认已登录状态。

### 4. 搜索商品

- 搜索给定关键词。
- 捕获结果页状态，便于追踪。

### 5. 筛选商品

- 检查商品卡片和/或商品详情页。
- 仅保留好评率达到或超过阈值的商品。

### 6. 加入购物车

- 将符合条件的商品加入购物车。
- 校验每次加购是否成功。

### 7. 回传结果

- 将摘要回传到飞书。
- 包含命中的商品、成功/失败状态和证据链接。

## 失败处理

- `TASK_INVALID`: Missing or malformed task fields.
- `LOGIN_REQUIRED`: Human takeover required.
- `SEARCH_FAILED`: Search page could not be loaded or parsed.
- `FILTER_FAILED`: Ratings could not be extracted reliably.
- `CART_FAILED`: Item could not be added to cart.
- `REPORT_FAILED`: Feishu callback could not be delivered.

## OpenClaw 兼容说明

- 保持 skill 描述足够明确，便于任务路由稳定匹配。
- 保持输入输出结构化，便于与其他工作流串联。
- 优先使用可检查的小步骤，而不是一个大而全的 prompt。