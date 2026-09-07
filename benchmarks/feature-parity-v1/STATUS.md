# 功能补齐进度：233项全量测试与打包通过，应用及平台验证继续

## 当前验收结果（2026-09-08）

后续更新：当前执行权限已允许在受审查的提升进程中启动CLI，原Java路径访问阻塞已不再阻止该运行。但Windows JLine管道驱动尚不能可靠提交用户消息，集成实验仍未通过，失败批次全部保留。不要重复运行旧全量测试，也不要将本地模拟服务测试称为真实提供商验证。以下关于必须由用户本机运行的说明是先前权限条件下的记录。

用户本机批次 `2026-09-07T14-59-12Z`：233项测试全部通过，失败/错误/跳过均为0；Gradle测试与shadowJar均成功。复核271个源码文件无变化，JAR与测试构建的279个生产类、3个资源逐字节相同。

当前JAR SHA256：`898c9de15f9b0054338c1ad6d3e567b70bd26ae4cf966e3f928f67887dcf11e8`；大小8,034,326字节。机器可读验收见 `../results/feature-parity-accepted.json`。测试发生时源码尚未提交，记录中的13997ac只是当时HEAD，不能称为包含新增功能的生产commit。

新增 `verify-accepted-run.py` 可重新核对源码完整集合、原始XML、JAR哈希和类/资源内容。新增 `run-session-e2e.py` 使用真实打包CLI、AgentLoop、Chat Completions HTTP序列化和生产文件工具；本地固定SSE服务只代替模型响应。驱动程序仅输入用户消息和 `/rewind`，不代替产品修改/恢复文件。它保存fixture、请求/响应、终端、命令时间线和结果JSON，隔离用户home、配置与Memory，不调用付费模型。此测试不是外部服务互操作，也不覆盖并发Worktree或UI会话resume。

Codex内首次应用验证在启动阶段退出，0次HTTP请求；独立Java路径探针确认同一workspace的toRealPath抛AccessDeniedException。原始FAILURE记录保留，环境诊断见 `../results/feature-parity-session-environment.json`。Git暂存也因 `.git/index.lock` 写入拒绝而未执行成功。因此生产冻结和应用E2E须通过已准备好的本机入口继续，不能据此否定已通过的233项测试。

```powershell
& 'C:\Users\Administrator\Desktop\project\star code\benchmarks\feature-parity-v1\run-next-gate.ps1'
```

此入口先重新核验已通过快照，确认没有其他已暂存改动，然后提交明确列出的源码、示例配置、验证脚本和状态文档，打印FROZEN_COMMIT，再运行本地CLI集成测试。不会重复全量Gradle或改变原baseline tag。完整兼容性与性能对齐仍为NOT_VERIFIED。

## 历史记录（以下为本次PASS之前的过程）

## 2026-09-08 更新

用户在本机 PowerShell 的完整测试已经成功启动：批次 `2026-09-07T05-10-36Z` 共231项，230通过、1失败。唯一失败是检查点恢复后消息不相等，根因是 Jackson 将 JsonNode 的 JSON null 恢复成 NullNode，而实时消息使用 Java null。现已在 ChatMessage 构造时统一空状态，保留非空协议结构和防御性拷贝；没有放宽测试断言。

修复后的 ConversationTest 共5项独立运行全部通过，包括两项新增 JSON 往返回归。这不等于最终全量测试通过：Codex 的 Gradle 仍被 journal-1.lock 访问限制阻塞，独立编译也保留了 JAR 关闭权限异常记录。证据见 `../results/feature-parity-null-state-verified.json`。本机需要重新运行下方同一命令，此次预期至少233项通过后才打包。旧交付 JAR 保持不变。

脚本现在保存失败测试数量和XML，并直接打印失败用例；Java版本通过标准输出读取，避免将 PowerShell 的 NativeCommandError 包装混入版本字段。

日期：2026-09-07。此文件描述本轮未发布的改动，不覆盖旧版本的217项通过记录。不能称为“已实现完整兼容性和性能对齐”。

## 已加入的代码

| 能力 | 实现 | 使用方式与限制 |
|---|---|---|
| Chat Completions | 新增 OpenAiCompatClient，配置与工厂接入；流式文本、按 index 汇聚工具调用、历史和工具结果回传、缓存用量、reasoning_content、限流与截断检查 | protocol: openai-compat；base_url 是 API 根路径，客户端追加 /chat/completions；stream_options/include_usage 和 reasoning_effort 仍须目标服务支持，尚未逐服务实测 |
| Mew 协议别名 | openai 归一化为 openai-responses | 不代表整个 Mew 配置文件格式已兼容；密钥仍从环境变量读取 |
| 文件检查点 | 每个主 Agent 用户回合前保存；write_file/edit_file 记录原内容和新内容；会话目录持久化；Worktree 共享历史 | `/rewind` 列表，`/rewind ID files`、`conversation`、`both`；不指定模式默认 both |
| 回退冲突处理 | 写入前保存意图；恢复前检查所有受影响文件；拒绝覆盖与历史两端都不匹配的手工改动；恢复失败尝试撤销已应用恢复 | 仅记录专用文件工具；Shell、外部编辑、长久 Memory 不回退。单文件上限16MiB。文件与会话日志跨文件恢复不是进程崩溃下的原子事务；选中检查点保留，可重试 conversation 恢复 |
| 跨平台 Shell | Windows PowerShell；Linux/macOS Bash；完整命令作为一个参数 | Linux/macOS 尚无实际运行验证 |
| 可选 Shell 沙箱 | Linux bubblewrap、macOS sandbox-exec；required 模式不可用则失败；网络默认禁止 | `$env:STAR_CODE_SANDBOX='required'`；网络显式 opt-in `STAR_CODE_SANDBOX_NETWORK=true`；默认 off；Windows required 会拒绝执行 |
| 无 usage 响应 | 不将完整历史锚定到0 Token，退回生产字符估算 | 避免兼容服务省略 usage 时压缩阈值永远不被触发；不是准确的服务端 Token 数 |

沙箱仅包装 bash 工具进程。它允许系统文件读取，限制工作目录和临时目录之外的写入，并按配置限制网络；不隔离主 JVM、MCP 服务、用户 Hook 和外部 Team 后端。不能宣称整个 Agent 的内核隔离或密钥保密。

## 测试与环境证据

新增协议、配置、回退、命令分发、Shell 策略和无用量估算测试，并更新命令数量断言。

1. 正常 Gradle 测试先遇到依赖 JAR 读取拒绝，随后在 journal-1.lock 上被 Windows 拒绝访问。已有目录读写授权未解决该运行时限制。
2. 独立工作区构建仍在 Java toRealPath/JAR 关闭时出现 AccessDeniedException；编译器有时返回0，不能只凭退出码接受构建。
3. 早期候选快照的独立 JUnit 运行器发现227项测试：146通过、81失败。77项直接为 AccessDeniedException，1项为该临时运行器将测试资源放入 JAR 后的资源路径错误，3项为断言失败（其中1项包裹 AccessDeniedException）。这些失败未被跳过或计作通过。**此快照早于最后的 Worktree 路径、检查点保留和补充测试修改，不是最终代码的通过证据。**
4. 最后一次正式 Gradle 验证原始记录：`../results/raw/feature-parity-v1/2026-09-07T05-05-42Z/`，状态 FAILURE，原因是 Gradle journal 锁访问拒绝。没有进行新真实模型或性能实验。
5. 最终候选源码的4个局部测试类（ProtocolToolFlowTest、ErrorClassificationTest、ShellRuntimeTest、CommandRegistryTest）共20项全部通过。它们覆盖本地模拟协议及参数策略，不覆盖实际文件回退、完整应用会话或内核沙箱。编译器仍有 JAR 关闭权限异常，不能据此接受完整构建。原始局部记录和源码哈希保存在 `../results/raw/feature-parity-v1/partial-validation-2026-09-07/`；汇总 `../results/feature-parity-v1-validation.json`，索引 `../results/feature-parity-v1-artifact-index.json`。

当前执行策略不允许直接提升 shell 权限。因此需要在你的本机 PowerShell 中运行下列已准备好的验证入口；它不调用真实模型、不改变系统 ACL，仅运行测试，全部通过后才打包。

```powershell
& 'C:\Users\Administrator\Desktop\project\star code\benchmarks\feature-parity-v1\run-validation.ps1' -Package
```

脚本保存源码 SHA256、Java/OS、Git commit、耗时、测试数量、完整日志和 JSON；检查至少233项测试、零失败/错误/跳过，并验证运行中源码未变。最终打印 STATUS 与 RESULTS 路径。如遇真实代码失败，使用这些日志继续修复；不能绕过测试门槛。

当时未替换旧 JAR。现已由上方233项通过批次生成新包；旧 JAR 的217项记录仅适用于旧生产 commit ae10a0f。

## 仍待完成

- 全量测试已完成；真实应用 `/rewind` E2E、会话恢复、并发子 Agent 和 Worktree仍待完成。
- Linux/macOS 实际 Shell、沙箱写入/网络拒绝验证；Windows 没有新增 OS 沙箱实现。
- 真实 Chat Completions 兼容服务互操作验证、差异配置说明。
- 冻结通过验证的生产版本，再执行同条件 MCP 和至少8任务×2模式×3次的性能实验。不能预填85%/60%等目标数字。
- 长上下文可靠性、自动限流退避和真实 SWE-bench-Live 仍在后续范围内。

源文件改动保留在工作区，尚未封为已验证生产版本。完整性能与兼容性对齐仍是未完成目标。
