# Hook 生命周期挂钩系统 Spec

> Feature：012  
> 状态：IMPLEMENTED（真实 subagent action 不在本章交付范围）  
> 适用项目：Star Code（Java 21 + Gradle）

## 背景

Feature 011 已支持可复用 Skill，但 Skill 和 Slash Command 都需要显式触发。格式化、额外检查、提示注入和外部通知等动作具有固定生命周期时机，适合通过声明式 Hook 自动执行。

Hook 是现有权限、Agent Event 和 Skill 机制的补充，不是权限绕过入口。不可变黑名单、路径沙箱、显式 deny 和用户审批仍由权限系统负责；Hook 只在工具获得权限后执行额外检查。

## 目标

- G1：提供 11 个稳定生命周期事件和同步分派接口。
- G2：从两层 YAML 配置加载“事件 + 条件 + 动作”规则；坏规则隔离且不阻断启动。
- G3：权限规则与 Hook 条件共享 exact、glob、regex、not 匹配器。
- G4：支持 shell、prompt、HTTP、subagent 四类动作；subagent 本章只占位。
- G5：支持 only-once、异步执行、超时、取消和结构化拦截回灌。
- G6：不破坏权限、MCP、并发工具执行、上下文压缩、会话恢复和 Skill。

## 功能需求

### 共享匹配器

- F1：新增共享 Matcher：exact、glob、regex、not。正则在加载期编译，非法表达式使单条规则失效。
- F2：权限字符串保持旧 glob 语法，并新增 `=value`、`~regex`、`!inner` 前缀；`!=value`、`!~regex` 均可用。
- F3：权限规则解析失败输出 stderr，跳过该规则；其他规则和启动流程不受影响。

### Hook 配置

- F4：依次加载 `<workspace>/.mewcode/hooks.yaml`、`~/.mewcode/hooks.yaml`，两层叠加；同名时先加载者保留，后者告警并跳过。
- F5：顶层为 `hooks` 数组。规则字段：`name`、`event`、可选 `if`、`action`、`only_once`、`async`、`timeout`。
- F6：事件为 SessionStart、SessionEnd、SessionResume、UserPromptSubmit、Stop、PreUserMessage、PreToolUse、PostToolUse、PreCompact、PostCompact、Notification。
- F7：每个 payload 都含 event、session_id、cwd、mode；事件按需增加 prompt、tool_name、tool_input、tool_result、is_error、trigger、before_tokens、after_tokens、kind、detail、iter。

### 条件

- F8：`if` 只能使用 `all_of` 或 `any_of` 之一，值为原子条件数组，不支持嵌套逻辑组。
- F9：原子条件包含 `field` 和 `match`；字段支持点分路径，不存在时按空串处理。
- F10：`match` 支持 exact、glob、regex、not；对象和数组以稳定 JSON 转成字符串。

### 动作

- F11：shell 使用平台 shell 执行配置命令，事件 payload 以稳定单行 JSON 写入 stdin。exit 0 成功；拦截事件 exit 2 表示拒绝；其他非零、超时和启动错误只记日志。
- F12：prompt 把文本加入下一次 LLM 请求的单次 reminder 队列；不写 Conversation、不写 JSONL。
- F13：http 支持 method、headers、body 模板 `${field}`；缺省 body 为 payload JSON。拦截事件仅在 2xx 且响应为 `{"decision":"block","reason":"..."}` 时拒绝；网络和解析错误默认放行。
- F14：subagent 校验 `agent_name` 与 `prompt`，运行时仅输出固定 NOT_IMPLEMENTED 日志。
- F15：`only_once` 在同一会话首次匹配并实际执行后生效；新建或恢复会话时清空。
- F16：非拦截事件允许 async，通过 virtual thread 后台运行；PreToolUse 与 UserPromptSubmit 禁止 async，违规规则加载时跳过。
- F17：timeout 默认 30 秒；Hook 失败统一 stderr 记录，不重试、不终止主流程。

### 生命周期集成

- F18：SessionStart 在新会话可用后触发；SessionEnd 在退出、clear、resume 离开旧会话前触发；SessionResume 在恢复完成后触发。
- F19：UserPromptSubmit 在普通用户输入进入 Conversation 前触发且可拦截；拦截时不发 LLM，输入文本回显错误原因。
- F20：PreUserMessage 在每次 provider 请求前触发；Stop 只在 Agent 自然完成、Completed 事件前触发。
- F21：工具顺序固定为权限判定 → PreToolUse Hook → 工具实现 → PostToolUse Hook。权限拒绝不运行 PreToolUse；Hook 拦截返回 `HOOK_BLOCKED` 且保留 call ID，并继续 Agent Loop。
- F22：PostToolUse 对成功、权限拒绝、Hook 拦截和工具失败均触发；只读批次仍可并发，结果按原序发布。
- F23：PreCompact/PostCompact 覆盖自动、手动、紧急三条路径；Notification 覆盖权限审批和流错误。
- F24：所有注入 prompt 在下一次请求 reminder 中按规则声明顺序拼在 plan reminder 后；消费后清空。
- F25：新增 `/hooks` 本地命令，列出规则名、事件、动作和 flags，并显示来源；无规则时显示 `No hooks loaded.`。

## 非功能需求

- N1：没有匹配规则时分派开销目标低于 1 ms；规则匹配不执行磁盘 I/O。
- N2：Matcher、only-once 和 reminder 队列线程安全；异步任务可在关闭时取消。
- N3：payload JSON 键按字典序稳定；日志不得输出 provider 密钥或 HTTP 敏感 header 值。
- N4：测试默认离线，不调用真实 LLM/HTTP；shell 测试只执行短小、无副作用命令。
- N5：单配置、单规则、单动作失败均隔离；配置文件缺失静默。
- N6：fork Skill 子 Agent 默认使用空 HookEngine，避免同一动作重复触发。

## 不做的事

- 不真实实现 subagent Hook。
- 不持久化 only-once，不热重载 hooks.yaml。
- 不支持条件递归、规则优先级、依赖、重试、独立日志文件或 `@include`。
- 不允许 Hook 修改权限配置，也不把 Hook 输出写入长期记忆。

## 验收标准

- AC1：权限 exact/regex/not/glob 均匹配正确，旧 glob 配置继续工作，非法规则告警并跳过。
- AC2：两层 Hook 合并、重名隔离、坏 YAML/未知事件/非法 matcher/非法 async 均不阻断启动。
- AC3：shell exit 2 可分别拦截 UserPromptSubmit 和获准后的 PreToolUse；工具结果使用 `HOOK_BLOCKED`。
- AC4：prompt 注入只出现于下一次 reminder，不进入会话历史且消费后清空。
- AC5：PostToolUse async 不阻塞 Agent；失败只写 stderr。
- AC6：HTTP block 响应可拦截，网络或 JSON 错误默认放行。
- AC7：only-once 同会话只执行一次，clear/resume 后重新可执行。
- AC8：Session/Stop/Compact/Notification 生命周期事件在规定位置触发。
- AC9：`/hooks` 展示当前规则和来源。
- AC10：完整测试和 Shadow JAR 构建通过，既有权限、MCP、上下文、会话与 Skill 测试无回归。
