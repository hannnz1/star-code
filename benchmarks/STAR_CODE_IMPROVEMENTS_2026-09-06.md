# Star Code 改进与验证记录（阶段性）

本轮已补上 MCP 按需暴露、Team 子任务结果查询/等待、会话权限授权。尚未补齐全部短板：Multi-Agent 正常结束、长会话验证、SWE-bench-Live 实例仍有工作，不应标成整体完成。

## 已完成的生产改进

| 项目 | 改动 | 验证与边界 |
|---|---|---|
| MCP | 工具短索引、search_mcp_tools、Agent 独立激活状态、逐轮刷新 schema、FULL 开关；保持权限检查 | 10/25/50/100 工具各模式5次；100工具初始 schema 估算7377→2420，减少67.20%。真实模型10个选择任务，两种模式均10/10；LAZY每任务多一次调用。不是85%，也不是整个任务 Token 降幅 |
| Team | 修复带 Team 名查询后台执行 ID 被错误路由到共享任务存储；增加0–60秒可取消等待；启动结果说明如何收集和集成 | 修复后两个子任务均被主 Agent 成功收集，主 Agent 与独立验收都通过21项检查。但主 Agent 第10轮后仍异常结束，严格 E2E 仍BLOCKED，不计算加速比 |
| 权限 | 新增 ALLOW_SESSION；按工具/目标、命令或参数、目录、Actor、模式限定；新建/恢复会话清空；不落盘 | 10组固定操作回放，每种策略180次决定；确认次数中位数12→8。50次高风险探测均拒绝。用户选择由脚本注入，无真实命令或模型执行，不代表实际用户会话频率 |

完整 Gradle 测试：204项、55个测试套件，失败/错误/跳过均0。另已生成最新版 `build/libs/star-code.jar`；构建与哈希记录见 results/improvements-package-build.log 和 package-manifest.json。

## 主要文件

- MCP生产：src/main/java/com/starcode/tool/ModelToolCatalog.java、Tool.java、ToolRegistry.java；mcp/McpToolAdapter.java；agent/AgentLoop.java；Main.java；permission/PermissionManager.java。
- Team生产：src/main/java/com/starcode/task/TaskGetTool.java、ChatApplication.java。
- 权限生产：src/main/java/com/starcode/permission/ApprovalChoice.java、PermissionManager.java；ui/TerminalUi.java；ChatApplication.java。
- 回归测试：McpLazyLoadingTest、TaskWaitTest、SessionApprovalTest。
- 测试基础设施：benchmarks/mcp-lazy-v1/、multi-agent/、permission-v1/；src/bench/McpLazyBench.java、McpSelectionFixture.java、GateCurrent.java、PermissionBench.java。
- 报告/原始索引：results/mcp-lazy-loading-final.md、multi-agent-postfix-validation.md、permission-v1-final.md；对应 CSV/JSON、artifact-index.json 和 ignored raw目录。

## 提交

- 原始 baseline：014808a0b0942f25bc4f1c3f415fa63262f98176，benchmark-baseline-v1 未改变。
- MCP生产与主要测试：64e4c92f5b623a166879ee5aa86f23fd09d50867；证据提交b80f9be。
- Team修复：53ec9ba；修复前失败证据14c2d27，修复后审计7afb97e。
- 会话权限及固定回放：ba607a3b3dc489228526556127314cab8d7827ce。
- 本报告与后续结果提交可用 `git log -1 --format=%H -- benchmarks/STAR_CODE_IMPROVEMENTS_2026-09-06.md` 查询。

## 未完成和不能写入简历的数字

- “MCP Token 降低85%”没有证据。可限定为100工具合成 fixture 的初始工具 schema 估算降低67.20%，不能泛化到整体 Token 或真实 MCP 市场。
- “8小时不丢上下文”尚未运行长期工作流；单次压缩和会话持久化不等于时长保证。
- “权限弹窗30→5”未证实。12→8仅来自固定合成策略回放，不能替代用户会话统计。
- “信息保留率17%→100%”不能使用。既有 Context 独立模型审核结论仍NEEDS_MORE_TESTING；不是人工审核，也不是已证明优化。
- “Multi-Agent 耗时降低60%”不能使用。普通子 Agent 与 Team 异步路径不同；本轮证明了部分并行及收集能力，但完整结束仍受限。
- SWE-bench-Live 尚无真实 resolved 样本，不应写为已建成并验证的流水线。

## 下一步

优先处理 Main Agent 轮数预算的产品配置与正常结束行为，明确成本/上限后冻结新版本，再做3个不同任务 E2E；不得将旧失败替换掉。通过后才启动速度对照。随后完成重复压缩/恢复/旧 Memory 的长期工作流及真实 SWE-bench-Live 环境可行性验证。

本轮未改 Context 压缩算法/模板、未降低阈值、未启用 OS 沙箱、未修改 MewCode。MCP仍在启动时下载 schema，延迟的是模型上下文暴露；权限路径检查也不构成内核隔离。原始请求、响应及失败保存在本地 ignored raw目录；复制项目时应连同 raw和依赖JAR归档一起保留，Git报告本身不足以重建全部实验。
