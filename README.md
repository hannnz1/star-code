# MUSE — Python AI 编程与任务助手

MUSE 是以 Python 为核心的 AI 助手：在保留 StarCode 编程能力的基础上，提供网页研究、资料整理和后台任务，支持网页工作台、Textual 界面及纯文本终端。

本项目以 `mewcode-python` 为源码基线，沿用原 StarCode 的模型服务地址、代理和凭据来源。模型通过配置选择；Skill、角色和子任务不能自行切换服务。当前版本为 **0.3.0rc8 开发候选**，Python 代码位于本仓库的 [muse-python-rc8 分支](https://github.com/hannnz1/star-code/tree/muse-python-rc8)。

> 功能开发和本机自动回归已完成；独立 Windows 环境、真实 Linux/macOS 沙箱、模型质量指标和人工验收仍有待完成。当前不能宣称“Java 完全替代版已正式验收”。

## 功能

| 能力 | 说明 |
| --- | --- |
| 编程助手 | 阅读项目、修改代码、运行验证；保留工具回执、文件检查点和审批记录 |
| 网页研究 | 阅读公开网页，整理带来源记录的报告 |
| 资料整理 | 提取 TXT、Markdown、文本 PDF 的内容，生成可下载、可追溯的成果 |
| 后台任务 | API 与持久化 Worker 分离；关闭网页或终端后任务继续，可暂停、恢复和取消 |
| MCP 按需加载 | 支持 HTTP/stdio 发现、搜索、加载及调用；发现和执行分别受权限约束 |
| Skill 与项目指令 | Markdown/YAML 技能、受限引用、角色目录和来源快照；支持显式运行技能 |
| 多 Agent 协作 | 持久化子任务、隔离 Git worktree、团队消息、依赖看板和审查后整合 |
| 记忆管理 | 用户/项目作用域、候选确认、版本历史及撤回；可选自动提取、整理与语义召回 |
| 权限模式 | default、acceptEdits、plan；审批绑定任务策略、工作区及实际参数 |
| 过程与恢复 | 工具耗时、任务树 trace、计划来源、思考摘要、对话分叉和文件回退 |
| 状态迁移 | SQLite 持久化、迁移前数据库备份、完整状态包备份与恢复 |
| 可选 OS 沙箱 | Linux bubblewrap / macOS Seatbelt 接入；required 模式失败时拒绝裸执行，Windows 明确不支持 |

自动记忆维护和显式 thinking 参数默认关闭。网页显示的是服务返回的思考摘要；私有签名或 encrypted 状态不公开导出。

## 运行结构

网页、TUI 和终端通过同一 API 创建任务、查看成果和处理审批；Worker 领取持久化任务，由 Agent 调用模型与工具。

```text
网页 / Textual TUI / 纯文本终端
                  │
              MUSE API
                  │
       SQLite 任务、状态与事件
                  │
          Worker → Agent → 模型服务
                       └→ 文件 / 命令 / 网页 / MCP / 子任务
```

主要源码位于 `src/muse/`；`frontend/` 是网页工作台；`tests/` 是自动回归；`benchmarks/` 是评测工具。旧 `mewcode` 辅助实现用于兼容和基线参考，公开命令入口共用 MUSE 服务。

## 环境要求

- Python **3.12 或以上**。
- Node.js 和 npm：用于源码安装时构建网页。
- Git：用于项目检查、隔离工作区和整合。
- 可访问的模型服务及对应凭据。Python 主运行路径不要求 Java/JRE；无 Java 的完整替代验收仍需独立环境验证。

以下命令在 **Python 分支的项目根目录**执行。原桌面 Java 项目只有配置文件时，不能直接在那里运行 Python 启动脚本。

## Windows 快速启动

### 1. 获取代码与安装

首次下载可执行：

```powershell
git clone --branch muse-python-rc8 --single-branch https://github.com/hannnz1/star-code.git muse-python
cd muse-python
.\Setup-MUSE.ps1
```

已有同一分支且工作区干净时，可使用 `git pull --ff-only` 更新；不要覆盖未提交的本地修改。

安装脚本创建虚拟环境、安装锁定依赖、下载 Chromium 并构建网页。它不调用模型 API；需要联网下载依赖。已有可用环境时无需重复安装。

### 2. 配置模型

通过 `-Config` 指定现有 StarCode YAML 文件。下面示例沿用原配置的 `gpt-5.4-mini`，请按自己的配置调整路径和模型 ID：

```powershell
.\Start-MUSE.ps1 -Config 'C:/Users/Administrator/Desktop/project/star code/config.yaml' -Model 'gpt-5.4-mini'
```

**请显式传入 `-Model`。** 当前启动脚本省略该参数时默认使用 `gpt-6-sol`；这会覆盖运行时模型 ID，不会改写原配置文件。不同模型的评测结果不能混用。

若配置使用 `api_key_env: OPENAI_API_KEY`，先确保启动窗口存在该环境变量。缺少时可安全输入：

```powershell
if (-not $env:OPENAI_API_KEY) {
    $env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new(
        '',
        (Read-Host '请输入 OpenAI API Key' -AsSecureString)
    ).Password
}
```

不要将实际密钥写入 README、测试报告或 Git 提交。其他配置使用不同环境变量时，以 `api_key_env` 为准。

### 3. 登录网页

启动器同时运行 API 和 Worker，默认打开：

```text
http://127.0.0.1:8765
```

在登录框填写启动窗口显示的**本地访问令牌**，不是模型 API Key。使用默认数据目录时，也可在本机查看：

```powershell
Get-Content -LiteralPath '.muse/access-token'
```

进入后添加一个已存在的工作区，例如 `C:/Projects/muse-test`，选择任务类型、权限模式，再提交目标。真实任务会调用配置中的模型 API，并可能产生费用。

### 4. 使用终端

API 和 Worker 保持运行，另开 PowerShell，进入同一项目目录：

```powershell
.\.venv\Scripts\python.exe -m muse tui --data-dir .muse --workspace 'C:/Projects/muse-test'

# 或纯文本终端
.\.venv\Scripts\python.exe -m muse terminal --data-dir .muse --workspace 'C:/Projects/muse-test'
```

工作区目录需要提前创建。终端、API 和 Worker 必须使用相同数据目录和端口；若启动时指定其他端口，终端也传相同的 `--port`。

### 5. 停止服务

```powershell
.\Stop-MUSE.ps1
```

关闭浏览器不会停止 Worker。上述停止脚本适用于启动脚本管理的进程；手动运行 `python -m muse api/worker` 时，应在各自窗口按 `Ctrl+C` 停止。

## 手动启动与独立测试状态

需要单独控制进程或隔离试用数据时，可分别在两个终端执行：

```powershell
# 窗口 A：API
$env:MUSE_MODEL = 'gpt-5.4-mini'
.\.venv\Scripts\python.exe -m muse api --config 'C:/Users/Administrator/Desktop/project/star code/config.yaml' --data-dir './work/manual-test-state' --port 8876

# 窗口 B：Worker；该窗口同样需要可用的模型凭据
$env:MUSE_MODEL = 'gpt-5.4-mini'
.\.venv\Scripts\python.exe -m muse worker --config 'C:/Users/Administrator/Desktop/project/star code/config.yaml' --data-dir './work/manual-test-state' --port 8876
```

访问 `http://127.0.0.1:8876`，登录令牌位于 `work/manual-test-state/access-token`。终端入口也需传 `--data-dir ./work/manual-test-state --port 8876`。

API 与 Worker 的配置、模型和状态目录必须一致。令牌属于对应状态目录，不能混用。

## 首次功能试用

先创建测试工作区，在其中准备 README、requirements 和 notes 等自制资料。使用“编程助手”及“只读计划”模式提交：

```text
阅读 README.md、requirements.md 和 notes.md，
用中文列出项目要求、待办和实现计划，注明来源文件。
不修改文件，不执行命令。
```

确认资料总结正确、文件未变，再按下表继续：

| 测试 | 操作 | 验收要点 |
| --- | --- | --- |
| 编程 | 完成只读计划后，终端输入 `/do 按计划实现并运行测试` | 实际修改符合目标，有真实验证回执 |
| 权限 | 新任务分别选择 default、acceptEdits、plan | default 写入/执行审批；acceptEdits 工作区编辑自动允许、执行审批；plan 只读 |
| 网页研究 | 选择“网页研究”，提供两个公开网页并要求比较与引用 | 来源可核对，读取失败不伪造 |
| 资料整理 | 要求整理自制 TXT/Markdown 并生成报告 | 成果可下载，原文不变 |
| 后台执行 | 提交任务后关闭网页，再打开查看 | Worker 保持运行时任务继续；暂停、恢复、取消生效 |
| Skill | 查看 `/skills`，使用 `/run-skill NAME ARGS` | 参数与来源正确，执行仍受权限约束 |
| 多 Agent | 在已提交的 Git 测试仓库启用协调者，要求两个隔离子任务并统一验证 | 子任务、审批和整合可追踪；父工作区有最终验证 |
| 记忆 | 显式开启维护后，检查候选、确认、重开召回与撤回 | 来源正确、作用域隔离、撤回后不再作为有效记忆注入 |

任务持续“排队中”时先检查 Worker 是否运行；“等待批准”时查看动作详情后审批，不代表模型连接失败。详细标准见[最终人工验收清单](docs/muse-upgrade-human-acceptance-2026-09-28.md)。

## 常用终端命令

| 用途 | 命令 |
| --- | --- |
| 帮助与模型 | `/help`、`/model`、`/cost`、`/context` |
| 任务选择与控制 | `/tasks`、`/use ID`、`/status`、`/clear`、`/pause`、`/resume`、`/cancel` |
| 计划与审查 | `/plan PROMPT`、`/do PROMPT`、`/review PROMPT` |
| 权限与审批 | `/mode default\|acceptEdits\|plan`、`/approvals`、`/approve ID`、`/deny ID`、`/renew ID` |
| 记忆管理 | `/memory`、`/memory-jobs`、`/memory-candidates`、`/confirm-memory ID`、`/withdraw-memory ID`、`/memory-history ID` |
| 协作与扩展 | `/coordinator on\|off`、`/children`、`/worktree`、`/team`、`/board`、`/skills`、`/run-skill NAME ARGS`、`/agents`、`/mcp` |
| 过程与恢复 | `/trace`、`/thinking`、`/checkpoints`、`/rewind`、`/reload`、`/sandbox` |

`/clear` 只清除客户端选择，已有任务继续运行。审批续期不等于批准；先重新查看动作再审批。协调者根任务不能直接编辑或运行命令，最终成果需要父工作区的实际验证。

## 可选记忆设置

合并到现有 YAML，保留原 `providers`。以下示例只启用自动提取：

```yaml
memory:
  auto_extract: true
  auto_consolidate: false
  semantic_recall: false
  budget_tokens: 32768
  max_requests: 4
  recall_top_k: 10
```

修改后重启 API 和 Worker。自动提取仅使用成功、非只读根任务中的用户来源；用户级与冲突候选需要确认。自动整理要求至少 24 小时和 5 个新增合格会话。语义召回是另一项可选模型调用。

`budget_tokens` 和 `max_requests` 是维护配额，不是美元费用上限；真实维护会产生 API 用量。费用未知时保留未知，不按零费用报告。详细设置及迁移说明见[升级说明](docs/muse-upgrade-release-notes-2026-09-28.md)。

## 自动测试与验收状态

**2026-09-28 功能升级提交 `0a61c74` 的上传前全量回归：1075 通过、3 跳过、2 项依赖弃用警告，无失败。** Ruff 与 TypeScript/Vite 构建通过。跳过项为本机 Windows 文件符号链接权限、未配置凭据的外部 consolidation API，以及 Linux/macOS 专用沙箱探针。

这些是对应提交的本机自动结果，不等同于真实模型 Benchmark 或正式发布验收。

新增功能的离线回归可执行：

```powershell
$env:PYTHONUTF8 = '1'
$Cases = @(
    'tests/muse/integration/test_permission_modes.py'
    'tests/muse/integration/test_file_paging_search.py'
    'tests/muse/integration/test_memory_maintenance.py'
    'tests/muse/integration/test_trusted_resources.py'
    'tests/muse/integration/test_upgrade_interfaces.py'
    'tests/muse/integration/test_upgrade_review_regressions.py'
    'tests/muse/integration/test_os_sandbox.py'
    'tests/muse/unit/test_thinking_protocol.py'
)
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider @Cases
```

上述测试使用模拟模型，不调用真实模型 API。真实业务试用、服务探测及模型 Benchmark 会调用 API，应单独记录模型、代码版本、逐例结果、用量和费用。

| 验收项目 | 当前口径 |
| --- | --- |
| 新增功能自动回归 | 已有本机通过记录 |
| 独立干净 Windows、真实 symlink/junction、安装与回滚 | 待独立环境验收 |
| Linux/macOS 内核沙箱 | 待真实平台探针；Windows 不支持；非空网络允许列表明确拒绝 |
| thinking 与记忆质量 | 离线协议/行为已测试，当前所选服务的正式质量试验仍待完成 |
| SWE-bench-Live | 当前汇总未提供可计入本版本的官方完整评分证据 |
| MCP、长上下文、8 小时耐久、权限弹窗、多 Agent 加速 | 历史或部分试验见报告；需按冻结版本与配对方案逐项验收 |

不能将“描述 Token 减少 85%”“8 小时事实保留”“30 次弹窗降至 5 次”“17%→100%”“多 Agent 加速约 60%”作为本次升级已正式验证的成绩。旧版本、不同模型和不同统计口径不拼接。

## 兼容、备份与边界

- `mewcode` 与 `python -m mewcode` 共用 MUSE 服务，保留终端与非交互任务入口；`-p` 返回码：0 成功、1 失败/取消、2 等待人工处理、3 客户端等待超时。超时不会取消后台任务。
- 新版不支持 `bypassPermissions`、`--teammate`、默认远程监听、旧 NDJSON 逐字段兼容，以及文件和对话的联合 `both` 回退。
- 当前数据库 schema 为 10；旧库升级前自动生成数据库备份。完整状态包备份需先停止 API/Worker。回滚时恢复升级前状态副本，不能直接让旧程序读取新库。
- OS 沙箱是可选能力，权限审批和正则子进程不等于内核隔离；required 模式不能静默降级为裸执行。
- 本地配置、密钥、状态包和运行数据不应提交 Git。新版本安装和试用不需要覆盖原 Java 项目。

## 文档与来源

- [本轮功能与验收状态](docs/muse-upgrade-status-2026-09-28.md)
- [功能升级 Spec](docs/superpowers/specs/2026-09-28-muse-mewcode-upgrade-design.md)
- [新版运行、恢复与迁移说明](docs/python-runtime-operations.md)
- [升级说明与配置](docs/muse-upgrade-release-notes-2026-09-28.md)
- [最终人工验收清单](docs/muse-upgrade-human-acceptance-2026-09-28.md)
- [Benchmark 测试计划](docs/mewcode-resume-benchmark-plan.md)
- [历史 Benchmark 实测与限制](docs/mewcode-resume-benchmark-results-2026-09-28.md)
- [独立 Windows 验收](docs/clean-windows-acceptance.md)
- [Java 生产文件映射](docs/java-migration-matrix.csv)、[测试映射](docs/java-test-matrix.csv)、[行为差异](docs/java-behavior-audit.md)
- [开发记录](docs/progress.md)、[源文件哈希](docs/source-manifest.json)

本项目保留 StarCode 与 mewcode-python 的来源标注。上游根级许可证及分发范围尚待核实；仓库公开可见不等于已确认全部第三方代码的再分发许可。
