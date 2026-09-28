# Python mewcode 基线功能差异检查

检查日期：2026-09-28。基准是桌面 Python mewcode 的实际入口和调用链；主要检查对象是当前 Python StarCode/MUSE，另附原 Java StarCode 的差异。此次只检查和运行离线测试，没有修改产品代码，也没有调用收费模型 API。

## 结论

**存在功能缺口，当前版本还不能称为 Python mewcode 的完整等价替代。** 基本编程、三类模型协议、MCP 按需加载、Skill、持久化子任务、团队消息/任务板均有可达实现；最明显的缺口集中在自动记忆维护、模型思考配置、部分文件工具参数和协调者模式。Windows 长路径下的隔离 worktree 协作还存在可复现故障。

迁移目录中保留旧 `mewcode/` 模块，不代表这些模块已接入当前产品。公开 `mewcode` 入口转到 `muse.compat_cli.main`，实际任务由 `src/muse/` 服务执行。旧 `_run_prompt_impl`、自动记忆提取器、沙箱后端等不能仅凭文件存在计为已实现。

有些差异是已有文档声明的行为调整，例如 SQLite 记忆、注册工作区边界、持久化团队、逐次执行审批和固定使用所选 StarCode 模型。这些需要明确决定是否接受，不能一律当成程序错误，也不能忽略后继续声称完全兼容。

## 范围和证据标准

| 对象 | 本地目录 | 角色 |
|---|---|---|
| Python mewcode | `C:/Users/Administrator/Desktop/project/mewcode-python` | v0.2.0 功能基线 |
| 原 Java StarCode | `C:/Users/Administrator/Desktop/project/star code` | 原始实现，附录比较 |
| Python StarCode/MUSE | `C:/Users/Administrator/Documents/Codex/2026-09-26/ai-starcode-muse-coding-agent-python/outputs/muse-next` | v0.3.0rc8，主要检查对象 |

“已接入”表示公开入口到实现的调用链存在，并非真实模型 benchmark 已通过。“缺失”表示基线有可达功能、当前公开调用链没有等价实现。“改变/部分”表示只有部分能力或使用方式发生改变。“运行故障”表示已有实现但本次或既有实际测试失败。

此次未运行基线和 Java 的完整测试套件，不能将本报告当成三方实测胜负排名。不用文件数量或功能条目比例推算开发完成率。

## 当前 Python StarCode/MUSE 功能矩阵

证据栏中 `基线:` 指桌面 mewcode，其他路径指当前 MUSE。行号以本次检查文件为准。

| 功能 | Python mewcode 基线行为 | 当前 Python StarCode/MUSE | 判定 | 主要证据 |
|---|---|---|---|---|
| 读/写/精确编辑文件 | ReadFile、WriteFile、EditFile | read_file、write_file、edit_file，工作区边界和文件历史 | 已接入 | `src/muse/tools/registry.py:41`；`src/muse/tools/files.py:48` |
| 按行读取大文件 | ReadFile 支持 offset、limit，带行号 | read_file 只接受 path；整文件读入，输出超限另行 offload | 部分，缺按行接口 | 基线 `mewcode/tools/read_file.py:21`；当前 `src/muse/tools/registry.py:41` |
| 内容搜索 | Grep 使用正则表达式 | search_text 为不区分大小写的字面子串匹配，有命中数量上限 | 部分，缺正则搜索 | 基线 `mewcode/tools/grep.py:36`；当前 `src/muse/tools/files.py:76` |
| 文件枚举 | Glob | list_files 支持 pattern、忽略目录、数量上限 | 已接入，参数契约改变 | `src/muse/tools/files.py:56` |
| Shell 与代码验证 | Bash | run_command、verify_command；持久化回执和进程树取消 | 已接入 | `src/muse/tools/registry.py:52`；`src/muse/tools/process_tree.py` |
| ReAct/工具循环 | 模型调用、工具回执、多轮执行 | 持久化 Agent loop、恢复、预算和完成检查 | 已接入 | `src/muse/agent/loop.py`；`tests/muse/unit/test_agent_completion.py` |
| 三类模型接入 | Anthropic、OpenAI Responses、Chat Completions | 三种协议均有流式适配和工具调用解析 | 已接入，真实模型兼容性另验 | `src/muse/providers/compatible.py:92`；`tests/muse/unit/test_provider_stream.py` |
| thinking 配置 | 基线 client 使用 thinking 参数，处理思考事件 | 配置读取 thinking，但当前 provider 请求构造未使用该字段 | 缺失/配置失效 | 基线 `mewcode/client.py:215`；当前 `src/muse/config.py:23`、`src/muse/providers/compatible.py:101`、`src/muse/providers/anthropic.py:9` |
| 思考流显示/状态 | 基线产生 ThinkingText/ThinkingComplete，并保存对应协议状态 | 当前主要事件为 text/call/usage/done，未恢复同等思考事件能力 | 缺失 | 基线 `mewcode/client.py`；当前 `src/muse/providers/anthropic.py`、`src/muse/providers/compatible.py` |
| 沿用原模型配置 | provider、model、key 等 | 保留所选 StarCode provider；不会让角色/Skill 静默换模型 | 已接入 | `src/muse/config.py`；`src/muse/extensions/roles.py:67` |
| 跨会话持久化记忆 | Markdown 记忆笔记，会话日志另存 JSONL | SQLite user/project 记忆；save/search/delete，任务加载 | 已接入，存储和写入契约改变 | `src/muse/memory/service.py`；`src/muse/extensions/memory.py` |
| LLM 自动提取记忆 | Agent 完成时触发 `_extract_memories`，模型提炼笔记 | 当前公开链没有接入旧 MemoryManager.extract；保存需调用持久化工具 | 缺失 | 基线 `mewcode/agent.py:660`、`:976`；当前 `src/muse/memory/service.py` |
| 自动整理记忆 | MemoryConsolidator 满足时间/会话门槛后后台合并整理 | 当前没有接入旧 consolidator 的 maybe_run 流程 | 缺失 | 基线 `mewcode/agent.py:663`、`mewcode/memory/consolidation.py` |
| 相关记忆选择 | find_relevant_memories 按任务选择笔记，有时效信息 | 当前 search 为文本筛选，for_task 加载最近更新的最多 100 条 | 部分，缺语义选择与同等时效策略 | 基线 `mewcode/app.py:1275`；当前 `src/muse/memory/service.py:41` |
| 项目指令与 @ 引用 | 用户目录、Git 根到工作目录的层级加载和引用 | 注册工作区根文件快照；引用限工作区、深度和链接边界 | 部分，隐式全局/祖先加载已取消 | 基线 `mewcode/memory/instructions.py`；当前 `src/muse/agent/instructions.py:46`；`docs/java-behavior-audit.md:49` |
| 上下文压缩与历史召回 | 基线渐进压缩、摘要和恢复信息 | 确定性压缩、保留原文证据、offload、recall_history | 已有替代实现；不是原算法的等价实现 | `src/muse/agent/context.py`；`src/muse/tools/registry.py`；`tests/muse/unit/test_context.py` |
| 8 小时以上事实保留 | 项目介绍的长期运行指标，需要时间跨度实测 | 有压缩和召回实现；本次仅离线结构测试 | 不在此次验收范围 | 不能从单元测试推出 8 小时实测已完成 |
| MCP 按需加载 | ToolSearch/McpCall，lazy/full 策略 | 服务器/工具发现和显式调用，持久化审批 | 已接入，授权契约改变 | `src/muse/extensions/mcp.py`；`tests/test_durable_mcp.py` |
| Skill 加载/安装/fork | LoadSkill、InstallSkill、fork recent/full/none | list/load/spawn/install，带来源校验、共享预算和持久化子任务 | 已接入；不同模型请求会拒绝 | `src/muse/extensions/skills.py:117`；`tests/test_durable_skills.py` |
| Skill 快捷 slash 命令 | App 注册每个 Skill 的命令及别名 | /skill NAME 展示目录信息；执行需在任务中请求工具 | 部分，缺原快捷执行入口 | 基线 `mewcode/app.py:836`；当前 `src/muse/terminal.py:118` |
| 子 Agent 与角色 | general/explore/plan，可选 verification、项目和用户角色 | 四类内置角色、项目自定义角色、持久化子任务 | 已接入；用户目录角色未自动发现 | 基线 `mewcode/agents/loader.py:16`；当前 `src/muse/extensions/roles.py` |
| 角色单独模型选择 | 基线角色定义可指定模型 | 当前只允许 inherit 或所选 StarCode 模型 | 行为改变，符合此前保留原配置要求 | `src/muse/extensions/roles.py:67` |
| 团队协作/消息/任务板 | TeamCreate、SendMessage、共享任务及成员后端 | SQLite root-task group、inbox/board、Worker 子任务与自动唤醒 | 已接入，团队运行后端改变 | `src/muse/extensions/teams.py`；`tests/test_durable_teams.py`、`tests/test_durable_delegation.py` |
| 协调者模式 | 开启后收窄主 Agent 工具集，由子 Agent 执行代码操作 | 当前没有相应 coordinator 工具过滤入口 | 缺失 | 基线 `mewcode/app.py:955`；当前 `src/muse/` 搜索无对应实现 |
| tmux/iTerm2/--teammate | 基线可启动独立队友进程/窗格 | 当前不支持该入口；以 API/Worker 和团队视图替代 | 已声明的行为改变 | 基线 `mewcode/__main__.py:23`；当前 `src/muse/compat_cli.py:59` |
| 隔离 worktree 子任务 | 基线 worktree 管理/集成 | spawn_worktree、review/merge/integrate/remove 都有接入 | 有实现，但 Windows 长路径故障 | `src/muse/extensions/worktrees.py`；本次失败工具回执 |
| 默认/acceptEdits/plan 权限模式 | default 写入询问；acceptEdits 写入允许；plan 只读 | plan 只读有效；default 和 acceptEdits 没有分别传入任务权限策略，工作区文件写入同走 risk=write | 部分，default/acceptEdits 区分缺失 | 基线 `mewcode/permissions/modes.py`；当前 `src/muse/compat_cli.py:69`、`:91`；`src/muse/tools/registry.py` 审批分支只对 execute |
| bypass 和可复用执行授权 | 基线支持 bypassPermissions、规则授权 | 当前不提供 bypass；执行操作绑定动作摘要和有效期 | 已声明的行为改变 | `docs/java-behavior-audit.md:81`；`src/muse/compat_cli.py:69` |
| OS 沙箱 | 基线可选 Linux bwrap/macOS Seatbelt，/sandbox 操作 | 当前没有接入旧 OS 沙箱后端或 /sandbox；只有路径边界和进程管理 | 缺失；不能称为内核隔离 | 基线 `mewcode/sandbox/`；当前 `src/muse/tools/process_tree.py:1` |
| Plan → 执行 | 基线会话内 plan 模式/ExitPlanMode | /plan、/do、/review 创建不同任务，非同会话切换 | 已声明的行为改变 | `src/muse/terminal.py`；`docs/python-runtime-operations.md` |
| 会话/文件回退 | 基线 /rewind files/conversation/both | 有文件历史和会话分叉；不提供同等 both 联合回退契约 | 部分，已声明行为改变 | `src/muse/tools/files.py:136`；`src/muse/terminal.py` |
| 调试 trace 命令 | 基线 App 注册 /trace，TraceManager 管理追踪 | 有 /events 和持久化工具回执，没有原 /trace 入口和同等展示契约 | 部分 | 基线 `mewcode/app.py:944`；当前 `src/muse/terminal.py:23` |
| 生命周期 Hooks | 配置加载和执行；基线某些执行器为占位 | 当前有 shell/HTTP/prompt/child 路径及持久化回执 | 已接入；不能把基线占位计作缺口 | `src/muse/extensions/hooks.py`；`tests/test_durable_hooks.py` |
| -p / stream-json | 基线直接执行和自己的 NDJSON 事件 | 连接现有 API/Worker 提交任务；事件结构和退出码改变 | 已接入，CLI 协议改变 | `src/muse/compat_cli.py:16`、`:59` |
| 远程/网页入口 | 基线 WebSocket 0.0.0.0:18888 浏览器 UI | 当前 loopback API 和网页，Worker 独立启动 | 有替代入口，网络/部署契约改变 | 基线 `mewcode/__main__.py:59`；当前 `src/muse/compat_cli.py:82` |

### 未误计为缺失的项目

- **批量替换参数**：基线 EditFile 本身要求 old_string 唯一，没有 replace_all；当前也要求唯一匹配，因此不能把 replace_all 缺失称为迁移退化。
- **通用 Markdown 自定义 slash loader**：基线存在 loader 文件，但本次未发现公开 App 接入；只将已接入的 Skill 快捷命令列为实际差异。
- **先读再改缓存**：基线工具类有可选 file_state_cache，但本次未发现 App/主入口实际注入，不作为已证实回归。
- **同轮并行工具执行**：基线有相关辅助方法，但未确认运行入口调用，不据此声称当前缺并行工具能力。
- **Hooks 子 Agent 占位**：基线 executor 有 stub，不能用方法名当完整实现。
- **Windows 原生内核沙箱**：基线的 OS 后端主要为 Linux/macOS，不能声称基线已提供 Windows 同等沙箱。

## 本次离线验证

### 结果

1. 在当前仓库的较长工作路径运行 15 个相关测试文件：**58 passed，1 failed，13.78 秒**。
2. 读取失败任务数据库的 `tool_calls.result`：spawn_worktree 返回 **`fatal: '$GIT_DIR' too big`**，未创建子任务，父任务随后结束。这不是模型没调用工具。
3. 同一 worktree 测试文件换到较短的 `C:/Users/Administrator/Documents/Codex/audit-mew-0928/run1`：**2 passed，2.08 秒**。
4. 在短路径运行扩大后的 19 个测试文件：**87 passed，13.47 秒**。

**87 项通过不抵消长路径失败。** 当前 worktree 创建对 Windows 路径长度敏感；短路径对照验证了触发条件，完整适配方案尚未实施。工作区路径、Git 版本/限制及派生路径的具体边界还应纳入后续回归测试。

失败证据留在：

`work/feature-audit-2026-09-28/pytest-run1/test_worktree_child_uses_isola0/data/state.sqlite3`

只读取了工具调用结果，没有输出该目录中的访问令牌或配置密钥。

### 可复现测试命令

在当前 Python MUSE 仓库执行，TEMP/TMP 指向已有可写短目录，避免 Windows 临时目录权限问题：

```powershell
$auditShortTemp='C:\Users\Administrator\Documents\Codex\audit-mew-0928'
$env:TEMP=$auditShortTemp
$env:TMP=$auditShortTemp
.\.venv\Scripts\python.exe -m pytest `
  tests/test_compat_entry.py tests/test_terminal_service.py tests/test_terminal_context.py `
  tests/test_project_guidance.py tests/test_durable_memory_tools.py tests/test_durable_roles.py `
  tests/test_durable_skills.py tests/test_durable_mcp.py tests/test_durable_hooks.py `
  tests/test_durable_delegation.py tests/test_durable_worktrees.py tests/test_durable_teams.py `
  tests/test_durable_anthropic.py tests/muse/unit/test_provider_stream.py `
  tests/muse/unit/test_permissions.py tests/muse/unit/test_context.py `
  tests/muse/unit/test_agent_loop.py tests/muse/unit/test_agent_completion.py `
  tests/muse/integration/test_artifacts_documents_memory.py -q `
  --basetemp C:/Users/Administrator/Documents/Codex/audit-mew-0928/run2
```

重跑时使用新的 basetemp 目录即可，不必删除已有证据。上述测试使用脚本模型或本地模拟 HTTP，不花 API 额度。

测试覆盖入口、终端、指令边界、记忆工具、角色、Skill、MCP、Hooks、持久化协作、worktree、模型协议、上下文和完成判定。它们没有覆盖未接入的功能，也不替代真实模型能力评测。

## 修复/补齐顺序和验收标准

| 优先级 | 工作 | 完成标准 |
|---|---|---|
| P0 | 修复 Windows 长路径 worktree 创建 | 在当前仓库深度及更深 fixture 下创建隔离子任务成功；失败时不把协作任务误报完成；子任务启动、恢复、集成都有回归证据 |
| P1 | 处理 thinking 参数与思考协议状态 | 每类受支持协议按模型能力构造请求；不支持时明确反馈；测试能断言实际 payload，思考状态不会破坏后续工具轮次 |
| P1 | 恢复或明确替代 default/acceptEdits 语义 | 相同写入操作在两个模式中产生预期不同审批行为；plan 保持只读；终端和 -p 行为一致 |
| P1 | 自动记忆提取、整理、相关召回 | 新会话能召回旧会话事实；重复/矛盾/过期记忆有确定策略；自动提炼不得自动获得执行权限；记录额外模型费用 |
| P1 | 补按行读取与正则搜索 | offset/limit/行号正确；正则合法/非法、大小写、空结果、大文件截断有验证；维持工作区边界 |
| P2 | 协调者模式与协作追踪 | 开启后主 Agent 不能调用受限编辑工具；子 Agent 可完成任务；主从回执、错误和消耗可追踪 |
| P2 | 明确全局/祖先指令与用户角色策略 | 用户可显式注册可信来源；加载次序和来源可见；嵌套项目覆盖行为有验证，保持现有工作区边界 |
| P2 | Skill 快捷执行、trace/回退体验 | 明确支持的命令；快捷执行仍走统一工具权限；提供与 /events、文件/会话恢复相对应的说明 |
| 独立平台项 | OS 沙箱 | 在支持平台实际验证文件/网络/进程限制；不可用时明确拒绝依赖沙箱的全自动模式；进程树管理不能代替该验收 |
| 最后能力验收 | 项目介绍 benchmark | 真实 SWE-bench-Live 官方评分、配对 MCP Token、跨会话记忆、8 小时事实保留、权限弹窗、单/多 Agent 同任务耗时；保留失败和费用证据 |

单/多 Agent 加速应在 worktree 故障修复后重跑。此前 Luna 曾多次请求 spawn_worktree，不能把创建失败解释为模型不支持派发子 Agent。

## 原 Java StarCode 附录

原 Java 已有编程工具、三类协议、MCP、Skill、自动记忆提取、分层指令、子 Agent、团队和 worktree 等实现，因此不能笼统说这些在 Java 全部缺失。与 Python mewcode 基线相比，本次静态检查发现：

| 项目 | 原 Java 状态 | 证据/限制 |
|---|---|---|
| -p / --output-format / --remote | Main 没有基线等价入口 | `src/main/java/com/starcode/Main.java:36` 处理 --team-member、--version、配置路径 |
| 自动记忆整理与相关笔记选择 | 未发现基线 consolidator / find_relevant_memories 等价流程 | 有 MemoryManager 提取笔记，不能将“自动提取”与“自动整理/选择”混为一项 |
| 内置 verification 角色 | 资源目录只有 general-purpose、explore、plan | Python 基线 verification 也是可选功能；是否必须补由角色需求决定 |
| /trace、动态 Skill 快捷命令 | 未见 Python App 同等注册流程 | Java BuiltinCommands 有 /skill、/active-skills、/reload-skills，但不是每个 Skill 的直接执行命令 |
| thinking 参数 | Java 已传 reasoning_effort / Anthropic thinking | 当前 Python MUSE 的 thinking 缺口不能说成原 Java 本来就没有 |

Java 附录是源代码/入口检查，没有在本轮重新运行 Java 编译或平台测试。

## 与项目介绍的关系

不能仅凭“跨会话记忆可保存”宣称“LLM 自动提取和分级指令加载”完全保留，也不能用离线压缩测试替代 8 小时实测。MCP 降幅 85%、权限弹窗 30→5、信息保留 17%→100%、多 Agent 加速 60% 都需要同口径配对数据；功能存在本身不证明这些数值。

此前报告中的真实 SWE-bench-Live 官方评分仍没有可核实结果。本轮未执行该评分，故不变更相关验收状态。

当前最准确的描述是：**Python MUSE 已保留核心 Coding Agent 能力并加入持久化个人助手能力，但与 mewcode 基线存在上述缺失、替代契约和平台故障，尚非完整等价替代。**
