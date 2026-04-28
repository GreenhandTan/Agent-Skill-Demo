# UI自动化测试 Skill 技术设计文档

## 1. 目标

设计一个可在 OpenClaw 框架中运行的 UI 自动化测试 Skill，完成从飞书接收任务、登录淘宝、搜索指定商品、按条件筛选、加入购物车并回传结果的完整闭环。

该 Skill 的定位是“任务编排 + 浏览器自动化 + 结果回传”，不依赖人工逐步干预，但在登录、验证码、风控、页面结构变化等场景下允许降级为人工确认。

## 2. 业务流程

### 2.1 标准流程

1. 任务下发：通过飞书接受测试任务指令。
2. 浏览器自动化：打开 `www.taobao.com` 并进入自动化执行态。
3. 用户登录：完成淘宝账号登录。
4. 商品搜索：搜索关键词“索尼耳机”。
5. 智能筛选：筛选好评率大于等于 99% 的商品。
6. 购物车操作：将符合条件的商品加入购物车。
7. 结果反馈：将执行结果回传飞书。

### 2.2 关键约束

- 需要兼容 OpenClaw 的 Skill 组织方式。
- 必须将飞书、浏览器、淘宝页面操作拆分为可替换适配层。
- 必须支持中断恢复、失败重试、结构化结果输出。
- 涉及登录、验证码、风控时，不应尝试绕过安全机制，只允许请求用户接管。

## 3. 设计原则

- 单职责：任务解析、浏览器控制、页面理解、结果回传分离。
- 状态化：整个流程以显式状态机驱动，避免“链式 prompt”失控。
- 可观测：每一步都产出结构化日志、截图和结果摘要。
- 可恢复：关键步骤失败后可以重试或从最近检查点恢复。
- 可替换：飞书、浏览器、商品解析器都做成适配器，便于未来接入其他平台。

## 4. OpenClaw 兼容的 Skill 结构

建议将 Skill 拆成以下逻辑块：

### 4.1 Skill 元数据

Skill 的说明字段必须覆盖触发场景，例如：

- 飞书任务下发
- 浏览器自动化
- 淘宝搜索与筛选
- 购物车操作
- 结果回传

这样 OpenClaw 才能在任务匹配时正确加载该 Skill。

### 4.2 输入契约

建议支持以下输入：

- `task_id`：飞书任务编号
- `feishu_message_id`：消息唯一标识
- `search_keyword`：默认值为“索尼耳机”
- `rating_threshold`：默认值为 `0.99`
- `max_candidates`：最大处理商品数
- `need_screenshot`：是否回传截图证据
- `manual_approval_required`：登录/验证码时是否等待人工接管

### 4.3 输出契约

输出应为结构化 JSON，至少包含：

- `task_id`
- `status`：`success` / `partial_success` / `failed`
- `login_status`
- `search_status`
- `filter_status`
- `cart_status`
- `matched_items`
- `evidence`：截图、页面 URL、时间戳
- `error`：错误码、错误信息、失败步骤

## 5. 总体架构

建议采用四层架构：

### 5.1 任务接入层

负责监听飞书消息、解析任务 payload、生成执行上下文。

职责：

- 拉取飞书消息
- 校验任务格式
- 生成 `RunContext`
- 记录任务状态

### 5.2 流程编排层

采用状态机或步骤队列驱动执行。

推荐状态：

- `RECEIVED`
- `BROWSER_READY`
- `LOGIN_PENDING`
- `LOGGED_IN`
- `SEARCHED`
- `FILTERED`
- `ADDED_TO_CART`
- `REPORTED`
- `FAILED`

### 5.3 浏览器执行层

负责真实页面交互：打开网页、输入搜索词、点击筛选、判断列表状态、加入购物车。

能力要求：

- 页面导航
- DOM 定位与文本识别
- 截图
- 异常弹窗处理
- 登录态检测

### 5.4 结果回传层

负责把执行结果写回飞书，包括简版摘要和证据链接。

### 5.5 OpenClaw 通讯边界

如果 OpenClaw 已经接入飞书通讯插件，则通讯层由 OpenClaw 统一负责，Skill 只需要处理进入工作流的任务载荷以及返回给 OpenClaw 的结果封装。

该设计下：

- 飞书消息收发不在 Skill 内部实现。
- `scripts/feishu_client.py` 仅作为协议适配层，负责任务载荷归一化和结果封装。
- Skill 只依赖结构化输入输出，不直接耦合飞书 SDK、Webhook 或轮询逻辑。

```mermaid
flowchart TB
  A[OpenClaw / 飞书通讯插件\n负责任务收发]
  B[SKILL.md\n技能入口]
  C[scripts/feishu_client.py\n协议适配层]
  D[scripts/workflow.py\n流程编排]
  E[scripts/browser_adapter.py\nPlaywright 浏览器层]
  F[scripts/session_manager.py\nstorage_state 持久化]
  G[Taobao 网站\n搜索 / 登录 / 加购]
  H[OpenClaw Result Envelope\n结果封装回传]

  A --> B
  B --> C
  C --> D
  D --> E
  D --> F
  E --> G
  F --> E
  D --> H
  H --> A

  subgraph Skill[Skill 内部职责]
    C
    D
    E
    F
  end

  subgraph External[外部依赖]
    A
    G
  end
```

## 6. 核心流程设计

### 6.1 飞书任务接收

1. 监听飞书机器人消息或飞书开放平台回调。
2. 提取任务参数，至少包括任务 ID、商品关键词、筛选阈值、结果回传目标。
3. 校验字段完整性。
4. 生成执行上下文并启动工作流。

任务进入 Skill 时应由 OpenClaw 注入标准化 payload，Skill 只依赖字段契约，不依赖具体示例。

### 6.2 浏览器初始化

1. 打开受控浏览器环境。
2. 进入 `https://www.taobao.com`。
3. 检查是否已登录。
4. 若未登录，进入登录分支。

建议将浏览器上下文与任务上下文绑定，确保每个任务独立执行，避免串号。

### 6.3 登录处理

登录是最容易受风控影响的环节，建议采用“自动检测 + 人工接管”的双模式。

策略：

- 如果页面存在扫码登录，等待用户扫码。
- 如果需要短信或验证码，不尝试破解，提示人工完成。
- 登录成功后写入会话状态。

建议判断登录成功的信号：

- 页面出现用户昵称
- 页面进入个人中心或首页已登录态
- Cookie 中出现登录态标志

### 6.4 搜索商品

1. 在淘宝首页输入关键词“索尼耳机”。
2. 提交搜索。
3. 等待结果页加载完成。
4. 记录搜索结果页 URL 和首屏截图。

### 6.5 智能筛选

需要在商品列表中识别好评率大于等于 99% 的商品。

推荐实现方式：

- 优先解析卡片中的显式文本，如“好评率 99%+”。
- 如果页面只显示部分信息，则进入商品详情页补采关键指标。
- 统一将百分比标准化为数值，再做阈值判断。

筛选逻辑：

```text
if praise_rate >= 0.99 then keep
else skip
```

如果列表页无法直接获取好评率，则需要：

1. 打开候选商品详情页。
2. 检索评价相关指标。
3. 仅对满足阈值的商品保留。

### 6.6 加入购物车

对筛选后的候选商品，按顺序执行加入购物车操作。

建议策略：

- 最多处理 `max_candidates` 个商品。
- 对每个商品记录 `item_id`、标题、价格、好评率。
- 添加成功后校验购物车状态。
- 如出现规格选择弹窗，选择默认可购买规格。

### 6.7 回传飞书

结果回传建议包含：

- 任务执行状态
- 登录是否成功
- 搜索结果数量
- 满足条件的商品数量
- 成功加入购物车数量
- 失败步骤和原因
- 关键截图或证据链接

如果由 OpenClaw 承担飞书通讯，则 Skill 应返回结构化 report envelope，由 OpenClaw 完成实际消息投递。

回传结果应由 OpenClaw 按统一 report envelope 投递，不需要在 Skill 文档中固定某个示例 JSON。

## 7. 状态机设计

建议使用显式状态机，避免隐式流程失控。

### 7.1 状态迁移

- `RECEIVED` -> `BROWSER_READY`
- `BROWSER_READY` -> `LOGIN_PENDING`
- `LOGIN_PENDING` -> `LOGGED_IN`
- `LOGGED_IN` -> `SEARCHED`
- `SEARCHED` -> `FILTERED`
- `FILTERED` -> `ADDED_TO_CART`
- `ADDED_TO_CART` -> `REPORTED`
- 任意状态 -> `FAILED`

### 7.2 失败恢复

- 浏览器初始化失败：重建上下文并重试。
- 登录超时：挂起等待人工接管。
- 搜索结果为空：回传空结果并终止。
- 筛选解析失败：截图留证并终止。
- 加购失败：记录失败商品并继续下一个候选项。

## 8. 数据模型

### 8.1 RunContext

```json
{
  "task_id": "string",
  "feishu_message_id": "string",
  "search_keyword": "string",
  "rating_threshold": 0.99,
  "max_candidates": 5,
  "need_screenshot": true,
  "manual_approval_required": true,
  "session_state_path": ".cache/ui-automation-test/taobao-session.json",
  "session_strategy": "storage_state",
  "session_auto_save": true
}
```

### 8.2 ExecutionResult

```json
{
  "task_id": "string",
  "status": "success|partial_success|failed",
  "session_status": "restored|captured|missing|unknown",
  "login_status": "success|waiting_manual|failed",
  "search_status": "success|failed",
  "filter_status": "success|failed",
  "cart_status": "success|partial_success|failed",
  "matched_items": [],
  "evidence": [],
  "error": null
}
```

## 9. 风险与对策

### 9.1 登录风控

风险：淘宝可能触发验证码、短信验证或异常登录检测。

对策：

- 允许人工接管登录。
- 不做任何绕过行为。
- 提前超时并回传状态。

### 9.2 页面结构变化

风险：商品卡片和评价信息 DOM 结构可能变化。

对策：

- 优先使用多策略定位。
- 使用文本、ARIA、DOM 结构联合识别。
- 关键页面保留截图和 DOM 快照。

### 9.3 商品评价信息不可见

风险：列表页可能无法直接拿到 99% 好评率。

对策：

- 支持详情页补采。
- 允许标记为 `partial_success`。

### 9.4 多商品处理时效

风险：逐个详情页补采会耗时较长。

对策：

- 限制候选商品数量。
- 并发仅用于读操作，写操作保持串行。

## 10. 测试方案

### 10.1 单元测试

- 任务消息解析
- 好评率阈值判断
- 状态机迁移
- 结果结构化输出

### 10.2 集成测试

- 飞书回调到任务启动
- 浏览器打开与登录状态识别
- 搜索页解析与候选筛选
- 加购物车结果校验
- 飞书结果回传

### 10.3 端到端测试

- 使用受控测试账号和测试商品环境完成整链路。
- 每次执行保存截图、日志和最终 JSON 结果。

## 11. 可观测性

建议至少记录以下信息：

- 每一步开始/结束时间
- 页面 URL
- 关键截图路径
- 当前状态码
- 失败原因和堆栈摘要

## 12. 验收标准

该 Skill 可视为完成，需满足：

- 能接收飞书任务并成功启动。
- 能进入淘宝并完成登录或人工接管提示。
- 能搜索“索尼耳机”。
- 能识别并筛选好评率大于等于 99% 的商品。
- 能将符合条件的商品加入购物车。
- 能把结果回传飞书。
- 能输出结构化执行结果和证据。

## 13. 建议的 Skill 目录结构

```text
Agent_Demo/
  SKILL.md
  requirements.txt
  scripts/
    browser_adapter.py
    config.py
    feishu_client.py
    models.py
    run_workflow.py
    session_flow.py
    session_manager.py
    workflow.py
  UI自动化测试Skill-技术设计文档.md
```

## 14. 建议的 SKILL.md 说明要点

建议 SKILL.md 的 description 覆盖以下触发词：

- 飞书任务
- 淘宝自动化
- 登录
- 搜索商品
- 购物车
- 结果回传

并在正文中明确：

- 使用 OpenClaw 风格的任务输入输出。
- 浏览器操作由工具适配层完成。
- 登录与验证码场景允许人工接管。
- 不执行任何绕过风控的行为。

## 15. 当前实现状态

- 浏览器层已接入 Playwright，同步支持 `storage_state` 恢复与保存。
- 会话层已支持成功登录后的自动持久化与下次恢复。
- 飞书层已降级为 OpenClaw 协议适配，不再承担具体通讯传输。
- 仓库已平铺到项目根目录，便于 OpenClaw 直接按根目录读取和执行。

## 16. 结论

这个 Skill 的核心不是“把提示词写长”，而是把 UI 自动化拆成可执行、可恢复、可回传的状态机。只要把飞书接入、浏览器自动化、商品筛选和结果回传四个边界层分开，就可以稳定兼容 OpenClaw，并支持后续扩展到更多站点和更多筛选条件。