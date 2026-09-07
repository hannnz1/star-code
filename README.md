# Star Code

**基于 Java 21 的终端 AI 编程助手。**

Star Code 将大模型对话、文件工具、命令执行和多 Agent 协作组合为一个编程工作流：理解任务、读取代码、实施修改，再通过构建与测试验证结果。

项目参考本地 Mew Code 的模块设计实现，并加入独立的 benchmark 与验证记录。当前以交互式终端为主要入口。

## 核心能力

| 模块 | 功能 |
| --- | --- |
| Agent Loop | 流式对话、连续工具调用、执行预算、取消与错误处理 |
| 模型接入 | Anthropic、OpenAI Responses、Chat Completions 兼容协议 |
| 工具系统 | 文件读取、搜索、写入、编辑与 Shell 命令执行 |
| MCP | 接入 stdio / HTTP 服务；模型侧工具检索与完整 schema 按需加载 |
| 上下文管理 | 大工具结果卸载、上下文压缩、恢复信息及 Token 用量记录 |
| 会话与记忆 | 会话持久化、恢复、项目与用户级 Memory |
| 权限管理 | 路径检查、危险命令拦截、分层规则、交互审批与会话授权 |
| Skill / Hook | 按需加载技能；在生命周期事件中执行自动化动作 |
| Sub-Agent | 定义式角色、Fork 子会话、后台任务与消息协作 |
| Git Worktree / Agent Team | 独立工作副本、团队任务、成员邮箱及结果回收 |
| 文件检查点 | 记录专用文件工具修改，支持文件和对话回退 |

## 快速开始

### 环境要求

- JDK 21。
- Git；使用 Worktree 时，工作目录必须是至少有一次提交的 Git 仓库。
- 可访问的模型服务，以及对应的 API key。
- 项目附带 Gradle Wrapper，无需单独安装 Gradle。

### 1. 获取项目并构建

Windows PowerShell：

```powershell
git clone https://github.com/hannnz1/star-code.git
cd star-code
.\gradlew.bat test shadowJar
```

Linux / macOS 的构建命令：

```bash
git clone https://github.com/hannnz1/star-code.git
cd star-code
bash gradlew test shadowJar
```

生成的可执行包为 `build/libs/star-code.jar`。目前已有 Windows 全量测试记录；Linux/macOS 的完整运行验证仍待完成。

### 2. 配置模型

复制 [config.example.yaml](config.example.yaml) 为 `config.yaml`，填写模型服务信息。示例配置默认启用了本地代理；不使用该代理时，将 `proxy.enabled` 改为 `false`。

```yaml
system_prompt: |
  You are Star Code, a terminal AI coding assistant.
  Reply in the user's language and verify code changes.

request_timeout_seconds: 120
proxy:
  enabled: false

providers:
  - name: My Provider
    protocol: openai-compat
    base_url: https://your-provider.example/v1
    api_key_env: STAR_CODE_API_KEY
    model: your-model-id
    thinking: false
    context_window: 128000

agent:
  max_turns: 40
  max_tool_calls: 100
```

将示例地址、模型 ID 和上下文窗口替换为服务实际支持的值。密钥从 `api_key_env` 指定的环境变量读取。

| `protocol` | 请求协议 |
| --- | --- |
| `anthropic` | Anthropic Messages |
| `openai-responses` | OpenAI Responses |
| `openai-compat` | Chat Completions，客户端在 API 根地址后追加 `/chat/completions` |
| `openai` | `openai-responses` 的兼容别名 |

Chat Completions 接口需支持流式工具调用；`stream_options.include_usage` 和启用思考后的 `reasoning_effort` 是否可用，取决于目标服务。

### 3. 启动

Windows PowerShell：

```powershell
$env:STAR_CODE_API_KEY = "你的 API key"
java -jar build/libs/star-code.jar config.yaml
```

Linux / macOS：

```bash
export STAR_CODE_API_KEY="你的 API key"
java -jar build/libs/star-code.jar config.yaml
```

启动时的当前目录就是工作区。要操作其他项目，请先进入目标目录，再使用 JAR 和配置文件的绝对路径启动。

## 使用方式

可以直接输入任务，例如：

```text
先阅读这个项目，说明入口、主要模块和测试运行方式。
修复这个异常，补充必要的回归测试，并运行相关测试。
将任务拆为两个可以独立修改的子任务，使用子 Agent 完成后整合验证。
```

按 Enter 发送，Ctrl+J 换行，Shift+Tab 切换权限模式。运行中的任务可通过 Esc 取消。

### 常用命令

| 命令 | 说明 |
| --- | --- |
| `/help` | 查看可用命令 |
| `/plan` | 进入只读计划模式 |
| `/do` | 恢复默认权限模式，并要求模型执行上一份计划 |
| `/review` | 要求模型审查当前代码 |
| `/status` | 查看模型、工作区、工具及 Token 用量 |
| `/permission` | 查看当前权限模式 |
| `/compact` | 手动压缩上下文 |
| `/session`、`/resume` | 查看当前会话、选择恢复已保存会话 |
| `/clear` | 开始新会话 |
| `/rewind` | 列出检查点 |
| `/rewind ID files` | 回退检查点对应的文件修改 |
| `/rewind ID conversation` | 仅回退对话 |
| `/rewind ID both` | 回退文件与对话；省略模式时默认为 both |
| `/memory` | 查看记忆文件列表 |
| `/skill`、`/active-skills`、`/reload-skills` | 查看、检查和刷新技能 |
| `/hooks` | 查看已加载的 Hook |
| `/worktree`、`/team` | 管理工作副本与团队 |
| `/exit` | 退出 |

## MCP 工具扩展

参考 [.mewcode.yaml.example](.mewcode.yaml.example) 创建项目级 `.mewcode.yaml`，配置需要连接的 MCP 服务。同名项目级服务配置覆盖用户级配置。

默认采用模型侧按需加载：模型先通过 `search_mcp_tools` 检索工具，再在下一轮请求中获得匹配工具的完整 schema。每个 Agent 独立维护加载状态，工具执行仍经过权限和 Hook 检查。

需要全量暴露 schema 时，可在启动前设置：

```powershell
$env:STAR_CODE_MCP_LOADING = "full"
```

默认值为 `lazy`。MCP 连接和 `tools/list` 仍在启动阶段执行，按需加载减少的是发送给模型的 schema，不是服务端工具发现量。

## 上下文、会话与扩展

系统提示由身份、执行规则、工具使用、输出风格、自定义指令、Skill 和 Memory 等模块组装。上下文管理结合大结果卸载、压缩摘要与恢复信息，为后续任务保留必要材料。

当前版本保留以下实际配置路径；这些兼容路径不代表项目名称仍为 Mew Code：

| 内容 | 路径 |
| --- | --- |
| 项目指令 | `MEWCODE.md`、`.mewcode/MEWCODE.md` |
| 用户指令 | `~/.mewcode/MEWCODE.md` |
| 技能 | `.mewcode/skills/`、`~/.mewcode/skills/` |
| 子 Agent 定义 | `.mewcode/agents/`、`~/.mewcode/agents/` |
| Hook | `.mewcode/hooks.yaml`、`~/.mewcode/hooks.yaml` |
| 会话 | `.mewcode/sessions/` |
| 项目 / 用户记忆 | `.mewcode/memory/`、`~/.mewcode/memory/` |
| 权限规则 | `.starcode/permissions.yaml`、`.starcode/permissions.local.yaml`、`~/.starcode/permissions.yaml` |

Hook 支持条件匹配、Shell、提示词和 HTTP 动作，以及异步和超时控制；subagent 类型的 Hook 动作目前为占位能力。

## 多 Agent 协作

内置 `general-purpose`、`explore`、`plan` 角色，支持自定义角色和 Fork 子会话。`TaskList`、`TaskGet`、`TaskStop` 与 `SendMessage` 用于管理后台任务。

子 Agent 定义中设置 `isolation: worktree` 可使用独立 Git 工作副本。有修改的副本会保留供主 Agent 检查和整合；子 Agent 返回完成消息不代表整个任务已通过统一测试。

Agent Team 提供持久化团队、共享任务和成员邮箱，包含进程内、tmux 和 iTerm2 后端。Windows 默认使用进程内后端；后台执行中的子 Agent 不支持跨进程恢复。

可选 Coordinator Mode 需要同时配置 `features.coordinator_mode: true` 和环境变量 `STAR_CODE_COORDINATOR_MODE=1`。启用后主 Agent 将文件修改委派给团队成员。

## 权限与执行边界

- 专用文件工具执行路径与符号链接边界检查；命令执行受危险命令规则、权限审批和超时约束。
- 权限弹窗支持单次允许、持久化本地规则、拒绝和本次会话允许。
- 会话授权限定于相同工具、路径或命令参数、执行目录、Agent 身份和权限模式；新建或恢复会话时清除。
- 主 Agent 默认最多40轮、100次工具调用，可通过 `agent` 配置调整；子 Agent 使用各自角色的轮次上限。
- `/rewind` 只记录专用写入/编辑工具，不撤销 Shell、外部编辑、长期 Memory 或其他外部副作用；单个记录文件上限16MiB，外部修改冲突会阻止回退。

可选 `STAR_CODE_SANDBOX=required` 为 Shell 子进程启用 Linux bubblewrap 或 macOS sandbox-exec。不可用时拒绝执行，不自动退回无沙箱模式；Windows 尚无该 OS 沙箱实现。网络默认禁用，可通过 `STAR_CODE_SANDBOX_NETWORK=true` 显式启用。

该沙箱不覆盖主 JVM、MCP、Hook 或外部团队进程，也不限制所有系统文件读取。Linux/macOS 的实际内核隔离验证仍待完成。

## 验证与 Benchmark

已保存的 Windows 验证批次包含 **233项测试，零失败、零错误、零跳过**；对应 JAR 的279个生产类和3个资源已完成一致性核验。

| 实验 | 已有结果 | 解释范围 |
| --- | --- | --- |
| MCP schema | 100工具 fixture 的估计 Token 从7377降至2420，减少约67.20% | 指定 tokenizer 的 schema 估计，不是整段会话的实际账单降低比例 |
| 多 Agent | 3个固定任务通过并行 Worktree、主 Agent 整合与统一测试 | 尚未完成单/多 Agent 配对加速比实验 |
| 权限回放 | 10条固定轨迹的弹窗中位数从12降至8 | 注入审批选择的策略回放，不是真实用户会话统计 |
| 长上下文 | 已保留压缩、失败、限流与中断记录 | 不足以证明8小时会话不丢上下文 |

详见 [当前验证状态](benchmarks/STAR_CODE_CURRENT_STATUS.md)、[功能对齐进度](benchmarks/feature-parity-v1/STATUS.md) 和 [本地验收记录](benchmarks/results/feature-parity-accepted.json)。不同实验对应不同代码版本，请以各报告记录的 commit、fixture 和运行条件为准。

`benchmarks/` 保存实验脚本与汇总；原始运行目录、用户配置和 Memory 默认不提交到 Git。复现实验时会在本地生成对应原始记录。

## 项目结构

```text
src/main/java/com/starcode/
├── agent/         # Agent Loop 与事件
├── llm/           # 模型协议与流式响应
├── tool/          # 工具注册、文件操作与 Shell
├── mcp/           # MCP 服务连接与工具接入
├── context/       # 上下文压缩与恢复
├── session/       # 会话与文件检查点
├── memory/        # 长期记忆
├── permission/    # 权限规则与审批
├── prompt/        # 系统提示组装
├── command/       # Slash 命令
├── skill/         # 技能目录与执行
├── hook/          # 生命周期 Hook
├── subagent/      # 子 Agent 定义与委派
├── task/          # 后台任务
├── worktree/      # Git 工作副本
├── team/          # 团队协作
└── ui/            # 终端交互
src/test/          # 自动化测试
benchmarks/        # 可复现实验与结果汇总
specs/             # 模块设计与实现记录
```

## 当前边界

Star Code 尚未完成与本地 Mew Code 的全部功能和性能对齐。当前未提供 Mew Code 的通用 `-p` 非交互运行、`--output-format stream-json` 或 `--remote` HTTP/WebSocket 服务入口。

真实模型服务互操作、完整终端回退流程、Linux/macOS 运行与沙箱验证仍有待完成；通用多模态输入和工具结果流式输出尚未支持。公开的测试与实验记录用于说明已验证范围，不代表所有兼容性和性能目标均已达成。

## 参考

项目参考本地 Mew Code Java 项目的 Agent、工具、上下文及协作模块设计。Star Code 的功能状态与实验结论以本仓库实际实现和验证记录为准。
