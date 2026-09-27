> 后续修复已实现：本文件保留修复前的审计结果。最新代码、真实模型复测及边界见 [长上下文与 MCP 修复报告](retention-and-mcp-loading.md)。

# 原 StarCode 指标迁移核验

日期：2026-09-27。对象：当前 MUSE 公共 Python 持久化运行时，基于 13e9d19 及工作区评测补丁。

结论：**不能认定原 Benchmark 指标已经全部迁移。存在机制差异与事实保留缺口。** 本次新增的是审计脚本与证据，没有修改产品能力，也没有调用付费模型。

## 原指标与当前证据

| 项目 | 原 StarCode 记录 | 本次结果 | 判定 |
| --- | --- | --- | --- |
| MCP 延迟加载 | 100 工具初始 schema 估计 7377→2420，减少 67.20%；FULL/LAZY 各 10/10 选工具 | 用原 selection-fixture 的 100 个工具运行生产 discovery：一次返回 100 个完整 schema，目录内容 28761 字符；模型侧始终是 mcp_discover/mcp_call 两个入口 | MCP 可用，但原检索/激活机制未等价迁移；67.20% 与 10/10 不可继承 |
| 多 Agent | checkout/numeric/text 三个真实模型任务 3/3，两个并行 Worktree，由主 Agent 整合并统一测试 | 实际 Git worktree 隔离、结果恢复、已完成子任务合并、清理保护和团队通信等回归通过 | 基础组件可用；本次没有重新执行原三项真实模型工作流，原 3/3 未重新证明，更不能声称加速比 |
| 权限确认 | 同一组 180 动作，ALLOW_ONCE 中位数 12，ALLOW_SESSION 中位数 8，总确认 80 | 原 180 动作回放：中位数 9，总确认 94，50/50 高风险探针拒绝，0 个风险自动允许，0 个普通动作校验错误 | 原 8 次指标未复现；审批策略已变化，不能将差异单独归因于性能 |
| 长上下文 | 一轮完整完成；检查点 11/11、17/17、23/23；全批已到达检查点各视图 79/79 | 使用原事实及日志执行生产 compact_messages：三个阶段字段可见数 11/11、11/17、11/23 | 较早阶段事实离开压缩输入；原摘要保留机制未等价迁移 |
| 工程质量 | Java 233 项通过，零跳过 | 本次相关组件定向回归 89 项通过；完整回归另附独立报告 | 测试数量不是 Java/Python 的逐断言等价证明 |

## 执行口径

### MCP

复用原始工具名称、描述与 schema；调用当前 DurableMCP.discover/restore。只用本地假传输提供冻结工具目录，没有外部服务调用。真实本地 stdio/HTTP 传输另外由定向回归覆盖。

当前两个通用工具入口使初始工具数组很小，但 discovery 将全量目录放入工具结果，不能只计算初始两个入口就声称复现 67.20%。本次未使用原 tokenizer 重算，也没有执行原 FULL/LAZY 配对真实模型选工具实验；Token 降幅和选工具成绩均为未测量。

### 权限

复用 permission-v1/fixture.json 的十个会话及 180 动作，映射 bash→run_command、search_text.query→pattern。使用生产 schema、路径判断、风险分类、调用记录及审批绑定；所有实际动作 handler 替换为无副作用成功响应。因此没有执行 Git 推送、删除、下载脚本或磁盘命令。

模拟用户同意普通命令、拒绝高风险命令；50/50 拒绝包含用户拒绝，不能宣称模型或程序自动识别了全部风险。当前工作区内文件编辑不逐动作请求审批，命令逐动作请求审批，没有原来的 ALLOW_SESSION 缓存模式。此口径验证策略，不能代表真实用户的弹窗体验。

### 上下文

复用原 fixture.json 的三阶段事实、最新状态和每阶段 55 段日志，以完整工具调用/结果对构造历史，逐次调用生产 compact_messages（默认 120000 字符）。保留每阶段压缩输入及逐字段检查结果。

本次是组件压力诊断：处理全部日志，而非原 Java 的累计 100K/200K/300K 截止点；没有原来的摘要模型、日志卸载预处理、会话重载和模型抽取步骤。字段可见数不是模型答题分数，也不能与原 79/79 直接相减。它证明在该生产压缩路径下，阶段 1/2 的事实被移出输入，不能保证无需检索就能保留旧事实。持久化历史仍可能存在，不等于磁盘数据丢失。

## 证据及复现

- `benchmarks/legacy_metrics_audit.py`：离线审计入口。
- `reports/legacy-metrics/permissions.json`：逐动作结果。
- `reports/legacy-metrics/mcp.json`：100 工具 discovery 观测。
- `reports/legacy-metrics/context.json`：逐阶段字段检查。
- `reports/legacy-metrics/context-phase-*.json`：实际压缩后的输入。
- `reports/legacy-metrics/fixture-hashes.json`：原夹具 SHA-256。
- `reports/legacy-metrics/evidence-sha256.json`：导出证据哈希。
- `reports/legacy-metrics-regression.xml`：89 项定向回归报告。
- `reports/legacy-metrics-full.xml`：本次全量回归 915 通过、1 失败、2 跳过、2 条依赖弃用警告，耗时 106.04 秒。失败为启动器调用 taskkill 时沙箱返回 Access denied。
- `reports/legacy-launcher-unsandboxed.xml`：沙箱外对启动器三个用例独立复测，3 项全部通过，耗时 3.07 秒。仅处理测试自己创建并校验 PID/启动时间的进程。此结果不覆盖或改写前述全量失败记录。

两项跳过仍为外部基线模型测试禁用、文件符号链接权限缺失；不能视为通过。当前没有一份新的“全量零失败、零跳过”报告。

在工程根目录执行（输出必须使用新目录）：

```powershell
.venv/Scripts/python.exe -m benchmarks.legacy_metrics_audit --source 'C:/Users/Administrator/Desktop/project/star code/benchmarks' --output work/legacy-metrics-new-run
```

首次开发审计脚本时，直接批准后未重新领取任务，生产租约检查正确拒绝继续执行。已修正测试驱动器的领取流程，失败日志 `reports/legacy-metrics-audit.log` 保留；有效运行是 `work/legacy-metrics-audit-02`，不是修改产品来绕过租约。

## 后续修复优先级

1. 长上下文：补齐可验证的历史事实摘要或按需检索，再复跑原累计负载、恢复和模型抽取实验。
2. MCP：实现任务级检索/激活与精确 schema 暴露，随后重测相同 tokenizer、序列化口径及十组配对选择任务。
3. 权限：先明确是否保留当前逐动作策略，或增加用户明确选择且不跨任务隐式复用的授权方式；不能仅为减少确认而放宽权限。
4. 多 Agent：迁移原三任务主 Agent 实际工作流和独立验证器，再单独测量单/多 Agent 配对耗时。

上述项目是后续开发与验收工作，本报告没有把它们标为已修复。
