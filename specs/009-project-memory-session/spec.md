# 项目记忆与会话持久化 Spec

> 状态：IMPLEMENTED（静态指令、结构化 JSONL、恢复 UI 与自动笔记已实现）  
> Feature：009  
> 前置能力：Feature 008 上下文管理
> 全局契约：[`../architecture-contracts.md`](../architecture-contracts.md)

## 初步想法

在新会话启动时自动恢复项目知识和用户偏好，让 Agent 从“每次失忆”变成“越用越懂你”。通过项目指令文件、会话存档和自动记忆三套机制，实现工作记忆与长期记忆的分层管理，中断后可以平滑继续。

技术方向：

- 项目指令文件支持项目级高于用户级的多层优先级，以及安全的 `@include`。
- 会话使用 JSONL 追加写，不维护独立 meta 文件，需要 ID、标题和消息数时扫描 JSONL 计算。
- 恢复时处理坏行、孤立工具调用、上下文超限和长时间暂停。
- 30 天以上的过期会话在后台清理。
- 自动笔记分为用户偏好、纠正反馈、项目知识和参考资料四类。
- 每轮 Agent Loop 自然结束后异步调用 LLM 更新笔记，由 LLM判断去重。
- 用户级与项目级笔记分开存放，请求前注入受大小限制的记忆索引。
- 本章不做向量数据库、RAG、团队记忆同步。

## 背景

Feature 008 解决了单进程内长会话的上下文膨胀问题，但进程退出后对话和工作上下文仍然丢失。编码项目通常具有稳定的规范、个人偏好、项目知识和未完成工作，每次重新解释既浪费时间，也容易遗漏。

本 Feature 引入三个独立层次：

1. `MEWCODE.md`：人工维护的静态项目规范。
2. JSONL 会话存档：可恢复的工作记忆。
3. 自动笔记：跨会话演化的长期记忆。

## 目标

- G1：新会话第一轮即可加载项目指令和记忆索引。
- G2：会话以 JSONL 实时追加写入，崩溃恢复可处理坏行、悬空工具调用和 token 超限。
- G3：提供 `/resume` 会话选择和恢复。
- G4：Agent 自然完成后异步提取值得长期保留的信息。
- G5：`@include` 有深度、环路和路径边界保护。
- G6：指令和记忆只在请求组装阶段注入，笔记更新不阻塞交互。
- G7：后台清理超过 30 天的过期会话。
- G8：会话 ID 统一为 `YYYYMMDD-HHMMSS-xxxx`，同时用于 JSONL 和 Feature 008 工具结果目录。

## 第 1 层：项目指令文件

### F1：三层加载

启动时按优先级扫描：

1. `<project_root>/MEWCODE.md`
2. `<project_root>/.mewcode/MEWCODE.md`
3. `~/.mewcode/MEWCODE.md`

找到即加载，缺失则跳过；内容按以上顺序拼接，层之间用空行分隔。

### F2：include 语法

独占一行的 `@include <relative_path>` 会被引用文件的完整内容替换。路径相对于当前文件目录解析，引用文件可以继续 include。段落中间出现的 `@include` 保持原文。

### F3：嵌套深度

最大深度为 5，根文件算第 1 层。超过限制时保留原 include 行，并追加：

```html
<!-- @include 超过最大嵌套深度，已跳过: <path> -->
```

### F4：环路检测

每条展开链维护已解析真实路径集合。重复出现时跳过并追加：

```html
<!-- @include 检测到环路，已跳过: <path> -->
```

### F5：路径边界

项目级两个入口只能包含项目根目录内文件；用户级入口只能包含 `~/.mewcode/` 内文件。路径必须先解析符号链接为真实路径，再做根目录前缀判断。越界时跳过并追加警告注释。

### F6：缺失、空文件与二进制

缺失文件静默跳过；空文件不影响拼接。前 512 字节包含 `0x00` 的文件视为二进制，跳过并追加警告注释。

### F7：系统提示注入

拼接结果进入系统提示的 `custom-instructions` 模块。内置安全约束始终高于任何 MEWCODE.md；项目级与用户级内容冲突时，项目级优先。

### F8：生命周期

启动时加载一次，进程内保持稳定，不实现热更新。

## 第 2 层：会话存档

### F9：Session ID

格式为 `YYYYMMDD-HHMMSS-xxxx`，后缀为 4 位随机十六进制。本格式同时用于 Feature 008 的工具结果目录。

### F10：SessionContext

新增统一的 `SessionContext`，拥有：

- `sessionId`
- `sessionDir = <workspace>/.mewcode/sessions/<session_id>`
- `toolResultDir = sessionDir/tool-results`
- `conversationPath = sessionDir/conversation.jsonl`

`ContextManager` 依赖 SessionContext，不再自行生成会话目录。

### F11：JSONL 消息格式

每条记录占一行 JSON：

- `role`：`user`、`assistant` 或 `tool`
- `content`：可选正文
- `tool_calls`：assistant 可选字段，结构同 ToolCall
- `tool_results`：tool 可选字段，结构同 ToolResult
- `ts`：写入时 Unix 秒时间戳
- `model`：仅会话第一条消息记录

API Key、授权头、环境变量秘密及其他敏感信息不得写入。

### F12：压缩标记

Conversation 替换为摘要历史时，先追加：

```json
{"type":"compact","ts":0}
```

再追加压缩后的消息。恢复时只加载最后一个 compact 标记之后的内容。

### F13：Conversation 事件

Conversation 升级为结构化事件模型，提供用户消息、助手消息、带工具调用的助手消息、工具结果和历史替换操作。每次操作完成后，通过构造时注入的回调追加 JSONL。

### F14：追加写

JSONL 只追加、不重写。最后一行不完整时，恢复过程允许丢弃。

### F15：Writer

会话 Writer 实现 `Closeable`，内部使用 FileChannel/BufferedWriter 和 ReentrantLock 保证单行追加原子性。用户消息、最终助手消息、compact 标记和每轮自然结束时强制刷盘；工具事件允许普通 flush 或批量刷盘。

### F16：退出

程序退出时关闭 Writer；单个关闭错误不得破坏其他资源的退出流程。

## 第 3 层：会话恢复

### F17：命令

新增 `/resume`，仅在 Agent 空闲时可用，并进入 `RESUMING` UI 状态。

### F18：扫描

扫描 `.mewcode/sessions/` 下严格符合会话 ID 格式且包含 `conversation.jsonl` 的目录，按 JSONL 最后修改时间倒序排列。

### F19：选择器

基于项目现有 JLine 实现会话选择器，支持上下键、字符搜索过滤、Enter 选择、Esc 取消；不引入 Lanterna。

### F20：列表信息

每项显示：

- 第一条用户消息作为标题，最多 50 字符
- 相对时间
- 第一条记录中的模型
- JSONL 文件大小

### F21：恢复校验

1. 从最后一个 compact 标记之后加载。
2. 最后一行损坏直接丢弃；中间坏行跳过并产生警告，然后重新验证消息合法性。
3. 悬空 tool call 截断到对应 assistant 之前。
4. 超过 Feature 008 自动阈值时先压缩。
5. 最后活动时间超过 6 小时时，追加时间跨度提醒。

### F22：事务切换

恢复采用事务顺序：完整读取并验证目标会话 → 打开目标 Writer → 必要时压缩 → 原子替换当前 Conversation/SessionContext/Writer → 最后关闭旧 Writer。任一步失败都继续保留当前会话。

### F23：UI 提示

恢复时显示加载提示；成功后显示：

```text
已恢复会话 <session_id>，共 <N> 条消息
```

### F24：新会话保留

恢复其他会话时不删除刚创建的新会话目录或 JSONL。

### F25–F26：过期清理

启动后在后台虚拟线程清理超过 30 天的会话。只处理严格匹配 ID 格式的真实目录，不跟随符号链接，当前会话永不删除；单个删除失败仅告警。

## 第 4 层：自动笔记

### F27：笔记分类

- `user_preference`
- `correction_feedback`
- `project_knowledge`
- `reference_material`

### F28：存储格式

每条笔记为独立 Markdown 文件，包含 YAML frontmatter：

```markdown
---
type: user_preference
title: 简洁回复，不要尾部摘要
created: 2026-06-01T10:30:00+08:00
updated: 2026-06-01T10:30:00+08:00
scope: user
source: conversation
---

用户偏好简洁回复，每次完成后不要在结尾重述刚做了什么。
```

## 自动笔记补充需求

### F29：两级存储

项目级目录为 `<workspace>/.mewcode/memory/`，用于项目知识和参考资料；用户级目录为 `~/.mewcode/memory/`，用于用户偏好和纠正反馈。具体级别由记忆更新 LLM 判断。

### F30：MEMORY.md 索引

每级维护一个 `MEMORY.md`，每行格式为：

```text
- [<type>] <title> — <一句话描述>
```

单个索引不超过 200 行/25KB；更新后超限时，由 LLM 决定合并或淘汰旧条目。注入前仍需执行本地硬限制，不能只依赖模型遵守。

### F31：文件名

LLM 提议 `<type>_<short_slug>.md`；slug 必须全小写并以下划线分隔。执行层必须再次校验 `^[a-z0-9]+(?:_[a-z0-9]+)*$`，禁止目录分隔符和路径逃逸。

### F32：索引刷新

启动时及每次成功更新后，按“项目级在前、用户级在后”重新读取并拼接索引。

### F33：注入内容

索引文本进入 `long-term-memory` 系统提示模块。只注入索引，不注入笔记全文；需要详情时由模型通过 `read_file` 读取。

### F34：索引预算

合并后的 UTF-8 内容最多 25KB，超出时安全截断并追加 `(index truncated)`。模块优先级固定为 `custom-instructions=150`、`long-term-memory=120`、`text-output=100`。

### F35：触发条件

Agent 自然完成后，在“每 5 个完成回合”或用户消息包含 `记住/记忆/别忘/remember/memo` 时触发。

### F36：异步执行

使用独立 virtual thread，不阻塞下一次输入；同一进程同时最多运行一个记忆更新。

### F37：更新输入

输入仅包含本轮最近消息和两级完整索引。

### F38：Provider 请求

复用当前会话 Provider，请求不携带工具定义，模型不得调用工具。

### F39：结构化操作

模型返回 JSON 数组，元素为 create/update/delete：

```json
[
  {"action":"create","level":"project","type":"project_knowledge","title":"...","slug":"...","content":"..."},
  {"action":"update","level":"user","filename":"user_preference_terse_replies.md","title":"...","content":"..."},
  {"action":"delete","level":"project","filename":"project_knowledge_old_api.md"}
]
```

空数组表示无需更新。解析后必须执行 schema、枚举、文件名和目录边界校验。

### F40：执行操作

create 创建带 frontmatter 的笔记并更新索引；update 原子替换笔记并更新索引条目；delete 只允许删除对应 memory 根目录内、索引已登记的合法文件，并移除索引条目。

### F41：去重

语义去重由 LLM 判断；文件名冲突、重复索引和路径边界仍由执行层机械防护。

### F42：失败隔离

LLM、JSON、磁盘错误只记录脱敏日志，不影响主会话、不自动重试。

## 集成与生命周期

- F43：`SystemPromptAssembler` 接受 instructions 和 memory；非空才挂载对应模块。最终优先级固定为 `custom-instructions=150`、`long-term-memory=120`、`text-output=100`，避免相同优先级依赖稳定排序。
- F44：Conversation 支持可选 `onAppend` 和 `onReplace` 回调；回调必须在释放 Conversation 锁后执行，避免磁盘 I/O 持有会话锁。
- F45：启动流程依次加载指令、初始化记忆索引、创建新会话并后台清理旧会话，再进入 TUI。
- F46：`/resume` 与 Agent run 互斥；运行中请求恢复时提示“请等待当前任务完成”。
- F47：记忆更新只读对话快照、只写 memory 目录，可与 `/compact` 并发；两次记忆更新之间由独立锁串行化。

## 非功能需求

- N1：指令加载目标 200ms 内；JSONL append 目标 10ms 内；50 个会话扫描目标 500ms 内。性能验收必须在本地磁盘和预热 JVM 下执行，文件系统强制 sync 不保证在所有硬件上达到 10ms。
- N2：Writer append、记忆 Store 更新和 Manager 更新分别使用明确锁保护。
- N3：缺少指令/记忆目录不影响启动；旧格式 session 不展示、不自动删除。
- N4：include、JSONL、索引和列表核心逻辑可离线测试；LLM 通过 LlmClient mock。
- N5：指令、JSONL、记忆和恢复错误独立降级，不使主进程崩溃。
- N6：笔记与索引不得保存 API Key、Authorization、Cookie、密码和疑似高熵密钥；日志同样脱敏。
- N7：异步记忆更新同时最多一个，单次受 provider request timeout 约束；退出时最多等待 5 秒后取消。

## 不做的事

- 不做向量数据库或 RAG。
- 不做团队记忆同步。
- 不在启动时自动恢复最近会话。
- 不做会话合并。
- 不做记忆质量反馈优化。
- 不做指令文件热更新。
- 不做笔记全文搜索。
- 不展示或清理旧格式 session ID。

## 验收标准

### 项目指令

- AC1：三层按优先级加载，缺失层静默跳过。
- AC2：正常 include 被正文替换。
- AC3：6 层 include 链在第 6 层给出深度警告。
- AC4：include 环路被检测并停止展开。
- AC5：真实路径越界或符号链接逃逸被拒绝。
- AC6：二进制或不可读 include 被隔离且不阻断其他层。

### 会话存档与恢复

- AC7：ID 匹配 `yyyyMMdd-HHmmss-[0-9a-f]{4}`，JSONL 第一条含 model。
- AC8：user/assistant/tool 和 compact 标记均为单行合法 JSON。
- AC9：Conversation 的结构化消息经 JSONL 往返后保持等价。
- AC10：compact 标记之后只恢复新消息序列。
- AC11：不完整尾行可丢弃，中间坏行跳过后重新验证结构。
- AC12：`/resume` 不发送给 LLM。
- AC13：列表支持选择、过滤和取消。
- AC14：孤立工具调用被截断或补齐为合法工具结果。
- AC15：超限会话先压缩，再进入空闲态。
- AC16：超过 6 小时追加时间跨度提醒。
- AC17：恢复成功后继续追加同一个 JSONL。
- AC18：恢复失败保持原 Conversation、Writer 和 SessionContext 不变。

### 清理

- AC19：31 天前的新格式目录被后台删除。
- AC20：旧格式、当前会话和符号链接目录不删除。

### 自动笔记

- AC21：显式偏好可创建合法 frontmatter 笔记。
- AC22：笔记变更同步更新对应 MEMORY.md。
- AC23：新会话系统提示只注入两级索引。
- AC24：异步更新不阻塞下一条用户消息。
- AC25：更新失败只记录脱敏日志，不影响会话。
- AC26：合并索引超过 25KB 时被本地截断并标注。

### 集成

- AC27：instructions/memory 非空时进入正确模块，空值跳过。
- AC28：Conversation append/replace 回调次数和参数正确；无回调保持兼容。
- AC29：Agent run 与 `/resume` 互斥，RESUMING 状态不能发起新 run。
