# Star Code 规格索引

## 文档规则

- 本目录是 Star Code 功能规格的唯一权威入口；根目录的 `spec.md`、`plan.md`、`task.md`、`checklist.md` 是早期 V1 草案，只用于历史追溯。
- 每章使用 `spec.md` 描述目标行为，`plan.md` 描述设计，`tasks.md` 描述实施切片，`checklist.md` 保存验收证据，`implementation-report.md` 记录当前偏差。
- 当前实现不得反向修改规范目标。尚未满足的规范必须在实现报告中标记为 `PARTIAL` 或 `NOT_IMPLEMENTED`。
- 后续章节可以扩展早期章节；发生覆盖时，后续章节必须明确列出被替代的需求编号。
- 全局数据模型、持久化和并发约束见 [`architecture-contracts.md`](architecture-contracts.md)。
- 文档问题与整改规则见 [`spec-quality-audit.md`](spec-quality-audit.md)；当前 Spec→Code 证据矩阵见 [`implementation-audit.md`](implementation-audit.md)。

## 状态定义

| 状态 | 含义 |
|---|---|
| `DRAFT` | 尚未批准，不得据此编码 |
| `APPROVED` | 需求已批准，尚未全部实现 |
| `PARTIAL` | 已有可运行实现，但仍存在明确缺口 |
| `IMPLEMENTED` | 目标代码已完成，尚缺完整验证 |
| `VERIFIED` | 自动测试通过且要求的人工验收已有证据 |
| `SUPERSEDED` | 已由另一份权威文档替代 |

## 章节状态

| 章节 | 功能 | 权威规格 | 当前状态 | 主要未闭环项 |
|---|---|---|---|---|
| ch01 | 多协议终端对话 | [`001-llm-terminal-chat/spec.md`](001-llm-terminal-chat/spec.md) | `IMPLEMENTED` | 真实双协议 E2E 证据需持续更新 |
| ch02 | 工具系统 | [`002-tool-system/spec.md`](002-tool-system/spec.md) | `IMPLEMENTED` | OS 级沙箱不在本章范围 |
| ch03 | 历史编号 | [`003-agent-loop/spec.md`](003-agent-loop/spec.md) | `SUPERSEDED` | 由 ch04 替代 |
| ch04 | Agent Loop | [`004-agent-loop/spec.md`](004-agent-loop/spec.md) | `IMPLEMENTED` | 真实双协议取消 E2E 仍需人工证据 |
| ch05 | 系统提示 | [`005-system-prompt-engineering/spec.md`](005-system-prompt-engineering/spec.md) | `IMPLEMENTED` | — |
| ch06 | 权限系统 | [`006-permission-system/spec.md`](006-permission-system/spec.md) | `IMPLEMENTED` | `.starcode` 为权限兼容目录，见全局契约 |
| ch07 | MCP 客户端 | [`007-mcp-client/spec.md`](007-mcp-client/spec.md) | `IMPLEMENTED` | 真实 HTTP server 人工验收 |
| ch08 | 上下文管理 | [`008-context-management/spec.md`](008-context-management/spec.md) | `IMPLEMENTED` | 极限上下文需真实 Provider 压力验收 |
| ch09 | 项目记忆与会话 | [`009-project-memory-session/spec.md`](009-project-memory-session/spec.md) | `IMPLEMENTED` | `/resume` 真实终端交互需持续验收 |
| ch10 | Slash 命令 | [`010-slash-command-system/spec.md`](010-slash-command-system/spec.md) | `IMPLEMENTED` | ch14 扩展了受控参数命令 |
| ch11 | Skill | [`011-skill-system/spec.md`](011-skill-system/spec.md) | `IMPLEMENTED` | 远程 GitHub 安装需联网人工验收 |
| ch12 | Hook | [`012-hook-system/spec.md`](012-hook-system/spec.md) | `IMPLEMENTED` | subagent action 明确延期 |
| ch13 | SubAgent | [`013-subagent-system/spec.md`](013-subagent-system/spec.md) | `IMPLEMENTED` | 真实 Provider E2E；Esc 转后台已明确不做 |
| ch14 | Worktree | [`014-worktree-isolation/spec.md`](014-worktree-isolation/spec.md) | `IMPLEMENTED` | 真实 Git 仓库/TUI E2E |
| ch15 | Agent Team | [`015-agent-team/spec.md`](015-agent-team/spec.md) | `IMPLEMENTED` | tmux/iTerm2 真实平台验收 |

## 命名约定

- Java 包名统一使用 `com.starcode.*`。
- 工具规范名使用 Registry 名称，例如 `read_file`、`write_file`、`edit_file`、`search_text`；UI 可显示 `Read`、`Write`、`Edit`、`Search`，但权限、Hook 和 SubAgent 配置必须使用规范名。
- `.mewcode/` 是当前会话、记忆、Skill、Hook、SubAgent、Worktree 与 Team 数据的兼容主目录。
- `.starcode/permissions*.yaml` 是 ch06 已发布的权限配置兼容路径；在完成显式迁移方案前不得静默改名。
- 验证命令统一使用 Gradle Wrapper：Windows 为 `.\gradlew.bat`，Unix 为 `./gradlew`。
