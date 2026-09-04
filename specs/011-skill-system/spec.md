# Skill 系统 Spec

> 状态：IMPLEMENTED（发现、热重载、inline/fork、安装与调用审计已实现）  
> Feature：011

## 背景与目标

- G1：用户无需修改 Java 即可增加可复用的 Agent SOP。
- G2：用户级与项目级 Skill 自动发现，项目同名覆盖用户。
- G3：正文按需重读，编辑 Skill 后无需重启即可生效。
- G4：inline 与 fork 使用统一渲染和 Host 接口，Skill 包不依赖 UI/Agent 具体类。
- G5：远程安装有严格来源、大小、文件数、深度和原子发布限制。

## 功能需求

- F1：扫描 `~/.mewcode/skills/<name>/` 和 `<workspace>/.mewcode/skills/<name>/`；目录缺失、不可读或单 Skill 损坏不影响其他条目。
- F2：优先读取 `skill.yaml + prompt.md`，否则读取可带 YAML frontmatter 的 `SKILL.md`。
- F3：元数据包括 name、description、whenToUse、tags、mode、model、forkContext；缺省 mode=`inline`、forkContext=`none`。
- F4：启动阶段建立元数据目录；`getFull` 每次从源目录重读正文，失败时保留上一个完整缓存。
- F5：`$ARGUMENTS` 被参数替换；没有占位符且参数非空时追加 `## User Request`。
- F6：inline 激活 SOP、记录调用并把渲染正文作为普通 user 消息发送给主 Agent。
- F7：fork 按 none/recent/full 选择父结构化消息种子，在独立 Agent Loop、ContextManager、权限模式、取消和用量状态中运行，最终文本写回主对话。
- F8：Skill 自动注册为 `/<skill-name>` PROMPT 命令，描述以 `[skill]` 结尾；内置命令冲突时保留内置命令并告警跳过 Skill 命令。
- F9：`/skill` 列出目录；`/reload-skills` 重新扫描并原子刷新动态命令。
- F10：Catalog 名称与描述进入稳定系统提示；活动 Skill 正文进入动态环境；`/clear` 清空活动状态但不删除 Skill 文件。
- F11：只读 `load_skill` 工具激活最新正文；安装工具属于有副作用工具并走权限流程。
- F12：远程安装仅接受 GitHub 官方 HTTPS tree/raw URL，通过 Contents API 下载；限制单文件 1 MiB、总计 8 MiB、64 文件、深度 4。
- F13：安装先写同级临时目录，验证存在有效 Skill 后原子发布；成功后刷新 Catalog 和命令，无需重启。
- F14：每次 inline/fork/tool 激活记录 skill 名、来源、时间和当前 session ID；记录失败不阻断执行。

## 非功能需求

- N1：同名后注册覆盖，目录列表顺序稳定且线程安全。
- N2：Skill 核心包不得 import `com.starcode.agent` 或 `com.starcode.ui`，通过 Host 接口反向依赖。
- N3：Skill 正文视为不可信提示，不能绕过权限、Hook、工作区路径或 SubAgent 嵌套限制。
- N4：安装路径必须防止 `..`、绝对路径、符号链接和非 GitHub 重定向逃逸。
- N5：日志和错误不得回显 Authorization 或 Token。

## 不做的事

- 本章 Slash Skill 命令不解析带引号的复杂参数语法。
- 不安装任意压缩包或任意网站目录。
- 不允许 Skill 注册覆盖内置命令。
- 不持久化 fork 子 Agent 的后台任务状态。

## 验收标准

- AC1：用户/项目两层加载且项目同名覆盖；坏 Skill 被告警隔离。
- AC2：`SKILL.md` 与 `skill.yaml + prompt.md` 均可加载，BOM 不污染 frontmatter。
- AC3：正文修改后下一次调用使用新内容；重读半成品失败时继续使用旧缓存。
- AC4：inline 进入主 Conversation/JSONL，`$ARGUMENTS` 规则正确。
- AC5：fork none/recent/full 的种子边界正确，子 Agent 状态隔离且用量合并。
- AC6：`/skill`、动态命令、补全和 `/reload-skills` 同步一致。
- AC7：`load_skill` 只读放行，活动正文在下一次请求环境中可见，`/clear` 后消失。
- AC8：GitHub tree/raw 安装满足大小、数量、深度、路径和原子发布限制。
- AC9：安装后无须重启即可调用新 Skill。
- AC10：每次 Skill 调用产生可追踪记录，记录失败不影响 Agent。
- AC11：完整 Skill 测试与 Shadow JAR 构建通过。
